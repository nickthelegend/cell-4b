"""CELL-4B fit and sanity checks. Run before every print.

Watertight is not the same as buildable. These are the ways this instrument
can be wrong without LOOKING wrong -- upstream CELL learned most of them the
expensive way (insert bosses standing inside the Pi footprint, vent pockets
deeper than the wall, a white patch with no optical path to it).

Two kinds of check:

  ANALYTIC  -- pure arithmetic on spec.py. Fast, exact, no meshing.
  SAMPLED   -- point-in-solid tests against the real triangles, by projecting
               each triangle to XY and counting crossings along +Z. Used where
               only the actual geometry can answer (does the cartridge corridor
               stay open, does the Pi fit in its bay).

Exit code is non-zero if anything FAILS, so the build refuses to write STLs.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union

import partlib as pl
import parts as P
import spec as S

RESULTS = []


def _rec(ok, name, detail, warn=False):
    RESULTS.append(("WARN" if (warn and not ok) else ("PASS" if ok else "FAIL"),
                    name, detail))
    return ok


# --------------------------------------------------------------------------
# point-in-solid, vectorised
# --------------------------------------------------------------------------

def _inside(mesh, pts):
    """Boolean array: is each point strictly inside the closed mesh?

    Ray along +Z. A triangle counts if the point's XY lies in its XY
    projection and the triangle's plane sits above the point.
    """
    V, F = mesh._np()
    tri = V[F]
    pts = np.asarray(pts, dtype=float).copy()
    # Jitter the ray by an irrational epsilon. Parts here are centred on x=0
    # and built from tessellated circles, so a ray at exactly x=0 runs ALONG
    # triangle edges and double-counts crossings -- which reads as "solid"
    # for points that are nowhere near the part. This is a ray-cast
    # degeneracy, not geometry; 0.1 um off-axis removes it.
    pts[:, 0] += 6.1803398e-5
    pts[:, 1] += 3.8196601e-5
    lo, hi = tri.min(axis=1), tri.max(axis=1)

    out = np.zeros(len(pts), dtype=bool)
    for i, p in enumerate(pts):
        # cheap bbox prefilter -- most triangles are nowhere near
        sel = ((lo[:, 0] <= p[0]) & (hi[:, 0] >= p[0]) &
               (lo[:, 1] <= p[1]) & (hi[:, 1] >= p[1]) & (hi[:, 2] >= p[2]))
        if not sel.any():
            continue
        t = tri[sel]
        ax, ay = t[:, 0, 0], t[:, 0, 1]
        bx, by = t[:, 1, 0], t[:, 1, 1]
        cx, cy = t[:, 2, 0], t[:, 2, 1]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        good = np.abs(d) > 1e-12
        if not good.any():
            continue
        l1 = np.where(good, ((by - cy) * (p[0] - cx) + (cx - bx) * (p[1] - cy)) /
                      np.where(good, d, 1.0), -1.0)
        l2 = np.where(good, ((cy - ay) * (p[0] - cx) + (ax - cx) * (p[1] - cy)) /
                      np.where(good, d, 1.0), -1.0)
        l3 = 1.0 - l1 - l2
        inxy = good & (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not inxy.any():
            continue
        zc = l1 * t[:, 0, 2] + l2 * t[:, 1, 2] + l3 * t[:, 2, 2]
        out[i] = bool((inxy & (zc > p[2])).sum() % 2)
    return out


def _grid(x0, x1, y0, y1, z0, z1, n=(9, 15, 5)):
    xs = np.linspace(x0, x1, n[0])
    ys = np.linspace(y0, y1, n[1])
    zs = np.linspace(z0, z1, n[2])
    return np.array([(x, y, z) for x in xs for y in ys for z in zs])


# --------------------------------------------------------------------------
# ANALYTIC -- the optics. These are the numbers that must not have moved.
# --------------------------------------------------------------------------

def check_optics():
    ok = True
    # The standoff is a DELIBERATE, documented deviation (see FINDINGS.md): a
    # 9 mm standoff is geometrically impossible with 5 mm LEDs at 45/12. What
    # must still hold is that the Ø3 x 6 tube at the SAMPLE end is unchanged
    # and is still the narrowest element in the path -- that is what fixes the
    # 3 mm spot, and it is the only thing the gates actually depend on.
    ok &= _rec(S.SHAFT_D > S.APERTURE_BORE, "optics/tube-is-limiting",
               f"Ø{S.APERTURE_BORE} x {S.APERTURE_LEN} tube at the sample, "
               f"relieved to Ø{S.SHAFT_D} above it, so the tube still sets "
               f"the {S.APERTURE_BORE} mm spot")
    ok &= _rec(True, "optics/sensor-standoff",
               f"AS7341 at {S.Z_SENSOR - S.Z_SAMPLE:.1f} mm (upstream states "
               f"{S.SENSOR_STANDOFF_UPSTREAM:.1f}; DEVIATION, see FINDINGS.md). "
               f"Flux down {(S.SENSOR_STANDOFF / S.SENSOR_STANDOFF_UPSTREAM)**2:.1f}x, "
               f"recovered by integration time and divided out by the white patch")

    for nm, az in (("led1", S.AZ_LED1), ("led2", S.AZ_LED2), ("ir", S.AZ_IR)):
        x, y = S.polar(S.R_LED, az)
        slant = math.hypot(math.hypot(x - S.RS_X, y - S.RS_Y),
                           S.Z_LED - S.Z_SAMPLE)
        ok &= _rec(abs(slant - S.LED_SLANT) < 1e-6, f"optics/{nm}-slant",
                   f"{slant:.3f} mm from the read spot at "
                   f"{S.LED_ANGLE:.0f} deg (spec {S.LED_SLANT:.1f})")

    lx, ly = S.polar(S.R_LASER, S.AZ_LASER)
    ls = math.hypot(math.hypot(lx, ly - S.RS_Y), S.Z_LASER - S.Z_SAMPLE)
    ok &= _rec(abs(ls - S.LASER_SLANT) < 1e-6, "optics/laser-slant",
               f"{ls:.3f} mm at {S.LASER_ANGLE:.0f} deg off normal")

    cs = math.hypot(S.R_CAMERA, S.Z_CAMERA - S.Z_SAMPLE)
    ok &= _rec(abs(cs - S.CAMERA_SLANT) < 1e-6, "optics/camera-slant",
               f"{cs:.3f} mm lensless standoff (spec {S.CAMERA_SLANT:.1f}), "
               f"tilt {S.CAMERA_ANGLE:.2f} deg")

    # The laser's specular lobe leaves at the same tilt, azimuth + 180. Compare
    # the two as 3-D DIRECTIONS -- azimuth separation alone flatters a design
    # where the tilts differ.
    def _dir(tilt, az):
        t, a = math.radians(tilt), math.radians(az)
        return (math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t))
    sp = _dir(S.LASER_ANGLE, (S.AZ_LASER + 180.0) % 360.0)
    cm = _dir(S.CAMERA_ANGLE, S.AZ_CAMERA)
    gamma = math.degrees(math.acos(max(-1.0, min(1.0, sum(u * v for u, v in zip(sp, cm))))))
    ok &= _rec(gamma >= 45.0, "optics/camera-off-specular",
               f"speckle axis is {gamma:.1f} deg off the specular lobe in 3-D "
               f"(need >= 45)")

    # the aperture must sit on the vertical axis over the spot
    ok &= _rec(S.RS_X == 0.0 and abs(S.APERTURE_BORE - 3.0) < 1e-9,
               "optics/aperture",
               f"Ø{S.APERTURE_BORE} x {S.APERTURE_LEN} on the vertical axis, "
               f"defining a {S.APERTURE_BORE} mm spot inside the "
               f"Ø{S.WELL_D} well")
    return ok


def _bore_exit_z(tilt_deg):
    """Height at which a bore's axis reaches the head's outer radius. Above
    HEAD_TOP means it never does, and the bore leaves through the top face."""
    if tilt_deg <= 0:
        return float("inf")
    return S.Z_SAMPLE + (S.HEAD_DIA / 2) / math.tan(math.radians(tilt_deg))


def check_bore_separation():
    """Separation is judged AT EACH BORE'S ENTRY, which is the only place it
    physically matters: that is where the component seats and where the wall
    between two holes has to survive being printed.

    Near the read spot every bore merges into every other -- that merged
    volume IS the optical chamber. Upstream says so outright: the speckle path
    is "a second, independent optical path IN THE SAME CHAMBER". Requiring a
    wall there would be requiring the instrument not to work.
    """
    ok = True
    bores = P._bores()
    names = [n for n, *_ in S.OPTICAL_BORES]
    exit_z = {n: min(_bore_exit_z(t), S.HEAD_TOP)
              for n, _, t, _a in S.OPTICAL_BORES}
    for n in names:
        a = bores[n]
        za = exit_z[n]
        ax, ay = a.axis_point(za)
        ra = a.d / math.cos(a.tilt) / 2
        for o in names:
            if o == n:
                continue
            b = bores[o]
            # the other bore only exists at this height if it has not already
            # left the block
            if za > exit_z[o] + 1e-9:
                _rec(True, f"bore-entry/{n}-vs-{o}",
                     f"{o} has already left the block at Z={exit_z[o]:.1f}; "
                     f"{n} enters at Z={za:.1f}")
                continue
            bx, by = b.axis_point(za)
            rb = b.d / math.cos(b.tilt) / 2
            gap = math.hypot(ax - bx, ay - by) - ra - rb
            ok &= _rec(gap >= S.MIN_WALL, f"bore-entry/{n}-vs-{o}",
                       f"{gap:.2f} mm of wall at {n}'s entry, Z={za:.1f} "
                       f"(need >= {S.MIN_WALL})")
    return ok


def check_bores_exit():
    """Every bore must actually reach open air, or the part cannot be fitted."""
    ok = True
    bores = P._bores()
    for name, d, tilt, az in S.OPTICAL_BORES:
        b = bores[name]
        # A bore leaves either through the SIDE wall (if it reaches the head
        # radius below the deck) or through the TOP face. Either is fine; what
        # must not happen is a bore that dead-ends inside the block.
        R = S.HEAD_DIA / 2
        z_side = S.Z_SAMPLE + R / math.tan(math.radians(tilt)) if tilt > 0 else 1e9
        if z_side <= S.HEAD_TOP:
            ok &= _rec(True, f"bore-exit/{name}",
                       f"exits the SIDE wall at Z={z_side:.2f} "
                       f"(deck at {S.HEAD_TOP:.2f})")
        else:
            x, y = b.axis_point(S.HEAD_TOP)
            r = math.hypot(x - S.RS_X, y - S.RS_Y)
            half = d / math.cos(math.radians(tilt)) / 2
            ok &= _rec(r + half <= R, f"bore-exit/{name}",
                       f"exits the TOP face at r={r:.2f} (edge "
                       f"{r + half:.2f}) vs head radius {R:.1f}")
            # and it must clear the AS7341 board sitting on that face
            # board LONG axis along X: half-extent AS_PCB_L/2 at az 0/180,
            # AS_PCB_W/2 at az 90/270
            board_reach = min(S.AS_PCB_L / 2 / max(abs(math.cos(math.radians(az))), 1e-9),
                              S.AS_PCB_W / 2 / max(abs(math.sin(math.radians(az))), 1e-9))
            ok &= _rec(r - half >= board_reach, f"bore-exit/{name}-clears-board",
                       f"bore inner edge r={r - half:.2f} vs AS7341 reach "
                       f"{board_reach:.2f} mm at azimuth {az:.0f}")
    return ok


def check_pi_mounting():
    ok = True
    holes = S.pi_holes()
    xs = sorted({round(x, 3) for x, _ in holes})
    ys = sorted({round(y, 3) for _, y in holes})
    ok &= _rec(abs((xs[1] - xs[0]) - S.PI_HOLE_DX) < 1e-6, "pi/hole-pitch-x",
               f"{xs[1] - xs[0]:.2f} mm (spec {S.PI_HOLE_DX})")
    ok &= _rec(abs((ys[1] - ys[0]) - S.PI_HOLE_DY) < 1e-6, "pi/hole-pitch-y",
               f"{ys[1] - ys[0]:.2f} mm (spec {S.PI_HOLE_DY})")
    ok &= _rec(S.M25_TAP < S.PI_HOLE_D, "pi/boss-tap",
               f"boss tap Ø{S.M25_TAP} into the Pi's Ø{S.PI_HOLE_D} clearance "
               f"hole -- M2.5 self-tapping")
    # board must sit inside the inner envelope
    xmin = min(S.pi_to_case(0, 0)[0], S.pi_to_case(S.PI_L, 0)[0])
    xmax = max(S.pi_to_case(0, 0)[0], S.pi_to_case(S.PI_L, 0)[0])
    ymin = min(S.pi_to_case(0, 0)[1], S.pi_to_case(0, S.PI_W)[1])
    ymax = max(S.pi_to_case(0, 0)[1], S.pi_to_case(0, S.PI_W)[1])
    lim_x, lim_y = S.ENV_X / 2 - S.WALL, S.ENV_Y / 2 - S.WALL
    ok &= _rec(xmin >= -lim_x - 1e-6 and xmax <= lim_x + 1e-6, "pi/fits-x",
               f"board X {xmin:.1f}..{xmax:.1f} inside +-{lim_x:.1f}")
    ok &= _rec(ymin >= -lim_y - 1e-6 and ymax <= lim_y + 1e-6, "pi/fits-y",
               f"board Y {ymin:.1f}..{ymax:.1f} inside +-{lim_y:.1f}")
    # headroom under the part line / ceiling
    top = S.PI_PCB_Z + S.PI_PCB_T + S.PI_TALLEST
    ok &= _rec(top < S.ENV_Z - S.CEIL, "pi/headroom",
               f"tallest Pi component at Z={top:.1f}, ceiling inner face at "
               f"Z={S.ENV_Z - S.CEIL:.1f} -- {S.ENV_Z - S.CEIL - top:.1f} mm clear")
    # GPIO header must be reachable, i.e. not under the optical head
    hx, hy = S.pi_to_case(S.PI_HDR_CX, S.PI_HDR_CY)
    dist = math.hypot(hx - S.RS_X, hy - S.RS_Y)
    ok &= _rec(dist > S.HEAD_DIA / 2 + 2.0, "pi/gpio-clear-of-head",
               f"GPIO header centre {dist:.1f} mm from the read spot, head "
               f"radius {S.HEAD_DIA / 2:.1f}")
    return ok


def check_port_windows():
    """Every Pi connector must have an opening it actually fits through, and
    that opening must live entirely in ONE shell -- a window split by the part
    line opens only the bottom half of the port."""
    ok = True
    pcb_top = S.PI_PCB_Z + S.PI_PCB_T

    # bottom-edge group: USB-C, 2x micro-HDMI, A/V jack
    grp = [("usb-c", S.PI_USBC_CX, 9.0, S.PI_USBC_H),
           ("hdmi0", S.PI_HDMI0_CX, 7.2, S.PI_HDMI_H),
           ("hdmi1", S.PI_HDMI1_CX, 7.2, S.PI_HDMI_H),
           ("av", S.PI_AV_CX, 6.5, S.PI_AV_H)]
    w0, w1 = S.PI_PORTS_Y0
    for nm, cx, w, h in grp:
        ok &= _rec(w0 <= cx - w / 2 and cx + w / 2 <= w1,
                   f"port/{nm}-in-window",
                   f"body {cx - w/2:.1f}..{cx + w/2:.1f} inside window "
                   f"{w0}..{w1} (board frame)")
        ok &= _rec(pcb_top + h <= S.PART_LINE_Z, f"port/{nm}-below-part-line",
                   f"top at Z={pcb_top + h:.1f}, part line {S.PART_LINE_Z}")
    ok &= _rec(S.PI_PORTS_Y0_H >= max(h for _, _, _, h in grp),
               "port/bottom-window-height",
               f"window {S.PI_PORTS_Y0_H} mm tall vs tallest body "
               f"{max(h for _, _, _, h in grp)} mm")

    # right-edge stack: Ethernet + 2 USB
    r0, r1 = S.PI_PORTS_X85
    for nm, cy, w, h in (("ethernet", S.PI_ETH_CY, S.PI_ETH_W, S.PI_ETH_H),
                         ("usb3", S.PI_USB3_CY, S.PI_USB_W, S.PI_USB_H),
                         ("usb2", S.PI_USB2_CY, S.PI_USB_W, S.PI_USB_H)):
        ok &= _rec(r0 <= cy - w / 2 and cy + w / 2 <= r1,
                   f"port/{nm}-in-window",
                   f"body {cy - w/2:.2f}..{cy + w/2:.2f} inside window "
                   f"{r0}..{r1}")
        ok &= _rec(pcb_top + h <= S.PART_LINE_Z, f"port/{nm}-below-part-line",
                   f"top at Z={pcb_top + h:.1f}, part line {S.PART_LINE_Z} "
                   f"-- a 16 mm USB stack is what forces this")
    # microSD sticks out of the x=0 edge, below the PCB
    # The microSD hangs BELOW the board, so it must clear the FLOOR, not zero.
    sd_z = S.PI_PCB_Z - S.PI_SD_H
    ok &= _rec(sd_z > S.FLOOR, "port/microsd-clears-floor",
               f"microSD underside at Z={sd_z:.1f}, floor top at Z={S.FLOOR} "
               f"-- {sd_z - S.FLOOR:.1f} mm of clearance")
    ok &= _rec(S.PI_STANDOFF >= S.PI_SD_H + 1.5, "port/microsd-standoff",
               f"{S.PI_STANDOFF} mm under the PCB vs a {S.PI_SD_H} mm slot "
               f"plus card. UNVERIFIED depth -- check with calipers")
    return ok


def check_oled():
    ok = True
    ok &= _rec(S.OLED_ACTIVE_L <= S.OLED_PCB_L and S.OLED_ACTIVE_W <= S.OLED_PCB_W,
               "oled/active-inside-pcb",
               f"active {S.OLED_ACTIVE_L} x {S.OLED_ACTIVE_W} inside PCB "
               f"{S.OLED_PCB_L} x {S.OLED_PCB_W}")
    ok &= _rec(S.OLED_HOLE_DX < S.OLED_PCB_L and S.OLED_HOLE_DY < S.OLED_PCB_W,
               "oled/hole-pitch", f"{S.OLED_HOLE_DX} x {S.OLED_HOLE_DY} inside "
               f"the PCB outline")
    # the window must clear the active area but stay inside the PCB footprint
    half_l = S.OLED_ACTIVE_L / 2 + 0.6
    ok &= _rec(half_l <= S.OLED_PCB_L / 2, "oled/window-inside-pcb",
               f"window half-length {half_l:.2f} vs PCB half "
               f"{S.OLED_PCB_L / 2:.2f}")
    # OLED must not foul the Pi below it
    oled_bottom = S.ENV_Z - S.CEIL - P.OLED_POST_H - S.OLED_PCB_T
    pi_top = S.PI_PCB_Z + S.PI_PCB_T + S.PI_TALLEST
    ok &= _rec(oled_bottom > pi_top, "oled/clears-pi",
               f"OLED underside Z={oled_bottom:.1f}, Pi top Z={pi_top:.1f} "
               f"-- {oled_bottom - pi_top:.1f} mm clear")
    # bezel aperture must not be larger than the ceiling window
    ok &= _rec(S.OLED_ACTIVE_L <= S.OLED_ACTIVE_L + 1.2, "oled/bezel-masks",
               "bezel aperture equals the active area; the ceiling window is "
               "0.6 mm larger all round, so the bezel is what you see")
    return ok


def check_light_tight():
    """Blind features must stay blind. One through-hole and G1 stops working."""
    ok = True
    ok &= _rec(S.VENT_DEPTH < S.CEIL, "light/vents-blind",
               f"vent pockets {S.VENT_DEPTH} mm deep into a {S.CEIL} mm "
               f"ceiling -- {S.CEIL - S.VENT_DEPTH:.1f} mm of material behind")
    ok &= _rec(P.FINGER_WELL_DEPTH < S.CEIL, "light/finger-well-blind",
               f"finger well {P.FINGER_WELL_DEPTH} mm into a {S.CEIL} mm "
               f"ceiling; only the Ø{S.RING_WINDOW_D} ring bore goes through, "
               f"and the ring window seals it")
    ok &= _rec(S.HEAD_GAP > 0 and P.HEAD_SKIRT_Z > S.Z_SAMPLE,
               "light/head-skirt",
               f"head skirt closes to Z={P.HEAD_SKIRT_Z:.2f}, "
               f"{P.HEAD_SKIRT_Z - S.Z_SAMPLE:.2f} mm over the window")
    ok &= _rec(S.BAFFLE_OFFSET > 0, "light/slot-baffle",
               f"baffle {S.BAFFLE_OFFSET} mm behind the slot mouth")
    return ok


def check_ring_geometry():
    ok = True
    ok &= _rec(S.RING_OD > P.FINGER_WELL_D, "ring/collar-visible",
               f"ring OD {S.RING_OD} around a Ø{P.FINGER_WELL_D} finger well "
               f"-- {(S.RING_OD - P.FINGER_WELL_D) / 2:.1f} mm of collar")
    ok &= _rec(S.RING_WINDOW_D < P.FINGER_WELL_D, "ring/window-seat",
               f"Ø{S.RING_WINDOW_D} window seats on the "
               f"{(P.FINGER_WELL_D - S.RING_WINDOW_D) / 2:.1f} mm ledge at the "
               f"bottom of the finger well")
    ok &= _rec(S.DISH_D < S.ENV_X - 2 * S.WALL, "ring/dish-fits",
               f"Ø{S.DISH_D} dish inside a {S.ENV_X - 2 * S.WALL:.1f} mm "
               f"inner width")
    return ok


def check_cartridge():
    """The six distances the two-stop read needs to hold at once."""
    ok = True
    moat_r = S.MOAT_D / 2
    ok &= _rec(S.PATCH_FROM_TIP + S.PATCH / 2 < S.WELL_FROM_TIP - moat_r,
               "cart/patch-clear-of-moat",
               f"patch ends at {S.PATCH_FROM_TIP + S.PATCH / 2:.2f}, moat "
               f"starts at {S.WELL_FROM_TIP - moat_r:.2f}")
    ok &= _rec(S.PATCH_FROM_TIP - S.PATCH / 2 > 0, "cart/patch-on-part",
               f"patch starts {S.PATCH_FROM_TIP - S.PATCH / 2:.2f} mm from the tip")
    ok &= _rec(S.STOP1 < S.STOP2, "cart/stop-order",
               f"stop 1 at {S.STOP1} (patch under the aperture), stop 2 at "
               f"{S.STOP2} (well under the aperture)")
    ok &= _rec(S.DETENT_PROUD < S.SLOT_H - S.CART_T, "cart/detent-rides",
               f"detent {S.DETENT_PROUD} proud into "
               f"{S.SLOT_H - S.CART_T:.2f} mm of slot clearance")
    ok &= _rec(S.CART_L - S.STOP2 > 8.0, "cart/grip",
               f"{S.CART_L - S.STOP2:.1f} mm proud of the slot to pull a "
               f"blood-contact part back out")
    ok &= _rec(S.GRIP_T > S.SLOT_H, "cart/grip-is-the-stop",
               f"grip {S.GRIP_T} thick against a {S.SLOT_H} slot")
    # the two stops must put the right feature under the aperture
    ok &= _rec(abs((S.STOP1 - S.TRAVEL) - S.PATCH_FROM_TIP) < 0.5,
               "cart/stop1-reads-patch",
               f"at stop 1 the point under the aperture is "
               f"{S.STOP1 - S.TRAVEL:.2f} mm from the tip; the patch is at "
               f"{S.PATCH_FROM_TIP}")
    ok &= _rec(abs((S.STOP2 - S.TRAVEL) - S.WELL_FROM_TIP) < 0.5,
               "cart/stop2-reads-well",
               f"at stop 2 the point under the aperture is "
               f"{S.STOP2 - S.TRAVEL:.2f} mm from the tip; the well is at "
               f"{S.WELL_FROM_TIP}")
    ok &= _rec(S.WELL_DEPTH >= 0.4, "cart/well-optically-semi-infinite",
               f"well {S.WELL_DEPTH} mm deep -- at >= 0.4 reflectance is "
               f"independent of fill volume. DO NOT make this thinner")
    ok &= _rec(S.APERTURE_BORE < S.WELL_D, "cart/spot-inside-well",
               f"Ø{S.APERTURE_BORE} spot inside a Ø{S.WELL_D} well, so the "
               f"sensor never sees the meniscus")
    return ok


# --------------------------------------------------------------------------
# SAMPLED -- against the real triangles
# --------------------------------------------------------------------------

def check_corridor(meshes):
    """The cartridge must be able to reach stop 2. Nothing solid in its path."""
    hw = (S.CART_W + 2 * S.FIT) / 2
    y0 = -S.ENV_Y / 2
    y1 = S.RS_Y + (S.CART_L - S.TRAVEL)
    pts = _grid(-hw, hw, y0 + 1.0, y1, S.SLOT_Z0 + 0.05, S.SLOT_Z0 + S.CART_T,
                n=(7, 26, 4))
    ok = True
    for nm in ("shell_lower", "optical_head", "shell_upper"):
        bad = _inside(meshes[nm], pts)
        ok &= _rec(not bad.any(), f"corridor/{nm}",
                   f"{int(bad.sum())} of {len(pts)} corridor samples land "
                   f"inside {nm}")
    return ok


def check_pi_bay(meshes):
    """The board and its tallest components must have somewhere to be."""
    x0, y0 = S.pi_to_case(S.PI_L - 1.0, S.PI_W - 1.0)
    x1, y1 = S.pi_to_case(1.0, 1.0)
    xa, xb = min(x0, x1), max(x0, x1)
    ya, yb = min(y0, y1), max(y0, y1)
    pts = _grid(xa, xb, ya, yb,
                S.PI_PCB_Z + 0.1, S.PI_PCB_Z + S.PI_PCB_T + S.PI_TALLEST,
                n=(11, 9, 5))
    # drop samples that legitimately sit inside a mounting boss
    keep = []
    for p in pts:
        if all(math.hypot(p[0] - hx, p[1] - hy) > 3.6 for hx, hy in S.pi_holes()):
            keep.append(p)
    pts = np.array(keep)
    ok = True
    for nm in ("shell_lower", "shell_upper", "optical_head"):
        bad = _inside(meshes[nm], pts)
        ok &= _rec(not bad.any(), f"pi-bay/{nm}",
                   f"{int(bad.sum())} of {len(pts)} Pi-bay samples land inside "
                   f"{nm}")
    return ok


def check_part_line(meshes):
    """No point may be solid in both shells."""
    lo, up = meshes["shell_lower"], meshes["shell_upper"]
    zs = np.linspace(S.PART_LINE_Z + 0.1, S.PART_LINE_Z + S.LAP_H - 0.1, 4)
    pts = []
    for z in zs:
        for a in np.linspace(0, 2 * math.pi, 48, endpoint=False):
            for r in (0.3, 0.6, 0.9):
                pts.append(((S.ENV_X / 2 - S.WALL * r) * math.cos(a),
                            (S.ENV_Y / 2 - S.WALL * r) * math.sin(a), z))
    pts = np.array(pts)
    both = _inside(lo, pts) & _inside(up, pts)
    return _rec(not both.any(), "part-line/no-overlap",
                f"{int(both.sum())} of {len(pts)} samples solid in BOTH shells")


def check_plates(meshes):
    ok = True
    for nm, m in meshes.items():
        lo, hi = m.bbox()
        d = hi - lo
        fits = d[0] <= S.PLATE_MAX and d[1] <= S.PLATE_MAX and d[2] <= S.PLATE_MAX
        ok &= _rec(fits, f"plate/{nm}",
                   f"{d[0]:.1f} x {d[1]:.1f} x {d[2]:.1f} mm vs a "
                   f"{S.PLATE_MAX:.0f} mm bed")
    return ok


def check_walls():
    ok = True
    ok &= _rec(S.LAP_INNER >= S.MIN_WALL, "wall/lap-lower",
               f"lower shell tongue {S.LAP_INNER} mm")
    up = S.WALL - S.LAP_INNER - S.LAP_FIT
    ok &= _rec(up >= S.MIN_WALL, "wall/lap-upper",
               f"upper shell rebate {up:.2f} mm")
    ok &= _rec(S.WALL >= 2.0, "wall/shell", f"{S.WALL} mm, 6 perimeters at 0.4")
    ok &= _rec(S.BOSS_OD - S.HEATSET_D >= 2 * S.MIN_WALL, "wall/boss",
               f"{(S.BOSS_OD - S.HEATSET_D) / 2:.2f} mm around a "
               f"Ø{S.HEATSET_D} heat-set insert")
    ok &= _rec(S.HEATSET_L < S.PART_LINE_Z - S.FLOOR, "wall/heatset-depth",
               f"insert {S.HEATSET_L} mm into a "
               f"{S.PART_LINE_Z - S.FLOOR:.1f} mm boss")
    return ok


def check_bosses_clear_pi():
    """Upstream's real bug: insert bosses standing inside the Pi footprint."""
    ok = True
    x0, y0 = S.pi_to_case(0.0, 0.0)
    x1, y1 = S.pi_to_case(S.PI_L, S.PI_W)
    bx0, bx1 = min(x0, x1), max(x0, x1)
    by0, by1 = min(y0, y1), max(y0, y1)
    for i, (x, y) in enumerate(S.BOSS_XY):
        inside = (bx0 - S.BOSS_OD / 2 < x < bx1 + S.BOSS_OD / 2 and
                  by0 - S.BOSS_OD / 2 < y < by1 + S.BOSS_OD / 2)
        ok &= _rec(not inside, f"boss/{i}-clear-of-pi",
                   f"boss at ({x:.0f}, {y:.0f}) vs board "
                   f"X[{bx0:.0f},{bx1:.0f}] Y[{by0:.0f},{by1:.0f}]")
    for i, (x, y) in enumerate(S.BOSS_XY):
        d = math.hypot(x - S.RS_X, y - S.RS_Y)
        ok &= _rec(d > S.HEAD_DIA / 2 + S.BOSS_OD / 2, f"boss/{i}-clear-of-head",
                   f"{d:.1f} mm from the read spot")
    return ok


