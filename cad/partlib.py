"""partlib — pure-python CAD kernel for CELL-4B.

Adapted from nickthelegend/orchestrator-pad `cad/partlib.py` (same author's
kernel, reused with the same contract) and extended with the layered-sweep
mesher CELL's optical head needs.

Everything is built from 2D shapely profiles extruded into closed triangle
shells. There is deliberately NO 3D CSG: each printable part is a union of
individually-watertight shells. Overlapping/coplanar shells are merged by the
slicer. 2D booleans (shapely) are allowed and encouraged.

The one thing CELL needs that a pure 2.5D kernel does not give you for free is
a bore that enters a wall at an angle -- 45 deg for the white LEDs, 30 deg for
the laser. `layered()` solves that exactly in cross-section: the horizontal
section of a cylinder of radius r whose axis is tilted by theta is an ELLIPSE
with semi-minor r and semi-major r/cos(theta), translated along the tilt
direction by (z - z0) * tan(theta). No approximation in XY; the only error is
the Z quantisation of the stack, which is set by LAYER and is under the print's
own tolerance on a clearance bore.

Units: mm. X right, Y back, Z up.
"""
from __future__ import annotations

import json
import math
import struct

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

EPS = 1e-9

# Z step for layered sweeps. 0.25 mm gives a staircase on an angled bore wall
# of 0.25*tan(45) = 0.25 mm at worst, against a bore that is already 0.4 mm
# oversize for a slip fit. Under the print's own tolerance.
LAYER = 0.25


# ------------------------------------------------------------ 2D shapes ----

def rounded_rect(w, h, r, seg=10):
    """Axis-aligned rounded rectangle centred at origin (CCW)."""
    r = min(r, w / 2 - 1e-6, h / 2 - 1e-6)
    if r <= 1e-6:
        return box(-w / 2, -h / 2, w / 2, h / 2)
    cx, cy = w / 2 - r, h / 2 - r
    corners = [((cx, -cy), -90), ((cx, cy), 0), ((-cx, cy), 90), ((-cx, -cy), 180)]
    pts = []
    for (ox, oy), a0 in corners:
        for t in np.linspace(math.radians(a0), math.radians(a0 + 90), seg + 1):
            pts.append((ox + r * math.cos(t), oy + r * math.sin(t)))
    return Polygon(pts)


def circle(d, seg=64, cx=0.0, cy=0.0):
    t = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    return Polygon(np.column_stack([cx + d / 2 * np.cos(t), cy + d / 2 * np.sin(t)]))


def ellipse(dx, dy, seg=64, cx=0.0, cy=0.0, rot_deg=0.0):
    """Axis-aligned ellipse of diameters dx, dy, then rotated about its centre."""
    t = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    p = Polygon(np.column_stack([dx / 2 * np.cos(t), dy / 2 * np.sin(t)]))
    if rot_deg:
        p = affinity.rotate(p, rot_deg, origin=(0, 0))
    return affinity.translate(p, cx, cy)


def ring2d(outer, inner):
    return outer.difference(inner)


def slot2d(w, h, r=None):
    """Rounded slot (stadium) centred at origin, w along X."""
    r = h / 2 if r is None else r
    return rounded_rect(w, h, r)


# ---------------------------------------------------------- angled bores ----

class Bore:
    """A cylindrical bore whose axis is tilted `tilt_deg` from vertical.

    (x0, y0, z0) is a point ON THE AXIS. `az_deg` is the compass direction the
    axis leans toward, measured in XY from +X toward +Y. `d` is the bore
    diameter measured PERPENDICULAR to the axis -- i.e. the real hole size the
    part has to pass.
    """

    def __init__(self, d, x0, y0, z0, tilt_deg=0.0, az_deg=0.0, seg=40):
        self.d, self.x0, self.y0, self.z0 = d, x0, y0, z0
        self.tilt = math.radians(tilt_deg)
        self.az = math.radians(az_deg)
        self.seg = seg

    def section(self, z):
        """Horizontal cross-section at height z: an ellipse, exactly."""
        run = (z - self.z0) * math.tan(self.tilt)
        cx = self.x0 + run * math.cos(self.az)
        cy = self.y0 + run * math.sin(self.az)
        major = self.d / math.cos(self.tilt)          # along the tilt azimuth
        return ellipse(major, self.d, self.seg, cx, cy, math.degrees(self.az))

    def axis_point(self, z):
        run = (z - self.z0) * math.tan(self.tilt)
        return (self.x0 + run * math.cos(self.az), self.y0 + run * math.sin(self.az))


