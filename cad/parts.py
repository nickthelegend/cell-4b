"""CELL-4B printable parts. Every part is a watertight mesh in case coords.

Print orientations are set here (parts are modelled where they ASSEMBLE, and
`build.py` lays them flat on plates), so `assembly()` and the plates come from
one source and cannot drift.
"""
from __future__ import annotations

import math

from shapely.geometry import box
from shapely.ops import unary_union

import bodies as BD
import partlib as pl
from partlib import Bore, Mesh, circle, ellipse, layered, prism, rounded_rect
import spec as S


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _bores():
    """The five optical bores as partlib.Bore, axes through the read spot."""
    out = {}
    for name, d, tilt, az in S.OPTICAL_BORES:
        out[name] = Bore(d, S.RS_X, S.RS_Y, S.Z_SAMPLE, tilt_deg=tilt, az_deg=az)
    return out


def _cart_channel(pad=0.0):
    """The corridor the cartridge sweeps, in XY, from the front face inward."""
    w = S.CART_W + 2 * S.FIT + 2 * pad
    return box(-w / 2, -S.ENV_Y / 2 - 1, w / 2, S.RS_Y + S.CART_L - S.TRAVEL + 2)


def lap_lower():
    """Lower shell's tongue: the inner LAP_INNER band of the wall.

    The wall spans inset 0 (outer face) to inset WALL (inner face). The tongue
    is the band from inset (WALL - LAP_INNER) to inset WALL, so it is exactly
    LAP_INNER thick and sits against the inner face.
    """
    return _env(S.WALL - S.LAP_INNER).difference(_env(S.WALL))


def lap_upper():
    """Upper shell over the lap: the outer band, clear of the tongue."""
    return _env().difference(_env(S.WALL - S.LAP_INNER - S.LAP_FIT))


def _screw_column(x, y, od, hole_d, z0, z1, hz0=None, hz1=None):
    """Boss with an axial hole. Returns a Mesh."""
    hz0 = z0 if hz0 is None else hz0
    hz1 = z1 if hz1 is None else hz1
    m = prism(circle(od, 40, x, y).difference(circle(hole_d, 32, x, y)), z0, z1)
    if hz0 > z0:
        m += prism(circle(hole_d, 32, x, y), z0, hz0)
    if hz1 < z1:
        m += prism(circle(hole_d, 32, x, y), hz1, z1)
    return m


# --------------------------------------------------------------------------
# cartridge family  --  upstream CELL BUILD.md section 8, unchanged
# --------------------------------------------------------------------------

def cartridge(kind="sample"):
    """51 x 14 x 2.4. Well-side up, no supports, ironing ON.

    Modelled in its own frame: tip at y=0, body running +y, top face at z=T.
    kind: "sample" (well + moat), "reference" (well only), "null" (neither).
    """
    body = box(-S.CART_W / 2, 0.0, S.CART_W / 2, S.CART_L)
    m = Mesh()
    wy = S.WELL_FROM_TIP
    well = circle(S.WELL_D, 64, 0.0, wy)
    moat = circle(S.MOAT_D, 64, 0.0, wy)
    z_well = S.CART_T - S.WELL_DEPTH        # 1.85, well floor
    z_moat = S.CART_T - S.MOAT_DEPTH        # 2.00, moat floor

    if kind == "null":
        # no well, no moat -- must fail Gate 1 on the BRIGHT side
        m += prism(body, 0.0, S.CART_T)
    elif kind == "reference":
        # well only, sealed with a known target; no moat
        m += prism(body, 0.0, z_well)
        m += prism(body.difference(well), z_well, S.CART_T)
    else:
        # solid up to the well floor
        m += prism(body, 0.0, z_well)
        # between the well floor and the moat floor only the well is open
        m += prism(body.difference(well), z_well, z_moat)
        # above the moat floor the whole Ø7 is open (well + annulus)
        m += prism(body.difference(moat), z_moat, S.CART_T)

    # grip tab, proud of the slot so it is the insertion stop
    grip = box(-S.CART_W / 2, S.STOP2, S.CART_W / 2, S.CART_L)
    m += prism(grip, S.CART_T, S.GRIP_T)

    # first-stop detent ridge, rides over on a deliberate push
    det = box(-S.CART_W / 2, S.STOP1 - S.DETENT_L / 2,
              S.CART_W / 2, S.STOP1 + S.DETENT_L / 2)
    m += prism(det, S.CART_T, S.CART_T + S.DETENT_PROUD)
    return m


