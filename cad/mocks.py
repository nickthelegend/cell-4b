"""Dimensional mock-ups of the bought parts, placed where they assemble.

These are NOT printed. They exist so the viewer shows a real assembly and so
audit.py can be extended to test against the actual bodies rather than against
my assumptions about them. Every dimension comes from spec.py, so a mock and
the pocket that houses it cannot drift apart.
"""
from __future__ import annotations

import math

from shapely.geometry import box
from shapely.ops import unary_union

import bodies as BD
import partlib as pl
from partlib import Bore, Mesh, circle, prism, rounded_rect
import parts as P
import spec as S


def _axis_solid(mesh, tilt_deg, az_deg, cx, cy, cz):
    """Take a mesh built along +Z about the origin and lay it on a bore axis.

    rotate_x(t) sends +Z to (0, -sin t, cos t), i.e. it leans toward -Y, which
    is azimuth 270. So a further rotate_z(az - 270) points the lean at `az`.
    """
    mesh.rotate_x(tilt_deg)
    mesh.rotate_z(az_deg - 270.0)
    return mesh.translate(cx, cy, cz)


def _on_bore(name, d, length, slant0, colour):
    """A cylinder lying on one of the optical bores, from slant0 outward."""
    tilt, az = None, None
    for n, _bd, t, a in S.OPTICAL_BORES:
        if n == name:
            tilt, az = t, a
    m = prism(circle(d, 32), slant0, slant0 + length)
    return _axis_solid(m, tilt, az, S.RS_X, S.RS_Y, S.Z_SAMPLE), colour


# --------------------------------------------------------------------------
# Raspberry Pi 4B
# --------------------------------------------------------------------------

def pi4b():
    z = S.PI_PCB_Z
    m = Mesh()
    # PCB, with the four mounting holes
    holes = unary_union([circle(S.PI_HOLE_D, 20, x, y) for x, y in S.pi_holes()])
    corners = [S.pi_to_case(0, 0), S.pi_to_case(S.PI_L, S.PI_W)]
    x0, x1 = sorted([corners[0][0], corners[1][0]])
    y0, y1 = sorted([corners[0][1], corners[1][1]])
    pcb = rounded_rect(S.PI_L, S.PI_W, S.PI_CORNER_R)
    pcb = pl.affinity.translate(pcb, (x0 + x1) / 2, (y0 + y1) / 2)
    m += prism(pcb.difference(holes), z, z + S.PI_PCB_T)

    top = z + S.PI_PCB_T

    def blk(bx0, by0, bx1, by1, h, base=None):
        p0 = S.pi_to_case(bx0, by0)
        p1 = S.pi_to_case(bx1, by1)
        g = box(min(p0[0], p1[0]), min(p0[1], p1[1]),
                max(p0[0], p1[0]), max(p0[1], p1[1]))
        return prism(g, base if base is not None else top,
                     (base if base is not None else top) + h)

    # 40-pin GPIO header
    m += blk(S.PI_HDR_CX - S.PI_HDR_L / 2, S.PI_HDR_CY - S.PI_HDR_W / 2,
             S.PI_HDR_CX + S.PI_HDR_L / 2, S.PI_HDR_CY + S.PI_HDR_W / 2,
             S.PI_HDR_H)
    # Right edge: Ethernet (Z=13.5) then the two USB stacks (Z=16.0 each)
    for cy, w, h in ((S.PI_ETH_CY, S.PI_ETH_W, S.PI_ETH_H),
                     (S.PI_USB3_CY, S.PI_USB_W, S.PI_USB_H),
                     (S.PI_USB2_CY, S.PI_USB_W, S.PI_USB_H)):
        m += blk(S.PI_L - 17.5, cy - w / 2,
                 S.PI_L + S.PI_PORT_PROUD, cy + w / 2, h)
    # Bottom edge: USB-C (Z=3.2), 2x micro-HDMI (Z=3.0), A/V jack (Z=6.0)
    m += blk(S.PI_USBC_CX - 4.5, -1.4, S.PI_USBC_CX + 4.5, 6.0, S.PI_USBC_H)
    for cx in (S.PI_HDMI0_CX, S.PI_HDMI1_CX):
        m += blk(cx - 3.6, -1.2, cx + 3.6, 5.5, S.PI_HDMI_H)
    m += blk(S.PI_AV_CX - 3.2, -2.0, S.PI_AV_CX + 3.2, 5.0, S.PI_AV_H)
    # CSI camera FFC connector, Z=5.5
    m += blk(S.PI_CSI_CX - 1.2, 12.0, S.PI_CSI_CX + 1.2, 34.0, 5.5)
    # SoC (Z=2.4) and RAM, so the viewer reads as a Pi
    m += blk(29.0, 22.0, 44.0, 37.0, S.PI_SOC_H)
    # microSD (Z=5.5), underside at the x=0 edge
    m += blk(-2.0, S.PI_SD_CY - S.PI_SD_W / 2, 12.0, S.PI_SD_CY + S.PI_SD_W / 2,
             S.PI_SD_H, base=z - S.PI_SD_H)
    return m


