"""Mesh-to-mesh interference and clearance measurement.

A bounding box cannot see a collision. Two parts whose AABBs overlap may be
nowhere near each other, and two parts whose AABBs are 40 mm apart are
certainly fine -- but everything in between needs the real surfaces.

Two questions, answered separately because they need different machinery:

  DOES IT INTERPENETRATE?  point-in-solid, by ray casting. Exact for closed
                           meshes, and the only reliable answer.
  HOW CLOSE DOES IT GET?   exact point-to-triangle distance from a sampled
                           point set on one surface to every triangle of the
                           other, both directions.

The sampling is what makes it tractable: a surface point set (vertices plus
triangle centroids plus edge midpoints, subsampled) rather than every vertex
of a 178k-triangle head. That makes the reported gap an UPPER BOUND on the
true minimum -- it can only overstate clearance if the sample misses the
closest spot, and denser sampling on the small parts keeps that honest.
"""
from __future__ import annotations

import numpy as np


def surface_points(mesh, n=600, seed=0):
    """Vertices + triangle centroids + edge midpoints, subsampled to ~n."""
    V, F = mesh._np()
    tri = V[F]
    pts = [V, tri.mean(axis=1),
           (tri[:, 0] + tri[:, 1]) / 2,
           (tri[:, 1] + tri[:, 2]) / 2,
           (tri[:, 2] + tri[:, 0]) / 2]
    P = np.vstack(pts)
    if len(P) > n:
        rng = np.random.default_rng(seed)
        P = P[rng.choice(len(P), n, replace=False)]
    return P


def interior_points(mesh, inside_fn, n=400, seed=0, eps=0.02):
    """Points strictly INSIDE `mesh`, offset off its own surface.

    Surface points are useless for deciding overlap when two parts share a
    face: "inside" is undefined on the boundary, and the ray test settles it by
    a parity that a coincident face makes arbitrary. So step off the surface
    along each triangle's own normal -- whichever way is into the solid -- and
    ask the question somewhere it has an answer.
    """
    V, F = mesh._np()
    tri = V[F]
    c = tri.mean(axis=1)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    L = np.linalg.norm(nrm, axis=1)
    L[L < 1e-12] = 1.0
    nrm = nrm / L[:, None]
    if len(c) > n:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(c), n, replace=False)
        c, nrm = c[idx], nrm[idx]
    plus, minus = c + nrm * eps, c - nrm * eps
    take_plus = inside_fn(mesh, plus)
    Q = np.where(take_plus[:, None], plus, minus)
    return Q[inside_fn(mesh, Q)]


def _pt_tri_dist2(P, tri):
    """Squared distance from each point in P (m,3) to each triangle (k,3,3).

    Ericson, Real-Time Collision Detection, section 5.1.5 -- the region test
    on the barycentric plane, vectorised over both axes.
    Returns (m, k).
    """
    a = tri[:, 0][None, :, :]
    b = tri[:, 1][None, :, :]
    c = tri[:, 2][None, :, :]
    p = P[:, None, :]

    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.einsum('mkc,mkc->mk', ab, ap)
    d2 = np.einsum('mkc,mkc->mk', ac, ap)

    bp = p - b
    d3 = np.einsum('mkc,mkc->mk', ab, bp)
    d4 = np.einsum('mkc,mkc->mk', ac, bp)

    cp = p - c
    d5 = np.einsum('mkc,mkc->mk', ab, cp)
    d6 = np.einsum('mkc,mkc->mk', ac, cp)

    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-20, 1e-20, denom)

    # start with the interior case
    v = vb / denom
    w = vc / denom
    v = np.clip(v, 0.0, 1.0)
    w = np.clip(w, 0.0, 1.0)
    q = a + v[..., None] * ab + w[..., None] * ac

    # vertex regions
    m_a = (d1 <= 0) & (d2 <= 0)
    m_b = (d3 >= 0) & (d4 <= d3)
    m_c = (d6 >= 0) & (d5 <= d6)
    q = np.where(m_a[..., None], a, q)
    q = np.where(m_b[..., None], b, q)
    q = np.where(m_c[..., None], c, q)

    # edge regions
    den_ab = np.where(np.abs(d1 - d3) < 1e-20, 1e-20, d1 - d3)
    t_ab = np.clip(d1 / den_ab, 0.0, 1.0)
    m_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0) & ~m_a & ~m_b
    q = np.where(m_ab[..., None], a + t_ab[..., None] * ab, q)

    den_ac = np.where(np.abs(d2 - d6) < 1e-20, 1e-20, d2 - d6)
    t_ac = np.clip(d2 / den_ac, 0.0, 1.0)
    m_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0) & ~m_a & ~m_c
    q = np.where(m_ac[..., None], a + t_ac[..., None] * ac, q)

    den_bc = (d4 - d3) + (d5 - d6)
    den_bc = np.where(np.abs(den_bc) < 1e-20, 1e-20, den_bc)
    t_bc = np.clip((d4 - d3) / den_bc, 0.0, 1.0)
    m_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0) & ~m_b & ~m_c
    q = np.where(m_bc[..., None], b + t_bc[..., None] * (c - b), q)

    d = p - q
    return np.einsum('mkc,mkc->mk', d, d)