def cartridge_sample():
    return cartridge("sample")


def cartridge_reference():
    return cartridge("reference")


def cartridge_null():
    return cartridge("null")


# --------------------------------------------------------------------------
# aperture tube  --  Ø3 x 6 bore. Print FLANGE DOWN.
# --------------------------------------------------------------------------

APT_FLANGE_D, APT_FLANGE_T = 10.0, 1.0
APT_BARREL_D = 6.0
APT_FLANGE_BORE = 5.0          # wider than the aperture, so only the barrel
#                                bore's 6.0 mm sets the acceptance cone


def aperture_tube():
    m = Mesh()
    m += prism(circle(APT_FLANGE_D, 64).difference(circle(APT_FLANGE_BORE, 48)),
               0.0, APT_FLANGE_T)
    m += prism(circle(APT_BARREL_D, 48).difference(circle(S.APERTURE_BORE, 40)),
               APT_FLANGE_T, APT_FLANGE_T + S.APERTURE_LEN)
    return m


# --------------------------------------------------------------------------
# optical head  --  the light-tight chamber. THE precision part.
# --------------------------------------------------------------------------

HEAD_SKIRT_Z = S.Z_SAMPLE + 0.20      # skirt reaches to 0.2 above the window
# Posts must clear TWO things: the skirt (inner radius (HEAD_DIA-6)/2 = 19.0)
# and the cartridge channel. OD 6.4 at r=15 reaches r=18.2, inside the skirt;
# azimuths at 30 deg off the X axis put them at |x| = 13.0, clear of the
# 7.3 mm channel plus a post radius.
HEAD_POST_R = 15.0
HEAD_POST_AZ = [30.0, 150.0, 210.0, 330.0]
Z_TUBE_TOP = S.Z_SAMPLE + 9.0         # top of the Ø3 x 6 aperture tube


def head_posts_xy():
    return [S.polar(HEAD_POST_R, a) for a in HEAD_POST_AZ]


def optical_head():
    """One solid Ø52 block, 6.2 -> 33.4, carrying all five optical paths.

    The five bores all aim at the read spot, so near the axis they merge --
    that merged volume IS the optical chamber (radius CHAMBER_R), not a
    missing wall. Outside it audit.check_bore_separation() holds every pair to
    MIN_WALL.

    Exits, all forced by the angles:
      * three 45 deg LED bores leave through the SIDE wall at z = 31.4
      * the 58 deg speckle bore leaves through the SIDE wall at z = 21.6
      * the 30 deg laser bore is the only one that leaves through the TOP,
        at r = 16.2, which clears the AS7341's 11.5 mm half-width at az 270
    """
    b = _bores()
    disc = circle(S.HEAD_DIA, 120, S.RS_X, S.RS_Y)
    tube_clear = circle(APT_BARREL_D + 2 * 0.2, 48, S.RS_X, S.RS_Y)
    tube_cbore = circle(APT_FLANGE_D + 2 * 0.2, 64, S.RS_X, S.RS_Y)
    shaft = circle(S.SHAFT_D, 48, S.RS_X, S.RS_Y)
    mount = unary_union([circle(S.M25_TAP, 24, x, y) for x, y in head_posts_xy()])
    names = ["led1", "led2", "ir", "laser", "camera"]

    pockets = BD.head_pockets()

    def profile(z):
        g = disc
        for n in names:
            g = g.difference(b[n].section(z))
        # drop-in pockets for the laser barrel and the camera board, both of
        # which are wider than the bore that carries their light. Derived from
        # bodies.py, so they cannot drift from the parts they clear.
        for prof, pz0, pz1 in pockets:
            if pz0 <= z <= pz1:
                g = g.difference(prof)
        # central column: tube bore, then its flange counterbore, then the
        # relief shaft. The Ø3 x 6 tube stays the limiting aperture.
        if z < Z_TUBE_TOP - APT_FLANGE_T:
            g = g.difference(tube_clear)
        elif z < Z_TUBE_TOP:
            g = g.difference(tube_cbore)
        else:
            g = g.difference(shaft)
        return g.difference(mount)

    m = Mesh()
    # skirt: closes the 0.8 mm gap over the cartridge everywhere except the
    # corridor the cartridge itself sweeps.
    skirt = disc.difference(circle(S.HEAD_DIA - 6.0, 120, S.RS_X, S.RS_Y)
                            ).difference(_cart_channel(pad=0.15))
    m += prism(skirt, HEAD_SKIRT_Z, S.HEAD_Z0)
    m += layered(profile, S.HEAD_Z0, S.HEAD_TOP, dz=0.35)
    return m