def layered(outline_fn, z0, z1, dz=LAYER, overlap=0.02):
    """Sweep a z-dependent 2D profile into a stack of thin prisms.

    outline_fn(z) -> (Multi)Polygon evaluated at the MIDDLE of each layer.
    Layers overlap slightly so the slicer unions them without relying on
    coplanar-face contact.
    """
    out = Mesh()
    n = max(1, int(round((z1 - z0) / dz)))
    step = (z1 - z0) / n
    for i in range(n):
        a = z0 + i * step
        b = a + step + (overlap if i < n - 1 else 0.0)
        geom = outline_fn(a + step / 2.0)
        if geom is None or geom.is_empty or geom.area < 1e-9:
            continue
        out += prism(geom, a, b)
    return out


# ------------------------------------------------------------------ mesh ----

class Mesh:
    """Triangle soup with optional coordinate welding.

    Mesh(weld=True): builders reuse a vertex index for identical (rounded)
    coordinates, so walls and caps of ONE shell stitch into a closed manifold.
    Merging meshes with `+=` never welds across meshes -- that is how separate
    shells stay separate.
    """

    def __init__(self, weld=False):
        self.V: list = []
        self.F: list = []
        self._weld = {} if weld else None

    def _pt(self, x, y, z):
        if self._weld is None:
            self.V.append((x, y, z))
            return len(self.V) - 1
        key = (round(x, 6), round(y, 6), round(z, 6))
        i = self._weld.get(key)
        if i is None:
            self.V.append((x, y, z))
            i = self._weld[key] = len(self.V) - 1
        return i

    def add_ring_wall(self, pts, z0, z1):
        n = len(pts)
        b = [self._pt(x, y, z0) for x, y in pts]
        t = [self._pt(x, y, z1) for x, y in pts]
        for i in range(n):
            j = (i + 1) % n
            self.F.append((b[i], b[j], t[j]))
            self.F.append((b[i], t[j], t[i]))

    def add_cap(self, geom, z, up):
        for poly in _polys(geom):
            poly = orient(poly, 1.0)
            tris = shapely.constrained_delaunay_triangles(poly)
            local = {}
            for ring in [poly.exterior, *poly.interiors]:
                for x, y in list(ring.coords)[:-1]:
                    local[(round(x, 6), round(y, 6))] = self._pt(x, y, z)
            for tri in tris.geoms:
                cs = [(round(x, 6), round(y, 6)) for x, y in tri.exterior.coords[:-1]]
                if not all(c in local for c in cs):
                    raise RuntimeError("CDT introduced a vertex off the input rings")
                a, b, c = (local[c] for c in cs)
                area = ((cs[1][0] - cs[0][0]) * (cs[2][1] - cs[0][1])
                        - (cs[2][0] - cs[0][0]) * (cs[1][1] - cs[0][1]))
                if abs(area) < 1e-9:
                    continue
                if (area > 0) != up:
                    a, c = c, a
                self.F.append((a, b, c))

    def _np(self):
        return np.asarray(self.V, dtype=np.float64), np.asarray(self.F, dtype=np.int64)

    def translate(self, dx=0.0, dy=0.0, dz=0.0):
        self.V = [(x + dx, y + dy, z + dz) for x, y, z in self.V]
        return self

    def rotate_z(self, deg, about=(0.0, 0.0)):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        ox, oy = about
        self.V = [((x - ox) * c - (y - oy) * s + ox,
                   (x - ox) * s + (y - oy) * c + oy, z) for x, y, z in self.V]
        return self

    def rotate_x(self, deg, about=(0.0, 0.0)):
        """Rotate about the X axis through (y, z) = about."""
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        oy, oz = about
        self.V = [(x, (y - oy) * c - (z - oz) * s + oy,
                   (y - oy) * s + (z - oz) * c + oz) for x, y, z in self.V]
        return self

    def bbox(self):
        V, _ = self._np()
        return V.min(axis=0), V.max(axis=0)

    def __iadd__(self, other):
        base = len(self.V)
        self.V.extend(other.V)
        self.F.extend((a + base, b + base, c + base) for a, b, c in other.F)
        return self

    def copy(self):
        m = Mesh()
        m.V = list(self.V)
        m.F = list(self.F)
        return m