def _aabb(mesh):
    lo, hi = mesh.bbox()
    return np.asarray(lo, float), np.asarray(hi, float)


def aabb_gap(a, b):
    """Separation of two AABBs. Negative means they overlap on all axes."""
    la, ha = _aabb(a)
    lb, hb = _aabb(b)
    sep = np.maximum(lb - ha, la - hb)
    return float(np.max(sep))


def min_gap(a, b, n=600, cutoff=25.0, chunk=64):
    """Approximate minimum surface separation, in mm.

    Returns +inf-ish (the AABB separation) when the boxes are already further
    apart than `cutoff`, because at that range the exact number is not
    interesting and the triangle pass is not worth its time.
    """
    g = aabb_gap(a, b)
    if g > cutoff:
        return g

    best = np.inf
    for src, dst, seed in ((a, b, 0), (b, a, 1)):
        P = surface_points(src, n, seed)
        V, F = dst._np()
        tri = V[F]
        # keep only triangles that could possibly be the closest
        lo, hi = P.min(axis=0) - cutoff, P.max(axis=0) + cutoff
        tlo, thi = tri.min(axis=1), tri.max(axis=1)
        keep = np.all((thi >= lo) & (tlo <= hi), axis=1)
        T = tri[keep]
        if len(T) == 0:
            continue
        for i in range(0, len(P), chunk):
            d2 = _pt_tri_dist2(P[i:i + chunk], T)
            best = min(best, float(np.sqrt(d2.min())))
    return best


def penetration(a, b, inside_fn, n=400, tol=0.15):
    """Deepest genuine overlap between two meshes, in mm.

    A plain point-in-solid test cannot tell TOUCHING from OVERLAPPING: two
    parts that share a face -- a board on a deck, a shell on a shell -- have
    sampled points sitting exactly on the boundary, and half of them classify
    as "inside". Every designed contact in this assembly would read as a
    collision.

    So a point only counts when it is inside the other solid AND further than
    `tol` from its surface. That is a real penetration depth, and it ignores
    contact, coplanar faces and the sampling's own numerical noise.

    Returns (max_depth_mm, n_points_deeper_than_tol).
    """
    if aabb_gap(a, b) > 0:
        return 0.0, 0
    worst, count = 0.0, 0
    for src, dst, seed in ((a, b, 2), (b, a, 3)):
        # interior points, not surface points -- see interior_points(). Two
        # parts that merely touch share no interior, so contact drops out
        # without needing to be whitelisted.
        # eps is deliberately TINY: it only has to escape exact coplanarity,
        # not set the sensitivity. `tol` below is what decides how shallow an
        # overlap counts, and stepping in by tol here would double that
        # threshold silently.
        P = interior_points(src, inside_fn, n, seed)
        if not len(P):
            continue
        ins = inside_fn(dst, P)
        if not ins.any():
            continue
        Q = P[ins]
        V, F = dst._np()
        tri = V[F]
        lo, hi = Q.min(axis=0) - 5.0, Q.max(axis=0) + 5.0
        tlo, thi = tri.min(axis=1), tri.max(axis=1)
        keep = np.all((thi >= lo) & (tlo <= hi), axis=1)
        T = tri[keep] if keep.any() else tri
        for i in range(0, len(Q), 64):
            d = np.sqrt(_pt_tri_dist2(Q[i:i + 64], T).min(axis=1))
            deep = d[d > tol]
            if len(deep):
                worst = max(worst, float(deep.max()))
                count += int(len(deep))
    return worst, count