def sensor_deck():
    """Caps the head at Z_SENSOR and carries the AS7341. Separate part so the
    LEDs, laser and camera can all be fitted before it goes on."""
    plate = circle(S.HEAD_DIA, 160)
    shaft = circle(S.SHAFT_D, 48)
    holes = unary_union([circle(S.M2_CLEAR, 24,
                                sx * S.AS_HOLE_DX / 2, sy * S.AS_HOLE_DY / 2)
                         for sx in (-1, 1) for sy in (-1, 1)])
    posts = unary_union([circle(S.M25_CLEAR, 24,
                                HEAD_POST_R * math.cos(math.radians(a)),
                                HEAD_POST_R * math.sin(math.radians(a)))
                         for a in HEAD_POST_AZ])
    # the laser is the one bore that exits the top face -- the deck must not
    # cap it. Its exit ellipse at HEAD_TOP, with clearance.
    # sized off the BARREL, not the light bore, with MIN_CLEAR each side
    b = Bore(S.LASER_BODY_D + 2 * 1.2, 0.0, 0.0, 0.0,
             tilt_deg=S.LASER_ANGLE, az_deg=S.AZ_LASER)
    laser_exit = b.section(S.HEAD_TOP - S.Z_SAMPLE)
    cut = unary_union([shaft, holes, posts, laser_exit])
    return prism(plate.difference(cut), 0.0, 2.4)


# --------------------------------------------------------------------------
# slot baffle  --  light trap behind the front flap
# --------------------------------------------------------------------------

def slot_baffle():
    """Light trap behind the front mouth.

    It stops BELOW the optical head's skirt. The skirt closes the chamber from
    HEAD_SKIRT_Z up; the baffle closes the slot from the floor to just under
    it. Together they are light-tight, and neither fouls the other -- a baffle
    tall enough to look sensible on its own drives straight into the skirt.
    """
    import mocks_geom as MG
    w = S.SLOT_W + 2.0
    outer = box(-w / 2, -1.2, w / 2, 1.2)
    gap = box(-(S.CART_W + 2 * S.FIT) / 2, -2, (S.CART_W + 2 * S.FIT) / 2, 2)
    # notch for the cartridge switch. The switch body fills the notch, so the
    # baffle stays light-tight -- an open notch here would let the slot leak.
    notch = MG.switch_footprint(0.9)      # > MIN_CLEAR, so it is a fit not a rub
    prof = outer.difference(gap).difference(
        pl.affinity.translate(notch, 0.0, -(-S.ENV_Y / 2 + S.WALL
                                            + S.BAFFLE_OFFSET)))
    return prism(prof, 0.0, HEAD_SKIRT_Z - S.SLOT_Z0 - 1.0)


