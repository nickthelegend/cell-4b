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
# Cartridge-present switch. It has to be ACTUATED BY THE CARTRIDGE, which is
# only exposed inside the case in the strip between the inner front wall and
# the optical head. Everywhere else the head is over it.
#
# Its lever reaches into the cartridge channel; the body sits beside the slot
# mouth. audit.check_switch_senses_cartridge() asserts the lever actually
# overlaps the channel -- a switch that fits perfectly but cannot be pressed is
# the failure this whole design is meant to avoid.
import mocks_geom as MG

SWITCH_CX, SWITCH_CY = MG.SWITCH_CX, MG.SWITCH_CY


def switch():
    m = prism(MG.switch_footprint(), S.FLOOR, S.FLOOR + S.SWITCH_H)
    # The lever is drawn DEPRESSED -- resting on the channel wall -- because
    # the mock cartridge is inserted. Its FREE position protrudes
    # SWITCH_FREE_TRAVEL further in; that is what actually gets pressed, and
    # audit.check_function() asserts it.
    hw = (S.CART_W + 2 * S.FIT) / 2
    # from the channel wall on the switch's side, out to the body's inner face
    x_chan = MG.SWITCH_SIDE * hw
    x_body = MG.SWITCH_CX - MG.SWITCH_SIDE * S.SWITCH_L / 2
    lev = box(min(x_chan, x_body), SWITCH_CY - 1.0,
              max(x_chan, x_body), SWITCH_CY + 1.0)
    m += prism(lev, S.SLOT_Z0 + 0.4, S.SLOT_Z0 + 1.8)
    return m


def csi_ribbon():
    """The CSI ribbon, swept along CABLE_ROUTE so you can SEE where it goes.

    Built as a chain of thin slabs, each oriented to that segment's 'h' / 'v'
    flag -- the same orientation the corridor check uses, so what you see is
    what was verified.
    """
    import numpy as np
    m = Mesh()
    half, halft = S.CABLE_W / 2, S.CABLE_T / 2 + 0.3
    for wa, wb in zip(S.CABLE_ROUTE, S.CABLE_ROUTE[1:]):
        a, b = np.array(wa[:3], float), np.array(wb[:3], float)
        seg = float(np.linalg.norm(b - a))
        if seg < 1e-6:
            continue
        d = (b - a) / seg
        if wa[3] == 'v':
            w = np.array([0.0, 0.0, 1.0]) - d * float(np.dot([0, 0, 1.0], d))
        else:
            w = np.cross(d, [0.0, 0.0, 1.0])
            if np.linalg.norm(w) < 1e-6:
                w = np.cross(d, [1.0, 0.0, 0.0])
        if np.linalg.norm(w) < 1e-6:
            continue
        w /= np.linalg.norm(w)
        t = np.cross(d, w)
        t /= (np.linalg.norm(t) or 1.0)
        # eight corners of the slab -> one closed shell
        quad = [(+half, +halft), (+half, -halft), (-half, -halft), (-half, +halft)]
        ring0 = [a + u * w + v * t for u, v in quad]
        ring1 = [b + u * w + v * t for u, v in quad]
        sh = Mesh(weld=True)
        idx0 = [sh._pt(*p) for p in ring0]
        idx1 = [sh._pt(*p) for p in ring1]
        for i in range(4):
            j = (i + 1) % 4
            sh.F.append((idx0[i], idx0[j], idx1[j]))
            sh.F.append((idx0[i], idx1[j], idx1[i]))
        sh.F.append((idx0[0], idx0[2], idx0[1]))
        sh.F.append((idx0[0], idx0[3], idx0[2]))
        sh.F.append((idx1[0], idx1[1], idx1[2]))
        sh.F.append((idx1[0], idx1[2], idx1[3]))
        # (w, t, d) can come out left-handed depending on the segment, which
        # inverts the shell. Flip the whole slab if its signed volume is
        # negative -- an inverted shell breaks every point-in-solid test.
        V = np.asarray(sh.V, float)
        vol = sum(float(np.dot(V[a_], np.cross(V[b_], V[c_]))) / 6.0
                  for a_, b_, c_ in sh.F)
        if vol < 0:
            sh.F = [(c_, b_, a_) for a_, b_, c_ in sh.F]
        m += sh
    return m


def touch_leds():
    """White + 940 nm IR in the touch collar, aimed UP at the fingertip.

    Same 45 deg / 12 mm illumination geometry as the blood tier -- the angle
    is what rejects specular return off skin, exactly as it does off wet blood
    -- just pointed the other way.
    """
    out = Mesh()
    for az in (S.AZ_TOUCH_W, S.AZ_TOUCH_IR):
        c = prism(circle(S.LED_BODY_D, 32),
                  S.LED_SLANT, S.LED_SLANT + S.LED_BODY_L)
        c.rotate_x(180.0 - S.LED_ANGLE)
        c.rotate_z(az - 270.0)
        out += c.translate(S.RS_X, S.RS_Y, S.TOUCH_SPOT_Z)
    return out


def touch_window():
    """Ø10 x 0.5 glass in the ceiling's rebate -- the finger's contact face."""
    z = S.ENV_Z - S.CEIL
    return prism(circle(S.RING_WINDOW_D, 48, S.RS_X, S.RS_Y),
                 z, z + S.RING_WINDOW_T)


MOCKS = {
    "mock_touch_leds": (touch_leds, "#E8E4D0", 1.0),
    "mock_touch_window": (touch_window, "#9FD8E8", 0.45),
    "mock_csi_ribbon": (csi_ribbon, "#C8A24A", 1.0),
    "mock_pi4b": (pi4b, "#1E6B4E", 1.0),
    "mock_as7341": (as7341, "#2B6CB0", 1.0),
    "mock_camera": (camera, "#3B4A5A", 1.0),
    "mock_laser": (laser, "#B04A4A", 1.0),
    "mock_leds": (leds, "#E8E4D0", 1.0),
    "mock_oled": (oled, "#1A2A3A", 1.0),
    "mock_switch": (switch, "#6B6B6B", 1.0),
    "mock_cartridge": (cartridge_in_place, "#EDF1F5", 1.0),
}
