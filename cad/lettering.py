"""A monoline geometric alphabet, drawn here rather than borrowed.

Text on a printed part has to become a shapely polygon like everything else in
this kernel. The obvious route -- pull glyph outlines out of a system font --
would bake Helvetica's or SF's contours into a public repository, which is not
ours to redistribute. So the letters are constructed: every glyph is a set of
centrelines, stroked to a constant width with round caps and joins.

That constraint turns out to suit the part. A uniform-stroke face is what
instrument panels have always been lettered in, it reads at small sizes, and a
constant stroke is exactly what a 0.4 mm nozzle wants -- no hairlines to drop,
no thick/thin transitions to smear.

Geometry is normalised: baseline at y=0, CAP HEIGHT at y=1, glyph starts at
x=0. `advance` is the pen movement, so tracking is added on top.

    from lettering import text_polygon
    g = text_polygon("CELL-4B", cap_h=11.0, stroke=1.6)
"""
from __future__ import annotations

import math

from shapely.geometry import LineString
from shapely.ops import unary_union

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _arc(cx, cy, rx, ry, a0, a1, n=22):
    """Elliptical arc centreline, a0/a1 in degrees, CCW."""
    a0, a1 = math.radians(a0), math.radians(a1)
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n),
             cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


# Standard proportions. W is the drawn width of a normal cap; the round stroke
# adds half a stroke width beyond the centreline on each side, which is what
# makes the optical sidebearings come out even.
W = 0.62
M = W / 2.0
_B = 0.50            # bowl top for B/P/R, and the waist of S
_R = 0.27            # bowl radius for round-sided caps


def _ell(a0, a1, n=22, cx=M, cy=0.5, rx=M, ry=0.5):
    return _arc(cx, cy, rx, ry, a0, a1, n)


# --------------------------------------------------------------------------
# the alphabet.  char -> (advance, [centreline paths])
# --------------------------------------------------------------------------

GLYPHS: dict[str, tuple[float, list]] = {
    " ": (0.42, []),
    "-": (0.46, [[(0.07, 0.46), (0.39, 0.46)]]),
    ".": (0.26, [[(0.13, 0.0), (0.13, 0.001)]]),
    "·": (0.30, [[(0.15, 0.44), (0.15, 0.441)]]),      # middle dot
    "/": (0.50, [[(0.03, -0.06), (0.47, 1.06)]]),
    ":": (0.26, [[(0.13, 0.62), (0.13, 0.621)], [(0.13, 0.0), (0.13, 0.001)]]),

    "A": (W, [[(0.0, 0.0), (M, 1.0), (W, 0.0)], [(0.125, 0.33), (W - 0.125, 0.33)]]),
    "B": (W, [[(0.0, 0.0), (0.0, 1.0)],
              [(0.0, 1.0), (0.30, 1.0)] + _arc(0.30, 1.0 - _R, _R, _R, 90, -90)
              + [(0.0, _B)],
              [(0.0, _B), (0.30, _B)] + _arc(0.30, _R, _R + 0.02, _R, 90, -90)
              + [(0.0, 0.0)]]),
    "C": (W, [_ell(58, 302, 30)[::-1]]),
    "D": (W, [[(0.0, 0.0), (0.0, 1.0), (0.28, 1.0)]
              + _arc(0.28, 0.5, W - 0.28, 0.5, 90, -90) + [(0.0, 0.0)]]),
    "E": (0.56, [[(0.0, 0.0), (0.0, 1.0)], [(0.0, 1.0), (0.52, 1.0)],
                 [(0.0, _B), (0.44, _B)], [(0.0, 0.0), (0.52, 0.0)]]),
    "F": (0.54, [[(0.0, 0.0), (0.0, 1.0)], [(0.0, 1.0), (0.52, 1.0)],
                 [(0.0, _B), (0.42, _B)]]),
    "G": (W, [_ell(58, 344, 36), [(0.36, 0.36), (0.61, 0.36)]]),
    "H": (W, [[(0.0, 0.0), (0.0, 1.0)], [(W, 0.0), (W, 1.0)],
              [(0.0, _B), (W, _B)]]),
    "I": (0.16, [[(0.08, 0.0), (0.08, 1.0)]]),
    "J": (0.52, [[(0.52, 1.0), (0.52, 0.26)]
                 + _arc(0.26, 0.26, 0.26, 0.26, 0, -180)]),
    "K": (W, [[(0.0, 0.0), (0.0, 1.0)], [(W, 1.0), (0.02, 0.42)],
              [(0.22, 0.585), (W, 0.0)]]),
    "L": (0.52, [[(0.0, 1.0), (0.0, 0.0), (0.50, 0.0)]]),
    "M": (0.74, [[(0.0, 0.0), (0.0, 1.0), (0.37, 0.30), (0.74, 1.0), (0.74, 0.0)]]),
    "N": (W, [[(0.0, 0.0), (0.0, 1.0), (W, 0.0), (W, 1.0)]]),
    "O": (W, [_ell(0, 360, 40)]),
    "P": (W, [[(0.0, 0.0), (0.0, 1.0)],
              [(0.0, 1.0), (0.30, 1.0)] + _arc(0.30, 1.0 - _R, _R, _R, 90, -90)
              + [(0.0, 1.0 - 2 * _R)]]),
    "Q": (W, [_ell(0, 360, 40), [(0.40, 0.22), (W + 0.03, -0.06)]]),
    "R": (W, [[(0.0, 0.0), (0.0, 1.0)],
              [(0.0, 1.0), (0.30, 1.0)] + _arc(0.30, 1.0 - _R, _R, _R, 90, -90)
              + [(0.0, 1.0 - 2 * _R)],
              [(0.26, 1.0 - 2 * _R), (W, 0.0)]]),
    "T": (0.58, [[(0.0, 1.0), (0.58, 1.0)], [(0.29, 1.0), (0.29, 0.0)]]),
    "U": (W, [[(0.0, 1.0), (0.0, 0.30)]
              + _arc(M, 0.30, M, 0.30, 180, 360) + [(W, 1.0)]]),
    "V": (W, [[(0.0, 1.0), (M, 0.0), (W, 1.0)]]),
    "X": (W, [[(0.0, 0.0), (W, 1.0)], [(0.0, 1.0), (W, 0.0)]]),
    "W": (0.86, [[(0.0, 1.0), (0.215, 0.0), (0.43, 0.66), (0.645, 0.0), (0.86, 1.0)]]),
    "Y": (W, [[(0.0, 1.0), (M, 0.52), (W, 1.0)], [(M, 0.52), (M, 0.0)]]),
    "Z": (0.58, [[(0.0, 1.0), (0.58, 1.0), (0.0, 0.0), (0.58, 0.0)]]),

    "0": (W, [_ell(0, 360, 40)]),
    "1": (0.34, [[(0.02, 0.80), (0.22, 1.0), (0.22, 0.0)]]),
    "2": (W, [_arc(0.31, 0.72, 0.31, 0.28, 190, -18, 26) + [(0.0, 0.0), (W, 0.0)]]),
    "3": (W, [_arc(0.30, 0.745, 0.28, 0.255, 160, -70, 22)
              + _arc(0.30, 0.265, 0.30, 0.265, 80, -170, 24)]),
    "4": (W, [[(0.45, 0.0), (0.45, 1.0), (0.0, 0.26), (W, 0.26)]]),
    "5": (W, [[(0.54, 1.0), (0.06, 1.0), (0.03, 0.56)]
              + _arc(0.30, 0.30, 0.30, 0.30, 100, -105, 26)]),
    "6": (W, [_arc(0.31, 0.30, 0.31, 0.70, 180, 60, 26),
              _ell(0, 360, 28, cx=0.31, cy=0.30, rx=0.31, ry=0.30)]),
    "7": (0.58, [[(0.0, 1.0), (0.58, 1.0), (0.16, 0.0)]]),
    "8": (W, [_ell(0, 360, 26, cx=0.31, cy=0.745, rx=0.28, ry=0.255),
              _ell(0, 360, 26, cx=0.31, cy=0.255, rx=0.31, ry=0.255)]),
    "9": (W, [_arc(0.31, 0.70, 0.31, 0.70, 0, -120, 26),
              _ell(0, 360, 28, cx=0.31, cy=0.70, rx=0.31, ry=0.30)]),
}