def _polys(geom):
    if isinstance(geom, Polygon):
        return [] if geom.is_empty else [geom]
    if isinstance(geom, MultiPolygon):
        return [p for p in geom.geoms if not p.is_empty]
    if hasattr(geom, "geoms"):
        out = []
        for g in geom.geoms:
            out.extend(_polys(g))
        return out
    raise TypeError(f"expected polygonal geometry, got {geom.geom_type}")


def _rings(poly):
    poly = orient(poly, 1.0)

    def clean(ring):
        pts = [(x, y) for x, y in list(ring.coords)[:-1]]
        return [p for i, p in enumerate(pts)
                if abs(p[0] - pts[i - 1][0]) > EPS or abs(p[1] - pts[i - 1][1]) > EPS]
    return clean(poly.exterior), [clean(r) for r in poly.interiors]


def prism(geom, z0, z1):
    """Closed extrusion of a (Multi)Polygon (holes supported)."""
    out = Mesh()
    for poly in _polys(geom):
        m = Mesh(weld=True)
        ext, holes = _rings(poly)
        m.add_ring_wall(ext, z0, z1)
        for h in holes:
            m.add_ring_wall(h, z0, z1)
        m.add_cap(poly, z1, up=True)
        m.add_cap(poly, z0, up=False)
        out += m
    return out


# ------------------------------------------------------------ validation ----