# --------------------------------------------------------------------------
# window jig  --  cutting template for the 12 x 10 PET windows
# --------------------------------------------------------------------------

def window_jig():
    plate = rounded_rect(60.0, 42.0, 3.0)
    cuts = []
    for i in range(2):
        for j in range(2):
            cuts.append(box(-26 + i * 28, -17 + j * 22,
                            -26 + i * 28 + S.WINDOW_L, -17 + j * 22 + S.WINDOW_W))
    return prism(plate.difference(unary_union(cuts)), 0.0, 3.0)


# --------------------------------------------------------------------------
# lower shell
# --------------------------------------------------------------------------

def _env(inset=0.0):
    return rounded_rect(S.ENV_X - 2 * inset, S.ENV_Y - 2 * inset,
                        max(0.6, S.CORNER_R - inset), seg=14)


def shell_lower():
    outer = _env()
    inner = _env(S.WALL)
    m = Mesh()

    # --- floor -------------------------------------------------------------
    m += prism(outer, 0.0, S.FLOOR)

    # --- walls, with the port windows and the cartridge slot cut out -------
    def wall_profile(z):
        g = outer.difference(inner)
        cuts = []
        # front cartridge slot (mouth 34 wide) + the guide channel behind it
        if S.SLOT_Z0 <= z <= S.SLOT_Z1:
            cuts.append(box(-S.SLOT_W / 2, -S.ENV_Y / 2 - 1,
                            S.SLOT_W / 2, -S.ENV_Y / 2 + S.WALL + 1))
            cuts.append(_cart_channel(pad=0.15))
        # back wall: USB-C / micro-HDMI x2 / A-V
        if S.PI_PCB_Z <= z <= S.PI_PCB_Z + S.PI_PCB_T + S.PI_PORTS_Y0_H:
            x0, _ = S.pi_to_case(S.PI_PORTS_Y0[1], 0.0)
            x1, _ = S.pi_to_case(S.PI_PORTS_Y0[0], 0.0)
            cuts.append(box(x0, S.ENV_Y / 2 - S.WALL - 1, x1, S.ENV_Y / 2 + 1))
        # left wall: Ethernet + 4x USB
        if S.PI_PCB_Z <= z <= S.PI_PCB_Z + S.PI_PCB_T + S.PI_USB_H:
            _, y0 = S.pi_to_case(0.0, S.PI_PORTS_X85[1])
            _, y1 = S.pi_to_case(0.0, S.PI_PORTS_X85[0])
            cuts.append(box(-S.ENV_X / 2 - 1, y0, -S.ENV_X / 2 + S.WALL + 1, y1))
        # right wall: microSD, on the board underside
        if S.FLOOR - 0.5 <= z <= S.PI_PCB_Z + S.PI_PCB_T + 0.5:
            _, cy = S.pi_to_case(0.0, S.PI_SD_CY)
            cuts.append(box(S.ENV_X / 2 - S.WALL - 1, cy - S.PI_SD_W / 2,
                            S.ENV_X / 2 + 1, cy + S.PI_SD_W / 2))
        if cuts:
            g = g.difference(unary_union(cuts))
        return g

    m += layered(wall_profile, S.FLOOR, S.PART_LINE_Z, dz=0.5)

    # --- lap joint: the lower shell's tongue is the INNER LAP_INNER of the
    # wall, so nothing at the joint is thinner than LAP_INNER.
    m += prism(lap_lower(), S.PART_LINE_Z, S.PART_LINE_Z + S.LAP_H)

    # --- Pi standoffs ------------------------------------------------------
    # Ø6 boss with a Ø2.2 tap hole straight through it, bottoming on the top
    # face of the floor: a BLIND hole PI_STANDOFF deep, which is 4 mm of
    # thread engagement for an M2.5 self-tapper. The floor underneath stays
    # solid -- there is no such thing as "extending the pilot hole downward"
    # in a kernel with no CSG, and adding a cylinder there just puts four
    # spikes on the underside of the case.
    for x, y in S.pi_holes():
        m += _screw_column(x, y, 6.0, S.M25_TAP, S.FLOOR, S.PI_PCB_Z)

    # --- optical head posts ------------------------------------------------
    for x, y in head_posts_xy():
        m += _screw_column(x, y, 6.4, S.M25_TAP, S.FLOOR, S.HEAD_Z0)

    # --- cartridge channel floor rails ------------------------------------
    rail_w = 2.0
    for sx in (-1, 1):
        gx = sx * ((S.CART_W + 2 * S.FIT) / 2 + rail_w / 2)
        m += prism(box(gx - rail_w / 2, S.RS_Y - 26, gx + rail_w / 2, -S.ENV_Y / 2 + S.WALL),
                   S.FLOOR, S.SLOT_Z0)
    m += prism(box(-(S.CART_W + 2 * S.FIT) / 2, S.RS_Y - 26,
                   (S.CART_W + 2 * S.FIT) / 2, -S.ENV_Y / 2 + S.WALL),
               S.FLOOR, S.SLOT_Z0)

    # --- corner screw bosses ----------------------------------------------
    for x, y in S.BOSS_XY:
        m += _screw_column(x, y, S.BOSS_OD, S.HEATSET_D,
                           S.FLOOR, S.PART_LINE_Z,
                           hz0=S.PART_LINE_Z - S.HEATSET_L)
    return m


