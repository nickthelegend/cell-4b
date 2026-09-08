"""Bought-component bodies, in ASSEMBLY coordinates.

This module exists to break a circular dependency and, more importantly, to
make the enclosure's clearance pockets *derived from* the components rather
than guessed at. `parts.optical_head()` subtracts the envelopes below, so a
pocket cannot drift from the body it is meant to clear -- change
`CAM_PCB_L` and the head's pocket changes with it.

Nothing here is printed.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import MultiPoint, box

import partlib as pl
from partlib import Mesh, circle, prism, rounded_rect
import spec as S


def on_axis(mesh, tilt_deg, az_deg):
    """Lay a mesh built along +Z at the origin onto a bore axis through the
    read spot. rotate_x(t) leans +Z toward -Y (azimuth 270), so a further
    rotate_z(az - 270) aims the lean at `az`."""
    mesh.rotate_x(tilt_deg)
    mesh.rotate_z(az_deg - 270.0)
    return mesh.translate(S.RS_X, S.RS_Y, S.Z_SAMPLE)


def _bore(name):
    for n, d, t, a in S.OPTICAL_BORES:
        if n == name:
            return d, t, a
    raise KeyError(name)


# --------------------------------------------------------------------------
# bodies
# --------------------------------------------------------------------------

def led_body(which):
    _d, tilt, az = _bore(which)
    m = prism(circle(S.LED_BODY_D, 32), S.LED_SLANT, S.LED_SLANT + S.LED_BODY_L)
    return on_axis(m, tilt, az)


def laser_body():
    _d, tilt, az = _bore("laser")
    m = prism(circle(S.LASER_BODY_D, 32),
              S.LASER_SLANT, S.LASER_SLANT + S.LASER_BODY_L)
    return on_axis(m, tilt, az)


def camera_body():
    """OV5647 with the lens removed: PCB perpendicular to the bore axis with
    the bare die facing the read spot at CAMERA_SLANT."""
    _d, tilt, az = _bore("camera")
    m = Mesh()
    m += prism(rounded_rect(S.CAM_PCB_L, S.CAM_PCB_W, 2.0),
               S.CAMERA_SLANT, S.CAMERA_SLANT + S.CAM_PCB_T)
    m += prism(box(-S.CAM_SENSOR / 2, -S.CAM_SENSOR / 2,
                   S.CAM_SENSOR / 2, S.CAM_SENSOR / 2),
               S.CAMERA_SLANT - 1.2, S.CAMERA_SLANT)
    m += prism(box(-S.CAM_FFC_W / 2, -S.CAM_PCB_W / 2 - 6.0,
                   S.CAM_FFC_W / 2, -S.CAM_PCB_W / 2),
               S.CAMERA_SLANT + S.CAM_PCB_T,
               S.CAMERA_SLANT + S.CAM_PCB_T + 1.2)
    return on_axis(m, tilt, az)


def as7341_body():
    """The breakout on the spectro boss, chip facing in down the shaft.

    Lives here rather than in mocks so that sensor_deck() can be cut to clear
    it without parts importing mocks -- the same reason the camera body does.
    """
    from partlib import circle, rounded_rect
    from shapely.ops import unary_union
    s = S.SPECTRO_STANDOFF
    m = Mesh()
    holes = unary_union([circle(S.AS_HOLE_D, 20,
                                sx * S.AS_HOLE_DX / 2, sy * S.AS_HOLE_DY / 2)
                         for sx in (-1, 1) for sy in (-1, 1)])
    m += prism(rounded_rect(S.AS_PCB_L, S.AS_PCB_W, 2.0).difference(holes),
               s, s + S.AS_PCB_T)
    m += prism(circle(3.0, 24), s - 1.0, s)
    return on_axis(m, S.SPECTRO_ANGLE, S.AZ_SPECTRO)


# --------------------------------------------------------------------------
# clearance envelopes the head has to make room for
# --------------------------------------------------------------------------

def xy_envelope(mesh, pad):
    """Convex hull of a mesh's XY projection, grown by `pad`.

    Used as a DROP-IN pocket: the head is cut with this profile over the
    body's whole z range, so the component lowers straight down into place
    before the sensor deck caps it. A vertical-walled pocket is also the only
    kind this kernel can cut without CSG.
    """
    V, _F = mesh._np()
    return MultiPoint([(float(x), float(y)) for x, y, _z in V]).convex_hull.buffer(pad)


def z_range(mesh):
    lo, hi = mesh.bbox()
    return float(lo[2]), float(hi[2])


def head_pockets(pad=None):
    """[(profile, z0, z1)] the optical head must clear.

    The LEDs are NOT here: a 5 mm LED slides down its own Ø5.4 bore and needs
    nothing else. The laser barrel and the camera board are both wider than
    their bores, so they need real pockets.

    The laser barrel is a slip fit in a bore (FIT); the camera is a PCB
    dropped into a recess, which is what PCB_FIT is for. Z gets a further
    S.HEAD_DZ at both ends -- see the note on HEAD_DZ in spec.py.
    """
    out = []
    for body, fit in ((laser_body(), S.FIT if pad is None else pad),
                      (camera_body(), S.PCB_FIT if pad is None else pad)):
        z0, z1 = z_range(body)
        out.append((xy_envelope(body, fit),
                    z0 - fit - S.HEAD_DZ,
                    min(z1 + fit + S.HEAD_DZ, S.HEAD_TOP)))
    return out