def validate(mesh):
    """Split into connected shells; each must be closed, edge-manifold,
    consistently wound and positive-volume. Returns a report dict."""
    V, F = mesh._np()
    report = {"vertices": len(V), "triangles": len(F), "shells": 0,
              "watertight": True, "problems": [], "volume_mm3": 0.0}
    if len(F) == 0:
        report["watertight"] = False
        report["problems"].append("empty mesh")
        return report

    edges = {}
    for fi, (a, b, c) in enumerate(F):
        if a == b or b == c or a == c:
            report["problems"].append(f"degenerate face {fi}")
            continue
        for e in ((a, b), (b, c), (c, a)):
            edges[e] = edges.get(e, 0) + 1

    parent = list(range(len(F)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    by_edge = {}
    for fi, (a, b, c) in enumerate(F):
        for e in ((a, b), (b, c), (c, a)):
            k = (min(e), max(e))
            if k in by_edge:
                union(fi, by_edge[k])
            else:
                by_edge[k] = fi

    for (a, b), n in edges.items():
        if n != 1 or edges.get((b, a), 0) != 1:
            report["watertight"] = False
            report["problems"].append(
                f"edge {a}->{b} count {n}, reverse {edges.get((b, a), 0)}")
            if len(report["problems"]) > 12:
                report["problems"].append("... (truncated)")
                return report

    shells = {}
    for fi in range(len(F)):
        shells.setdefault(find(fi), []).append(fi)
    report["shells"] = len(shells)
    vol_total = 0.0
    for faces in shells.values():
        vol = 0.0
        for fi in faces:
            a, b, c = F[fi]
            vol += float(np.dot(V[a], np.cross(V[b], V[c]))) / 6.0
        if vol <= 0:
            report["watertight"] = False
            report["problems"].append(f"shell volume {vol:.3f} <= 0 (inverted?)")
        vol_total += vol
    report["volume_mm3"] = round(vol_total, 2)
    return report


# --------------------------------------------------------------- exports ----

def _explode(mesh):
    V, F = mesh._np()
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    n = n / ln
    return tri.reshape(-1, 3).astype(np.float32), np.repeat(n, 3, axis=0).astype(np.float32)


def stl_write(path, mesh, header=b"cell4b"):
    V, F = mesh._np()
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    n = (n / ln).astype(np.float32)
    tri32 = tri.astype(np.float32)
    with open(path, "wb") as fh:
        fh.write(header[:80].ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(F)))
        for i in range(len(F)):
            fh.write(n[i].tobytes())
            fh.write(tri32[i].tobytes())
            fh.write(b"\0\0")
    return len(F)


def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def glb_write(path, items):
    """items: list of (name, Mesh, '#RRGGBB'[, opacity]) -> one node each."""
    bin_chunk = b""
    views, accessors, meshes, nodes, materials = [], [], [], [], []

    def add_view(blob, target):
        nonlocal bin_chunk
        views.append({"buffer": 0, "byteOffset": len(bin_chunk),
                      "byteLength": len(blob), "target": target})
        bin_chunk += blob + b"\0" * (-len(blob) % 4)
        return len(views) - 1

    for i, item in enumerate(items):
        name, mesh, hexcol = item[0], item[1], item[2]
        alpha = item[3] if len(item) > 3 else 1.0
        pos, nrm = _explode(mesh)
        idx = np.arange(len(pos), dtype=np.uint32)
        vp = add_view(pos.tobytes(), 34962)
        vn = add_view(nrm.tobytes(), 34962)
        vi = add_view(idx.tobytes(), 34963)
        accessors += [
            {"bufferView": vp, "componentType": 5126, "count": len(pos), "type": "VEC3",
             "min": [float(x) for x in pos.min(axis=0)],
             "max": [float(x) for x in pos.max(axis=0)]},
            {"bufferView": vn, "componentType": 5126, "count": len(pos), "type": "VEC3"},
            {"bufferView": vi, "componentType": 5125, "count": len(idx), "type": "SCALAR"},
        ]
        rgb = [_srgb_to_linear(int(hexcol[j:j + 2], 16)) for j in (1, 3, 5)]
        mat = {"name": f"{name}-mat", "pbrMetallicRoughness": {
            "baseColorFactor": [*rgb, alpha], "metallicFactor": 0.05,
            "roughnessFactor": 0.55}}
        if alpha < 1.0:
            mat["alphaMode"] = "BLEND"
            mat["doubleSided"] = True
        materials.append(mat)
        meshes.append({"name": name, "primitives": [{
            "attributes": {"POSITION": 3 * i, "NORMAL": 3 * i + 1},
            "indices": 3 * i + 2, "material": i}]})
        nodes.append({"mesh": i, "name": name})

    gltf = {"asset": {"version": "2.0", "generator": "cell4b partlib"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes, "meshes": meshes, "materials": materials,
            "bufferViews": views, "accessors": accessors,
            "buffers": [{"byteLength": len(bin_chunk)}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_chunk)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk)


# ------------------------------------------------------------ smoke test ----

if __name__ == "__main__":
    import sys
    ok = True

    slab = prism(ring2d(rounded_rect(40, 30, 6), circle(10)), 0, 5)
    r = validate(slab)
    print("prism+hole :", r["shells"], "shell(s), watertight:", r["watertight"],
          r["problems"][:2])
    ok &= r["watertight"] and r["shells"] == 1

    # A 45 deg bore through a block: the section must migrate by exactly the run.
    b = Bore(5.4, 0.0, 0.0, 0.0, tilt_deg=45.0, az_deg=0.0)
    s0, s1 = b.section(0.0), b.section(10.0)
    dx = s1.centroid.x - s0.centroid.x
    print(f"bore 45deg  : section moved {dx:.3f} mm over 10 mm rise "
          f"(expect 10.000)")
    ok &= abs(dx - 10.0) < 1e-6
    # semi-major must be d/cos(45)
    w0 = s0.bounds[2] - s0.bounds[0]
    print(f"bore 45deg  : section major {w0:.3f} (expect {5.4/math.cos(math.radians(45)):.3f})")
    ok &= abs(w0 - 5.4 / math.cos(math.radians(45))) < 0.02

    blk = layered(lambda z: rounded_rect(30, 30, 3).difference(b.section(z)), 0, 10)
    r = validate(blk)
    print("layered bore:", r["shells"], "shell(s), watertight:", r["watertight"],
          r["problems"][:2], f'{r["volume_mm3"]:.0f} mm3')
    ok &= r["watertight"]

    print("SMOKE", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