# --------------------------------------------------------------------------
# upper shell
# --------------------------------------------------------------------------

FINGER_WELL_D = 14.0
FINGER_WELL_DEPTH = 2.0                     # from the top face
OLED_POST_H = 3.4                           # ceiling underside to PCB top
BEZEL_T = 1.2                               # bezel sits in a top-face recess


def shell_upper():
    """Z 18 -> 34. Ceiling carries the dish, the ring, the finger well and
    the OLED window. Every ceiling feature is a BLIND pocket except the OLED
    active window and the ring bore -- see audit.check_light_tight()."""
    outer = _env()
    inner = _env(S.WALL)
    z0, z1 = S.PART_LINE_Z, S.ENV_Z
    ceil0 = z1 - S.CEIL                       # 31.6, inner face of the ceiling
    z_dish = z1 - S.DISH_DEPTH                # 32.4, dish floor
    z_finger = z1 - FINGER_WELL_DEPTH         # 32.0, ring-window seat
    z_bezel = z1 - BEZEL_T                    # 32.8, bezel recess floor
    m = Mesh()

    # --- wall. Over the lap the upper shell keeps only the OUTER band, so
    # the lower shell's tongue slides inside it with LAP_FIT of clearance.
    wall_ring = outer.difference(inner)
    m += prism(lap_upper(), z0, z0 + S.LAP_H)
    m += prism(wall_ring, z0 + S.LAP_H, ceil0)

    # --- ceiling features, as XY profiles --------------------------------
    dish = circle(S.DISH_D, 128, S.RS_X, S.RS_Y)
    ring_bore = circle(S.RING_WINDOW_D, 64, S.RS_X, S.RS_Y)      # through
    finger = circle(FINGER_WELL_D, 64, S.RS_X, S.RS_Y)           # blind, 2.0
    oled_win = box(S.OLED_CX - S.OLED_ACTIVE_L / 2 - 0.6,
                   S.OLED_CY + S.OLED_ACTIVE_OFF_Y - S.OLED_ACTIVE_W / 2 - 0.6,
                   S.OLED_CX + S.OLED_ACTIVE_L / 2 + 0.6,
                   S.OLED_CY + S.OLED_ACTIVE_OFF_Y + S.OLED_ACTIVE_W / 2 + 0.6)
    bezel_recess = pl.affinity.translate(
        rounded_rect(S.OLED_PCB_L + 3.0 + 2 * S.FIT,
                     S.OLED_PCB_W + 3.0 + 2 * S.FIT, 2.5), S.OLED_CX, S.OLED_CY)

    # blind vents, cut from the TOP face only, VENT_DEPTH deep
    vents = []
    for i in range(6):
        for sx in (-1, 1):
            x = sx * (S.ENV_X / 2 - 7.0 - i * 4.0)
            vents.append(box(min(x, x - S.VENT_W), S.OLED_CY - 24.0,
                             max(x, x - S.VENT_W) + S.VENT_W,
                             S.OLED_CY - 24.0 + S.VENT_L))
    vent_g = unary_union(vents).intersection(inner.buffer(-1.0))

    ticks = []
    for i in range(S.TICKS):
        r0, r1 = S.DISH_D / 2 - 3.2, S.DISH_D / 2 - 1.2
        t = pl.affinity.rotate(box(r0, -0.35, r1, 0.35),
                               i * 360.0 / S.TICKS, origin=(0, 0))
        ticks.append(pl.affinity.translate(t, S.RS_X, S.RS_Y))
    tick_g = unary_union(ticks).intersection(dish.buffer(-0.8))

    # --- ceiling, built as bands from the inner face up ------------------
    # The finger well is DEEPER than the dish, so the band order from the
    # inside face out is: ceil0 < z_finger < z_dish < z_bezel < z1.
    assert ceil0 < z_finger < z_dish < z_bezel < z1, "ceiling bands out of order"

    # ceil0 -> z_finger : solid; only the Ø10 ring bore and the OLED window
    # are open. The ring bore's top lip at z_finger is the window seat.
    m += prism(inner.difference(ring_bore).difference(oled_win), ceil0, z_finger)
    # z_finger -> z_dish : the Ø14 finger well is open (it bottoms here)
    m += prism(inner.difference(finger).difference(oled_win), z_finger, z_dish)
    # z_dish -> z_bezel : the dish recess opens (the finger well is inside it)
    m += prism(inner.difference(dish).difference(oled_win), z_dish, z_bezel)
    # z_bezel -> z1 : the bezel recess and the blind vents open at the top face
    m += prism(inner.difference(dish).difference(bezel_recess)
               .difference(vent_g), z_bezel, z1)
    # tick ridges standing proud of the dish floor
    m += prism(tick_g.difference(finger), z_dish, z_dish + 0.4)
    # the ring: a collar around the finger well, standing on the dish floor
    m += prism(circle(S.RING_OD, 64, S.RS_X, S.RS_Y).difference(finger),
               z_dish, z_bezel)

    # --- OLED posts: PCB hangs under the ceiling, glass up to the window --
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = S.OLED_CX + sx * S.OLED_HOLE_DX / 2
            y = S.OLED_CY + sy * S.OLED_HOLE_DY / 2
            m += _screw_column(x, y, 5.0, S.M2_TAP, ceil0 - OLED_POST_H, ceil0)

    # --- corner screw counterbores ----------------------------------------
    for x, y in S.BOSS_XY:
        m += _screw_column(x, y, S.BOSS_OD, S.M25_CLEAR, z0, ceil0)
        m += prism(circle(S.M25_HEAD, 32, x, y).difference(
            circle(S.M25_CLEAR, 24, x, y)), ceil0, ceil0 + 2.0)
    return m