# S: two bowls that MEET at the waist (0.31, 0.5) -- the upper runs waist ->
# left -> over the top -> top right, the lower waist -> right -> under ->
# bottom left. Chaining them any other way leaves a gap across the middle.
GLYPHS["S"] = (W, [_arc(0.31, 0.735, 0.31, 0.235, -340, -90, 28)
                   + _arc(0.31, 0.265, 0.31, 0.235, 90, -160, 28)])

TRACKING = 0.14          # extra space between glyphs, in cap heights
STROKE = 0.145           # stroke width, in cap heights


def advance(s: str, tracking: float = TRACKING) -> float:
    """Total pen advance for `s`, in cap heights."""
    if not s:
        return 0.0
    return (sum(GLYPHS[c][0] for c in s)
            + tracking * (len(s) - 1))


def missing(s: str) -> list[str]:
    return sorted({c for c in s if c not in GLYPHS})


def text_polygon(s, cap_h, stroke=None, tracking=TRACKING,
                 cx=0.0, cy=0.0, anchor="center"):
    """`s` as a filled shapely polygon.

    cap_h    cap height in mm
    stroke   stroke width in mm (default: STROKE x cap_h)
    anchor   "center" -> (cx, cy) is the middle of the cap-height box
             "baseline-left" -> (cx, cy) is the baseline at the left edge
    """
    s = s.upper()
    bad = missing(s)
    if bad:
        raise KeyError(f"lettering has no glyph for {bad!r}")
    stroke = STROKE * cap_h if stroke is None else stroke

    total = advance(s, tracking) * cap_h
    if anchor == "center":
        x = cx - total / 2.0
        y = cy - cap_h / 2.0
    else:
        x, y = cx, cy

    parts = []
    for ch in s:
        adv, paths = GLYPHS[ch]
        for p in paths:
            pts = [(x + px * cap_h, y + py * cap_h) for px, py in p]
            if len(pts) == 1:
                pts = pts + [(pts[0][0] + 1e-4, pts[0][1])]
            parts.append(LineString(pts).buffer(
                stroke / 2.0, cap_style=1, join_style=1, resolution=8))
        x += (adv + tracking) * cap_h
    return unary_union(parts)


def text_bounds(s, cap_h, stroke=None, tracking=TRACKING):
    stroke = STROKE * cap_h if stroke is None else stroke
    return (advance(s, tracking) * cap_h + stroke, cap_h + stroke)