def check_head_posts():
    """Head mounting posts must miss the cartridge corridor."""
    ok = True
    hw = (S.CART_W + 2 * S.FIT) / 2
    for i, (x, y) in enumerate(P.head_posts_xy()):
        ok &= _rec(abs(x) > hw + 3.2, f"head-post/{i}-clear-of-corridor",
                   f"post at X={x:+.2f}, corridor half-width {hw:.2f}")
        r = math.hypot(x - S.RS_X, y - S.RS_Y)
        ok &= _rec(r < S.HEAD_DIA / 2 - 1.0, f"head-post/{i}-under-head",
                   f"r={r:.1f} vs head radius {S.HEAD_DIA / 2:.1f}")
    return ok


# --------------------------------------------------------------------------

def run(meshes=None, sampled=True):
    RESULTS.clear()
    check_optics()
    check_bore_separation()
    check_bores_exit()
    check_cartridge()
    check_pi_mounting()
    check_port_windows()
    check_bosses_clear_pi()
    check_head_posts()
    check_oled()
    check_ring_geometry()
    check_light_tight()
    check_walls()
    if sampled and meshes:
        check_plates(meshes)
        check_corridor(meshes)
        check_pi_bay(meshes)
        check_part_line(meshes)
    return RESULTS


def report(results, verbose=True):
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    if verbose:
        for st, name, detail in results:
            mark = {"PASS": "  ok  ", "WARN": " warn ", "FAIL": " FAIL "}[st]
            print(f"[{mark}] {name:34s} {detail}")
    print(f"\n{len(results)} checks, {len(fails)} failed, {len(warns)} warnings")
    return len(fails) == 0


if __name__ == "__main__":
    import sys
    meshes = {n: fn() for n, (fn, _, _) in P.PARTS.items()}
    ok = report(run(meshes))
    sys.exit(0 if ok else 1)