# --------------------------------------------------------------------------
# OLED bezel  --  masks the window down to the active area
# --------------------------------------------------------------------------

def oled_bezel():
    frame = rounded_rect(S.OLED_PCB_L + 3.0, S.OLED_PCB_W + 3.0, 2.5)
    ap = box(-S.OLED_ACTIVE_L / 2, S.OLED_ACTIVE_OFF_Y - S.OLED_ACTIVE_W / 2,
             S.OLED_ACTIVE_L / 2, S.OLED_ACTIVE_OFF_Y + S.OLED_ACTIVE_W / 2)
    holes = unary_union([circle(S.M2_CLEAR, 24,
                                sx * S.OLED_HOLE_DX / 2, sy * S.OLED_HOLE_DY / 2)
                         for sx in (-1, 1) for sy in (-1, 1)])
    return prism(frame.difference(ap).difference(holes), 0.0, BEZEL_T)


# --------------------------------------------------------------------------
# sensor carrier  --  AS7341 board, seats chip-DOWN (blood) or chip-UP (touch)
# --------------------------------------------------------------------------

CARRIER_T = 1.8


def sensor_carrier():
    """Retainer that clamps the AS7341 down onto the sensor deck. It sits ON
    TOP of the board, so it must be thin enough to stay under the ceiling."""
    frame = rounded_rect(S.AS_PCB_L + 5.0, S.AS_PCB_W + 5.0, 2.0)
    window = rounded_rect(S.AS_PCB_L - 6.0, S.AS_PCB_W - 6.0, 1.0)
    holes = unary_union([circle(S.M2_CLEAR, 24,
                                sx * S.AS_HOLE_DX / 2, sy * S.AS_HOLE_DY / 2)
                         for sx in (-1, 1) for sy in (-1, 1)])
    return prism(frame.difference(window).difference(holes), 0.0, CARRIER_T)


