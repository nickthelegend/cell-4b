"""Build everything: STLs, GLBs for the viewer, print plates, MANIFEST.md.

    python3 cad/build.py

Refuses to write anything if audit.py reports a FAIL, so a plate that reaches
your slicer has already passed every fit check.
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit
import mocks as M
import partlib as pl
import parts as P
import spec as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
STL = os.path.join(OUT, "stl")
GLB = os.path.join(OUT, "glb")

# print orientation: "asis" | "flipx" (roll 180 so the open face is up)
ORIENT = {
    "shell_upper": "flipx",
    "sensor_deck": "asis",
}

PRINT_SETTINGS = {
    "cartridge": ("white PLA", "0.15 mm, 3 perim, 100%, IRONING ON",
                  "well-side up, no supports"),
    "cartridge_reference": ("white PLA", "as cartridge", "well-side up"),
    "cartridge_null": ("white PLA", "as cartridge", "flat, no supports"),
    "aperture_tube": ("black PLA", "0.12 mm, 4 perim, 100%",
                      "FLANGE DOWN; paint the bore matte black"),
    "optical_head": ("black PLA", "0.12 mm, 6 perim, 40%",
                     "base down, no supports; paint ALL bores matte black"),
    "sensor_deck": ("black PLA", "0.16 mm, 4 perim, 60%", "flat"),
    "slot_baffle": ("black PLA", "0.16 mm, 4 perim, 100%", "flat"),
    "window_jig": ("any", "0.2 mm, 2 perim, 20%", "flat; not a device part"),
    "shell_lower": ("black PLA", "0.16 mm, 4 perim, 25%",
                    "open side up, no supports"),
    "shell_upper": ("black PLA", "0.16 mm, 4 perim, 25%",
                    "TOP FACE DOWN, no supports"),
    "oled_bezel": ("black PLA", "0.12 mm, 4 perim, 100%", "flat, front face down"),
    "sensor_carrier": ("black PLA", "0.16 mm, 4 perim, 100%",
                       "flat; SYMMETRIC -- it clamps the AS7341 either way up"),
    "touch_collar": ("black PLA", "0.12 mm, 5 perim, 40%",
                     "base down; paint the bores matte black"),
}

PLATES = [
    ("Plate 1 - shell lower", ["shell_lower"]),
    ("Plate 2 - shell upper", ["shell_upper"]),
    ("Plate 3 - optics + small parts",
     ["optical_head", "sensor_deck", "touch_collar", "aperture_tube",
      "slot_baffle", "oled_bezel", "sensor_carrier", "window_jig"]),
    ("Plate 4 - cartridges",
     ["cartridge"] * 20 + ["cartridge_reference", "cartridge_null"]),
]


def for_print(name, mesh):
    """Lay a part flat at the origin in its print orientation."""
    m = mesh.copy()
    if ORIENT.get(name) == "flipx":
        lo, hi = m.bbox()
        m.rotate_x(180.0, about=(float((lo[1] + hi[1]) / 2),
                                 float((lo[2] + hi[2]) / 2)))
    lo, hi = m.bbox()
    return m.translate(-float((lo[0] + hi[0]) / 2),
                       -float((lo[1] + hi[1]) / 2), -float(lo[2]))


def pack(items, gap=4.0):
    """Shelf-pack (name, mesh) onto a PLATE_MAX bed. Returns placed meshes."""
    sized = []
    for nm, m in items:
        lo, hi = m.bbox()
        sized.append((nm, m, float(hi[0] - lo[0]), float(hi[1] - lo[1])))
    sized.sort(key=lambda t: -t[3])
    placed, x, y, row_h = [], 0.0, 0.0, 0.0
    for nm, m, w, h in sized:
        if x + w > S.PLATE_MAX and x > 0:
            x, y = 0.0, y + row_h + gap
            row_h = 0.0
        c = m.copy()
        lo, _ = c.bbox()
        c.translate(x - float(lo[0]), y - float(lo[1]), 0.0)
        placed.append((nm, c))
        x += w + gap
        row_h = max(row_h, h)
    return placed, y + row_h


def main():
    os.makedirs(STL, exist_ok=True)
    os.makedirs(GLB, exist_ok=True)

    print("building parts ...")
    parts = {n: fn() for n, (fn, _, _) in P.PARTS.items()}

    print("running audit ...")
    results = audit.run(parts)
    ok = audit.report(results, verbose=False)
    n_fail = sum(1 for r in results if r[0] == "FAIL")
    if not ok:
        print("\nAUDIT FAILED -- nothing written. Run cad/audit.py for detail.")
        return 1

    # keep the measured placement + clearance numbers so the viewer can show
    # what was actually verified, rather than asserting it in prose
    gaps, seats = [], []
    for st, name, detail in results:
        if name.startswith("gap/"):
            pair = name[4:].split("~")
            kind = ("contact" if "designed contact" in detail
                    else "slide" if "sliding fit" in detail else "clear")
            gaps.append({"a": pair[0], "b": pair[1], "kind": kind,
                         "mm": float(detail.split()[0]), "status": st})
        elif name.startswith("seat/"):
            seats.append({"name": name[5:], "detail": detail, "status": st})
    gaps.sort(key=lambda g: g["mm"])

    manifest = {"parts": [], "plates": [], "spec": {}, "mocks": [],
                "audit": {"checks": len(results), "failed": n_fail},
                "gaps": gaps, "seats": seats}

    # ---- STLs, in print orientation -------------------------------------
    print("\nwriting STLs ...")
    printed = {}
    for name, m in parts.items():
        pm = for_print(name, m)
        printed[name] = pm
        n = pl.stl_write(os.path.join(STL, f"{name}.stl"), pm)
        rep = pl.validate(pm)
        lo, hi = pm.bbox()
        mat, settings, orient = PRINT_SETTINGS.get(name, ("?", "?", "?"))
        qty = P.PARTS[name][2]
        manifest["parts"].append({
            "name": name, "qty": qty, "triangles": n,
            "volume_mm3": rep["volume_mm3"], "watertight": rep["watertight"],
            "bbox": [round(float(hi[i] - lo[i]), 2) for i in range(3)],
            "material": mat, "settings": settings, "orientation": orient,
            "colour": P.PARTS[name][1],
        })
        print(f"  {name:22s} {n:7d} tri  "
              f"{hi[0]-lo[0]:6.1f} x {hi[1]-lo[1]:6.1f} x {hi[2]-lo[2]:6.1f} mm"
              f"  x{qty}")

    # ---- assembly GLBs ---------------------------------------------------
    print("\nwriting GLBs ...")
    printed_items = [(n, parts[n], P.PARTS[n][1])
                     for n in parts if not n.startswith("cartridge")]
    printed_items.append(("cartridge", parts["cartridge"], P.PARTS["cartridge"][1]))

    mock_items = []
    for n, (fn, col, alpha) in M.MOCKS.items():
        mock_items.append((n, fn(), col, alpha))
        manifest["mocks"].append({"name": n, "colour": col})

    pl.glb_write(os.path.join(GLB, "assembled.glb"),
                 [(n, m, c, 1.0) for n, m, c in printed_items] + mock_items)
    pl.glb_write(os.path.join(GLB, "printed_only.glb"),
                 [(n, m, c, 1.0) for n, m, c in printed_items])

    # ---- assembly steps --------------------------------------------------
    # Each step is what the bench looks like AFTER that step, so the viewer
    # can be walked forwards like a build. The order is ASSEMBLY.md's, and the
    # last entry of each step is what was just added.
    placed_all = dict(P.assembly())
    mockmap = {n: m for n, m, _c, _a in mock_items}
    colours = {n: c for n, _m, c, _a in mock_items}

    STEPS = [
        ("1 - Pi 4B on its bosses", ["shell_lower", "mock_pi4b", "mock_switch"]),
        ("2 - slot baffle", ["slot_baffle"]),
        ("3 - emitters into the head", ["mock_leds", "mock_laser", "mock_camera"]),
        ("4 - optical head down", ["optical_head"]),
        ("5 - CSI ribbon routed", ["mock_csi_ribbon"]),
        ("6 - aperture tube", ["aperture_tube"]),
        ("7 - sensor deck", ["sensor_deck"]),
        ("8 - AS7341 on the flip-mount", ["mock_as7341", "sensor_carrier"]),
        ("9 - touch collar + its LEDs", ["touch_collar", "mock_touch_leds"]),
        ("10 - cartridge in to stop 2", ["mock_cartridge"]),
        ("11 - upper shell, OLED, windows",
         ["shell_upper", "mock_oled", "oled_bezel", "mock_touch_window"]),
    ]

    def look(n):
        if n in placed_all:
            return placed_all[n], P.PARTS[n][1], 1.0
        return mockmap[n], colours.get(n, "#888888"), 1.0

    manifest["steps"] = []
    running = []
    for i, (title, added) in enumerate(STEPS, 1):
        for n in added:
            m, c, a = look(n)
            running.append((n, m, c, a))
        # dim everything already on the bench, so the new part reads clearly
        items = []
        for n, m, c, a in running:
            new = n in added
            items.append((n, m, c if new else "#4A5058", a if new else 0.55))
        pl.glb_write(os.path.join(GLB, f"step{i}.glb"), items)
        manifest["steps"].append({"id": i, "title": title, "adds": added,
                                  "glb": f"step{i}.glb"})
        print(f"  step {i:2d}  {title:34s} +{', '.join(added)}")

    # ---- exploded: staged along Z in true assembly order ------------------
    # Components ride with the part they mount to, rather than being lifted on
    # an unrelated schedule -- a Pi floating above its own shell is a diagram
    # of nothing.
    STAGE = {
        "shell_lower": 0, "mock_pi4b": 0, "mock_switch": 0, "slot_baffle": 0,
        "mock_leds": 1, "mock_laser": 1, "mock_camera": 1,
        "optical_head": 2, "mock_csi_ribbon": 2,
        "aperture_tube": 3, "sensor_deck": 4,
        "mock_as7341": 5, "sensor_carrier": 5,
        "touch_collar": 6, "mock_touch_leds": 6,
        "mock_cartridge": 1,
        "shell_upper": 8, "mock_oled": 8, "oled_bezel": 9,
        "mock_touch_window": 9,
    }
    GAP = 26.0
    exploded = []
    for n, m, c, a in running:
        exploded.append((n, m.copy().translate(0, 0, STAGE.get(n, 3) * GAP),
                         c, a))
    pl.glb_write(os.path.join(GLB, "exploded.glb"), exploded)

    # Cutaway: the shells hidden and the optical head made translucent, because
    # the camera sits at r = 14.1 -- INSIDE the Ø52 head -- and is otherwise
    # completely invisible in every other view.
    placed = P.assembly()
    cut = [("optical_head", placed["optical_head"], "#5A6270", 0.28),
           ("sensor_deck", placed["sensor_deck"], "#5A6270", 0.35),
           ("aperture_tube", placed["aperture_tube"], "#2E3238", 1.0),
           ("slot_baffle", placed["slot_baffle"], "#2E3238", 1.0)]
    for n, m, c, a in mock_items:
        if n in ("mock_oled", "mock_touch_window"):
            continue
        cut.append((n, m, c, a))
    pl.glb_write(os.path.join(GLB, "cutaway.glb"), cut)

    # ---- plates ----------------------------------------------------------
    print("\npacking plates ...")
    for i, (title, names) in enumerate(PLATES, 1):
        items = []
        counts = {}
        for n in names:
            counts[n] = counts.get(n, 0) + 1
            items.append((f"{n}_{counts[n]}", printed[n]))
        placed, depth = pack(items)
        w = max(float(m.bbox()[1][0]) for _, m in placed)
        pl.glb_write(os.path.join(GLB, f"plate{i}.glb"),
                     [(n, m, P.PARTS[n.rsplit('_', 1)[0]][1], 1.0)
                      for n, m in placed])
        fits = w <= S.PLATE_MAX and depth <= S.PLATE_MAX
        manifest["plates"].append({
            "id": i, "title": title, "parts": counts,
            "extent": [round(w, 1), round(depth, 1)],
            "fits_p1s": fits, "glb": f"plate{i}.glb",
        })
        print(f"  {title:34s} {w:6.1f} x {depth:6.1f} mm  "
              f"{'OK' if fits else 'TOO BIG'}  ({len(placed)} parts)")

    # ---- key numbers for the viewer -------------------------------------
    manifest["spec"] = {
        "envelope": [S.ENV_X, S.ENV_Y, S.ENV_Z],
        "read_spot": [S.RS_X, S.RS_Y, S.Z_SAMPLE],
        "sensor_standoff": S.SENSOR_STANDOFF,
        "sensor_standoff_upstream": S.SENSOR_STANDOFF_UPSTREAM,
        "aperture": [S.APERTURE_BORE, S.APERTURE_LEN],
        "head_dia": S.HEAD_DIA,
        "bores": [{"name": n, "d": d, "tilt": t, "az": a}
                  for n, d, t, a in S.OPTICAL_BORES],
        "pi_holes": [[round(x, 2), round(y, 2)] for x, y in S.pi_holes()],
        "plate_max": S.PLATE_MAX,
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)

    write_manifest_md(manifest)
    print(f"\nwrote {len(parts)} STLs, {len(PLATES)} plates, "
          f"3 assembly GLBs -> {OUT}")
    return 0


def write_manifest_md(man):
    L = []
    L.append("# CELL-4B printed parts\n")
    L.append("Generated by `cad/build.py`. Every number is interpolated from "
             "`cad/spec.py`, so this file cannot drift from the STLs beside "
             "it. Do not hand-edit -- regenerate.\n")
    L.append("| Part | Qty | Triangles | Volume | Size (mm) | Material | Settings | Orientation |")
    L.append("|---|---|---|---|---|---|---|---|")
    for p in man["parts"]:
        b = p["bbox"]
        L.append(f"| `{p['name']}` | {p['qty']} | {p['triangles']} | "
                 f"{p['volume_mm3']:.0f} mm3 | {b[0]} x {b[1]} x {b[2]} | "
                 f"{p['material']} | {p['settings']} | {p['orientation']} |")
    L.append("\n## Plates (Bambu P1S, 256 mm bed, "
             f"{man['spec']['plate_max']:.0f} mm usable)\n")
    L.append("| # | Plate | Footprint | Fits | Contents |")
    L.append("|---|---|---|---|---|")
    for p in man["plates"]:
        contents = ", ".join(f"{k} x{v}" for k, v in p["parts"].items())
        L.append(f"| {p['id']} | {p['title']} | "
                 f"{p['extent'][0]} x {p['extent'][1]} mm | "
                 f"{'yes' if p['fits_p1s'] else 'NO'} | {contents} |")
    L.append("\n## Filament\n")
    black = sum(p["volume_mm3"] * p["qty"] for p in man["parts"]
                if p["material"].startswith("black"))
    white = sum(p["volume_mm3"] * p["qty"] for p in man["parts"]
                if p["material"].startswith("white"))
    L.append(f"- black PLA: {black/1000:.1f} cm3 solid, "
             f"~{black/1000*1.24:.0f} g at 100% (much less at the infills above)")
    L.append(f"- white PLA: {white/1000:.1f} cm3 solid, "
             f"~{white/1000*1.24:.0f} g -- cartridges print at 100%, so take "
             f"this one as real\n")
    L.append("**One white spool, one session, ironing ON.** The white patch on "
             "every cartridge is the photometric reference every gate "
             "normalises against; switching filament mid-batch walks your "
             "thresholds without telling you.\n")
    with open(os.path.join(ROOT, "MANIFEST.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