# --------------------------------------------------------------------------
# sensors
# --------------------------------------------------------------------------

def as7341():
    """Breakout on the sensor deck, chip DOWN over the relief shaft.
    Long axis along X -- that orientation is load-bearing, see audit."""
    z = S.HEAD_TOP + P.DECK_T
    m = Mesh()
    board = pl.affinity.translate(
        rounded_rect(S.AS_PCB_L, S.AS_PCB_W, 2.0), S.RS_X, S.RS_Y)
    holes = unary_union([circle(S.AS_HOLE_D, 20,
                                S.RS_X + sx * S.AS_HOLE_DX / 2,
                                S.RS_Y + sy * S.AS_HOLE_DY / 2)
                         for sx in (-1, 1) for sy in (-1, 1)])
    m += prism(board.difference(holes), z, z + S.AS_PCB_T)
    # the sensor package itself, looking down the shaft
    m += prism(circle(3.0, 24, S.RS_X, S.RS_Y), z - 1.0, z)
    return m


def camera():
    return BD.camera_body()


def laser():
    return BD.laser_body()


def leds():
    out = Mesh()
    for nm in ("led1", "led2", "ir"):
        out += BD.led_body(nm)
    return out


def oled():
    z = S.ENV_Z - S.CEIL - P.OLED_POST_H - S.OLED_PCB_T
    m = Mesh()
    board = pl.affinity.translate(
        rounded_rect(S.OLED_PCB_L, S.OLED_PCB_W, 2.0), S.OLED_CX, S.OLED_CY)
    holes = unary_union([circle(S.OLED_HOLE_D, 20,
                                S.OLED_CX + sx * S.OLED_HOLE_DX / 2,
                                S.OLED_CY + sy * S.OLED_HOLE_DY / 2)
                         for sx in (-1, 1) for sy in (-1, 1)])
    m += prism(board.difference(holes), z, z + S.OLED_PCB_T)
    glass = pl.affinity.translate(
        box(-S.OLED_GLASS_L / 2, -S.OLED_GLASS_W / 2,
            S.OLED_GLASS_L / 2, S.OLED_GLASS_W / 2),
        S.OLED_CX, S.OLED_CY + S.OLED_ACTIVE_OFF_Y)
    m += prism(glass, z + S.OLED_PCB_T, z + S.OLED_PCB_T + 1.5)
    return m


def ring_window():
    z = S.ENV_Z - P.FINGER_WELL_DEPTH
    return prism(circle(S.RING_WINDOW_D, 48, S.RS_X, S.RS_Y),
                 z, z + S.RING_WINDOW_T)


def cartridge_in_place():
    """A sample cartridge inserted to STOP2 -- the well under the aperture.

    Modelled tip-at-y=0 running +y, so it drops straight in: the tip points
    +Y (inward) and the grip trails out through the front face. At STOP2 the
    tip is STOP2 mm past the outer front face, which puts the well, WELL_FROM_TIP
    behind the tip, exactly on the read spot.
    """
    y_tip = -S.ENV_Y / 2 + S.STOP2
    m = P.cartridge_sample()
    m.rotate_z(180.0)          # body now runs -y from the tip, i.e. outward
    return m.translate(0.0, y_tip, S.SLOT_Z0)


# Cartridge-present microswitch, beside the cartridge channel.
#
# Long axis along Y. A 20 mm body laid across X does not fit between the Ø52
# head and the inner wall at 43.6, and every azimuth that clears the head runs
# into one of the corner bosses. Turned 90 degrees it drops into the gap
# between the head, the boss at (38, -58) and the front wall.
# 34, not 32: at 32 it sat exactly MIN_CLEAR from the camera board, which
# reaches r = 26.6 at azimuth 0 on its way out of the head.
SWITCH_CX, SWITCH_CY = 34.0, -44.0


def switch():
    g = box(SWITCH_CX - S.SWITCH_W / 2, SWITCH_CY - S.SWITCH_L / 2,
            SWITCH_CX + S.SWITCH_W / 2, SWITCH_CY + S.SWITCH_L / 2)
    return prism(g, S.FLOOR, S.FLOOR + S.SWITCH_H)


MOCKS = {
    "mock_pi4b": (pi4b, "#1E6B4E", 1.0),
    "mock_as7341": (as7341, "#2B6CB0", 1.0),
    "mock_camera": (camera, "#3B4A5A", 1.0),
    "mock_laser": (laser, "#B04A4A", 1.0),
    "mock_leds": (leds, "#E8E4D0", 1.0),
    "mock_oled": (oled, "#1A2A3A", 1.0),
    "mock_ring_window": (ring_window, "#9FD8E8", 0.45),
    "mock_switch": (switch, "#6B6B6B", 1.0),
    "mock_cartridge": (cartridge_in_place, "#EDF1F5", 1.0),
}