PARTS = {
    "cartridge": (cartridge_sample, "#E9EDF2", 20),
    "cartridge_reference": (cartridge_reference, "#E9EDF2", 1),
    "cartridge_null": (cartridge_null, "#E9EDF2", 1),
    "aperture_tube": (aperture_tube, "#2E3238", 1),
    "optical_head": (optical_head, "#2E3238", 1),
    "sensor_deck": (sensor_deck, "#2E3238", 1),
    "slot_baffle": (slot_baffle, "#2E3238", 1),
    "window_jig": (window_jig, "#8A9099", 1),
    "shell_lower": (shell_lower, "#3A3F46", 1),
    "shell_upper": (shell_upper, "#3A3F46", 1),
    "oled_bezel": (oled_bezel, "#2E3238", 1),
    "sensor_carrier": (sensor_carrier, "#2E3238", 1),
}


# --------------------------------------------------------------------------
# placement
#
# Some parts are modelled in their own frame because that is the frame they
# are DIMENSIONED in (a cartridge is 51 mm from its own tip; an aperture tube
# is a tube). `place()` is the single source of truth for where each one
# actually goes, so the clearance audit and the viewer see a real assembly
# rather than a pile of parts at the origin.
# --------------------------------------------------------------------------

Z_TUBE_FLANGE_TOP = Z_TUBE_TOP            # 14.4; flange sits in the counterbore
DECK_T = 2.4


def place(name, mesh):
    m = mesh.copy()
    if name == "aperture_tube":
        # modelled flange-down for printing; assembles flange-UP in the head's
        # counterbore, barrel hanging into the bore below it.
        m.rotate_x(180.0, about=(0.0, 0.0))
        return m.translate(S.RS_X, S.RS_Y, Z_TUBE_FLANGE_TOP)
    if name == "sensor_deck":
        return m.translate(S.RS_X, S.RS_Y, S.HEAD_TOP)
    if name == "sensor_carrier":
        return m.translate(S.RS_X, S.RS_Y, S.HEAD_TOP + DECK_T + S.AS_PCB_T)
    if name == "oled_bezel":
        return m.translate(S.OLED_CX, S.OLED_CY, S.ENV_Z - BEZEL_T)
    if name == "slot_baffle":
        return m.translate(0.0, -S.ENV_Y / 2 + S.WALL + S.BAFFLE_OFFSET,
                           S.SLOT_Z0)
    return m                                   # already in case coordinates


# parts that are consumables / tools, not part of the assembled instrument
LOOSE = {"cartridge", "cartridge_reference", "cartridge_null", "window_jig"}


def assembly():
    """Every printed part of the instrument, placed."""
    return {n: place(n, fn()) for n, (fn, _c, _q) in PARTS.items()
            if n not in LOOSE}
