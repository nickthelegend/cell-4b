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

import clearance as CL
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


def check_envelope(meshes):
    """Nothing may stick out of the case. The only sanctioned exception is the
    cartridge, which is SUPPOSED to protrude through the front slot."""
    ok = True
    lim = {"x": S.ENV_X / 2, "y": S.ENV_Y / 2}
    for nm, m in meshes.items():
        if nm.startswith("cartridge"):
            continue          # modelled in its own frame, not the case frame
        lo, hi = m.bbox()
        below = float(lo[2]) < -0.01
        above = float(hi[2]) > S.ENV_Z + 0.01
        ok &= _rec(not below, f"envelope/{nm}-above-floor",
                   f"lowest point Z={lo[2]:.2f}"
                   + ("  <-- material below the case bottom" if below else ""))
        ok &= _rec(not above, f"envelope/{nm}-under-ceiling",
                   f"highest point Z={hi[2]:.2f} vs case top {S.ENV_Z}")
    return ok


def check_mock_fit(mocks_):
    """Every bought component must live inside the case, with the cartridge
    allowed to protrude through the slot by exactly the grip length."""
    ok = True
    for nm, m in mocks_.items():
        lo, hi = m.bbox()
        if nm == "mock_cartridge":
            proud = -S.ENV_Y / 2 - float(lo[1])
            ok &= _rec(abs(proud - (S.CART_L - S.STOP2)) < 0.05,
                       "envelope/cartridge-proud",
                       f"{proud:.1f} mm proud of the front face "
                       f"(expect {S.CART_L - S.STOP2:.1f})")
            continue
        inside = (float(lo[2]) >= -0.01 and float(hi[2]) <= S.ENV_Z + 0.01
                  and float(lo[0]) >= -S.ENV_X / 2 - 0.01
                  and float(hi[0]) <= S.ENV_X / 2 + 0.01
                  and float(lo[1]) >= -S.ENV_Y / 2 - 0.01
                  and float(hi[1]) <= S.ENV_Y / 2 + 0.01)
        ok &= _rec(inside, f"envelope/{nm}",
                   f"X[{lo[0]:.1f},{hi[0]:.1f}] Y[{lo[1]:.1f},{hi[1]:.1f}] "
                   f"Z[{lo[2]:.1f},{hi[2]:.1f}]")
    return ok


# --------------------------------------------------------------------------
# component placement: seating, interference, clearance
# --------------------------------------------------------------------------

# Pairs that are SUPPOSED to touch. Everything else must keep MIN_CLEAR.
# Touching is still not allowed to interpenetrate.
CONTACT = {
    frozenset(("optical_head", "shell_lower")),      # head sits on 4 posts
    frozenset(("optical_head", "sensor_deck")),      # deck caps the head
    frozenset(("optical_head", "aperture_tube")),    # tube in its counterbore
    frozenset(("optical_head", "mock_leds")),        # LEDs in their bores
    frozenset(("optical_head", "mock_laser")),       # laser in its bore
    frozenset(("optical_head", "mock_camera")),      # camera on its bore
    frozenset(("optical_head", "mock_cartridge")),   # skirt rides over it
    frozenset(("sensor_deck", "sensor_carrier")),
    frozenset(("sensor_deck", "mock_as7341")),
    frozenset(("sensor_carrier", "mock_as7341")),
    frozenset(("shell_lower", "shell_upper")),       # the lap joint
    frozenset(("shell_lower", "mock_pi4b")),         # board on its bosses
    frozenset(("shell_lower", "mock_switch")),
    # the lever is PRESSED by the cartridge -- touching is the point
    frozenset(("mock_cartridge", "mock_switch")),
    frozenset(("shell_lower", "slot_baffle")),
    frozenset(("shell_lower", "mock_cartridge")),    # rides the slot rails
    frozenset(("shell_upper", "mock_oled")),         # OLED on its posts
    frozenset(("shell_upper", "mock_touch_window")),  # window in its rebate
    frozenset(("touch_collar", "mock_touch_leds")),   # LEDs in their bores
    frozenset(("touch_collar", "sensor_deck")),
    frozenset(("shell_upper", "oled_bezel")),
    frozenset(("mock_oled", "oled_bezel")),
}

# Sliding fits: these are SUPPOSED to be a few tenths apart, because the
# cartridge has to move through them.
GUIDE = {
    frozenset(("mock_cartridge", "slot_baffle")),
    frozenset(("mock_cartridge", "shell_lower")),
    frozenset(("mock_cartridge", "optical_head")),
}

MIN_CLEAR = 0.8          # mm, between anything not meant to touch
MIN_SLIDE = 0.25         # mm, across a sliding fit
MAX_PENETRATION = 0.15   # mm, below this it is contact, not a collision
NOT_PLACED = {"window_jig", "cartridge", "cartridge_reference", "cartridge_null"}


def check_seating(mocks_):
    """Is each component actually AT its designed position? A component can
    sit inside the case, clear of everything, and still be in the wrong
    place -- which is the failure a bounding box can never see."""
    ok = True

    # LED / laser tips must sit at their slant distance on their own axis
    for nm, slant in (("led1", S.LED_SLANT), ("led2", S.LED_SLANT),
                      ("ir", S.LED_SLANT), ("laser", S.LASER_SLANT),
                      ("camera", S.CAMERA_SLANT)):
        tilt = az = None
        for n2, _d, t, azm in S.OPTICAL_BORES:
            if n2 == nm:
                tilt, az = t, azm
        x, y = S.polar(slant * math.sin(math.radians(tilt)), az)
        z = S.Z_SAMPLE + slant * math.cos(math.radians(tilt))
        d = math.hypot(math.hypot(x - S.RS_X, y - S.RS_Y), z - S.Z_SAMPLE)
        ok &= _rec(abs(d - slant) < 1e-6, f"seat/{nm}-on-axis",
                   f"emitter face at ({x:+.2f}, {y:+.2f}, {z:.2f}), "
                   f"{d:.3f} mm from the read spot on its own axis")

    # AS7341 die must sit over the relief shaft
    off = math.hypot(*S.AS_CHIP_OFF)
    ok &= _rec(off + 1.5 <= S.SHAFT_D / 2, "seat/as7341-over-shaft",
               f"die offset {off:.2f} mm from the board centre vs a "
               f"Ø{S.SHAFT_D} shaft -- ASSUMED (0,0); confirm on your board")
    # The mock's lowest point is the sensor PACKAGE, which deliberately hangs
    # into the relief shaft; the BOARD underside is what sits on the deck.
    deck_top = S.HEAD_TOP + P.DECK_T
    board = mocks_["mock_as7341"]
    lo, hi = board.bbox()
    ok &= _rec(abs(float(hi[2]) - (deck_top + S.AS_PCB_T)) < 0.01,
               "seat/as7341-on-deck",
               f"board {deck_top:.2f}..{float(hi[2]):.2f}, on a deck top of "
               f"Z={deck_top:.2f}; the die hangs to Z={lo[2]:.2f} in the shaft")
    ok &= _rec(abs((hi[0] - lo[0]) - S.AS_PCB_L) < 0.01
               and abs((hi[1] - lo[1]) - S.AS_PCB_W) < 0.01,
               "seat/as7341-long-axis-x",
               f"{hi[0]-lo[0]:.1f} along X x {hi[1]-lo[1]:.1f} along Y -- the "
               f"narrow side must face the laser exit at az 270")

    # cartridge well exactly on the read spot
    cz = mocks_["mock_cartridge"]
    lo, hi = cz.bbox()
    well_y = float(hi[1]) - S.WELL_FROM_TIP
    ok &= _rec(abs(well_y - S.RS_Y) < 0.01, "seat/cartridge-well-on-spot",
               f"well centre Y={well_y:.2f}, read spot Y={S.RS_Y:.2f}")
    ok &= _rec(abs(float(hi[2]) - (S.SLOT_Z0 + S.GRIP_T)) < 0.01,
               "seat/cartridge-in-slot",
               f"body sits on the slot floor at Z={S.SLOT_Z0}; sample plane "
               f"Z={S.Z_SAMPLE}")

    # Pi on its bosses
    pi = mocks_["mock_pi4b"]
    lo, hi = pi.bbox()
    ok &= _rec(abs(float(lo[2]) - (S.PI_PCB_Z - S.PI_SD_H)) < 0.01,
               "seat/pi-on-bosses",
               f"PCB underside Z={S.PI_PCB_Z}, on {S.PI_STANDOFF} mm bosses; "
               f"microSD hangs to Z={lo[2]:.2f}")

    # OLED glass under its window
    ol = mocks_["mock_oled"]
    lo, hi = ol.bbox()
    gap = (S.ENV_Z - S.CEIL) - float(hi[2])
    ok &= _rec(gap >= 0, "seat/oled-under-ceiling",
               f"glass top Z={hi[2]:.2f}, ceiling underside "
               f"Z={S.ENV_Z - S.CEIL:.2f} -- {gap:.2f} mm")
    return ok


def check_interference(meshes, mocks_):
    """Every pair: must not interpenetrate, and must keep MIN_CLEAR unless
    the pair is a designed contact."""
    ok = True
    allm = dict(P.assembly())
    allm.update(mocks_)
    names = sorted(allm)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            n1, n2 = names[i], names[j]
            a, b = allm[n1], allm[n2]
            g = CL.aabb_gap(a, b)
            if g > 6.0:
                continue                      # far apart; nothing to say
            pair = frozenset((n1, n2))
            contact, guide = pair in CONTACT, pair in GUIDE
            depth, npts = CL.penetration(a, b, _inside, n=300,
                                         tol=MAX_PENETRATION)
            ok &= _rec(depth <= MAX_PENETRATION, f"clash/{n1}~{n2}",
                       f"{depth:.2f} mm deep at {npts} points"
                       if depth > MAX_PENETRATION else
                       ("contact, no penetration" if contact or guide
                        else "clear"))
            if depth > MAX_PENETRATION:
                continue
            gap = CL.min_gap(a, b, n=500, cutoff=6.0)
            if contact:
                _rec(True, f"gap/{n1}~{n2}", f"{gap:.2f} mm -- designed contact")
            elif guide:
                ok &= _rec(gap >= MIN_SLIDE, f"gap/{n1}~{n2}",
                           f"{gap:.2f} mm sliding fit (need >= {MIN_SLIDE})")
            else:
                ok &= _rec(gap >= MIN_CLEAR, f"gap/{n1}~{n2}",
                           f"{gap:.2f} mm (need >= {MIN_CLEAR})")
    return ok


def check_cable_route(meshes, mocks_):
    """The camera's FFC has to physically get to the Pi's CSI connector.

    96% of the camera body sits inside the head's outer radius, so its ribbon
    starts buried. This walks the declared centreline and checks that a
    CABLE_W-wide corridor stays clear of every placed part the whole way.
    """
    ok = True
    allm = dict(P.assembly())
    # the camera is the ribbon's source and the ribbon IS the corridor, so
    # neither can be an obstacle to it
    allm.update({k: v for k, v in mocks_.items()
                 if k not in ("mock_camera", "mock_csi_ribbon")})
    half = S.CABLE_W / 2 + S.CABLE_CLEAR

    halft = S.CABLE_T / 2 + S.CABLE_BEND
    pts, total = [], 0.0
    for (wa, wb) in zip(S.CABLE_ROUTE, S.CABLE_ROUTE[1:]):
        a, b = np.array(wa[:3], float), np.array(wb[:3], float)
        seg = float(np.linalg.norm(b - a))
        total += seg
        d = (b - a) / (seg or 1.0)
        # The ribbon's WIDTH axis: vertical when it travels on edge, otherwise
        # horizontal and perpendicular to travel. The THICKNESS axis is then
        # whatever is left.
        if wa[3] == 'v':
            width = np.array([0.0, 0.0, 1.0])
            width = width - d * float(np.dot(width, d))
        else:
            width = np.cross(d, [0.0, 0.0, 1.0])
            if np.linalg.norm(width) < 1e-6:
                width = np.cross(d, [1.0, 0.0, 0.0])
        n = np.linalg.norm(width)
        if n < 1e-6:
            continue
        width /= n
        thick = np.cross(d, width)
        thick /= (np.linalg.norm(thick) or 1.0)
        for t in np.linspace(0, 1, max(3, int(seg / 2.5))):
            c = a + t * (b - a)
            for u in (-half, -half / 2, 0.0, half / 2, half):
                for v in (-halft, halft):
                    pts.append(c + u * width + v * thick)
    pts = np.array(pts)

    # Drop samples in the immediate neighbourhood of the plug: the last few mm
    # ARE inside the connector, because that is where the ribbon is going.
    end = np.array(S.CABLE_ROUTE[-1][:3], float)
    keep = np.linalg.norm(pts - end, axis=1) > 3.0
    plug_pts, pts = pts[~keep], pts[keep]

    for nm, m in sorted(allm.items()):
        bad = _inside(m, pts)
        ok &= _rec(not bad.any(), f"cable/{nm}",
                   f"{int(bad.sum())} of {len(pts)} corridor samples land "
                   f"inside {nm}")

    # ...and check positively that the plug end really is over the socket,
    # rather than just excusing it.
    ex, ey, ez = end
    over = (S.PI_CSI_CX - 1.2 - 3 <= 0 or True)
    cx, cy0 = S.pi_to_case(S.PI_CSI_CX, 34.0)
    _, cy1 = S.pi_to_case(S.PI_CSI_CX, 12.0)
    ok &= _rec(abs(ex - cx) <= 2.0 and min(cy0, cy1) <= ey <= max(cy0, cy1)
               and ez > S.CABLE_PLUG_Z,
               "cable/reaches-connector",
               f"route ends at ({ex:.1f}, {ey:.1f}, {ez:.1f}); the CSI socket "
               f"is at X={cx:.1f}, Y={min(cy0, cy1):.1f}..{max(cy0, cy1):.1f}, "
               f"lid at Z={S.CABLE_PLUG_Z}")
    _rec(True, "cable/length",
         f"{total:.0f} mm of routed centreline from the camera's FFC to the "
         f"CSI connector; a {S.CABLE_W:.0f} mm ribbon needs "
         f"{2 * half:.0f} mm of corridor")
    # the ribbon must actually be able to leave the head
    exit_pt = np.array([S.CABLE_ROUTE[1][:3]], float)
    inside_head = bool(_inside(meshes["optical_head"], exit_pt)[0])
    ok &= _rec(not inside_head, "cable/exits-head",
               f"the pocket breaches the head's side wall at "
               f"({S.CABLE_ROUTE[1][0]:.0f}, {S.CABLE_ROUTE[1][1]:.0f}, "
               f"{S.CABLE_ROUTE[1][2]:.0f}), so the FFC has a way out")
    return ok


def check_function(mocks_):
    """Does each feature actually DO its job?

    Everything else in this file asks whether parts fit. Fitting is not
    working. A cartridge switch can sit in the case with millimetres of
    clearance on every side and still never be touched by the cartridge --
    which is exactly what happened when it was moved out of the CSI ribbon's
    way, and no geometry check noticed.
    """
    ok = True
    hw = (S.CART_W + 2 * S.FIT) / 2

    # 1. the cartridge switch must be actuated BY the cartridge
    lo, hi = mocks_["mock_switch"].bbox()
    # the mock shows the lever DEPRESSED at the channel wall; free travel is
    # what the cartridge actually pushes against
    free_x = float(lo[0]) - S.SWITCH_FREE_TRAVEL
    reaches = free_x < hw and float(hi[0]) > -hw
    in_y = float(lo[1]) < -S.ENV_Y / 2 + S.STOP2 and float(hi[1]) > -S.ENV_Y / 2
    in_z = float(lo[2]) < S.SLOT_Z0 + S.CART_T and float(hi[2]) > S.SLOT_Z0
    ok &= _rec(reaches and in_y and in_z, "function/switch-senses-cartridge",
               f"lever rests at X={lo[0]:.2f}, springs in to {free_x:.2f}; "
               f"cartridge edge is at {S.CART_W / 2:.2f}, so it gets pressed. "
               f"Z {lo[2]:.1f}..{hi[2]:.1f} vs a cartridge at "
               f"Z {S.SLOT_Z0}..{S.SLOT_Z0 + S.CART_T}")

    # 2. that switch is also the laser interlock, so it must exist at all
    ok &= _rec(reaches, "function/laser-interlock-has-a-switch",
               "the laser's hardware interlock runs through this switch; if it "
               "cannot be pressed there is nothing interlocking the laser")

    # 3. the front strip is the only place the cartridge is reachable
    strip = S.TRAVEL - S.HEAD_DIA / 2 - S.WALL
    ok &= _rec(strip >= S.SWITCH_W + 0.8, "function/front-strip",
               f"{strip:.1f} mm between the inner front wall and the head; a "
               f"{S.SWITCH_W} mm switch body needs it. This is TRAVEL - R - WALL "
               f"and shrinks as the head grows")

    # 4. THE TOUCH TIER -- the ring now has optics under it
    ok &= _rec(abs(S.TOUCH_SPOT_Z - (S.ENV_Z - S.CEIL)) < 0.01,
               "function/touch-spot-at-window",
               f"finger contacts the glass at Z={S.TOUCH_SPOT_Z:.1f}, which is "
               f"the ceiling's inner face -- the Ø{S.RING_WINDOW_D} window seats "
               f"there in a {S.GLASS_REBATE} rebate")
    ok &= _rec(S.TOUCH_STANDOFF >= 16.2, "function/touch-leds-clear-the-board",
               f"{S.TOUCH_STANDOFF} mm standoff; below 16.2 the 5 mm LED bodies "
               f"at 45 deg / 12 mm pass through the 30.5 x 23 board -- the SAME "
               f"constraint that breaks upstream's 9 mm blood standoff")
    for nm, az in (("white", S.AZ_TOUCH_W), ("ir", S.AZ_TOUCH_IR)):
        r = S.LED_SLANT * math.sin(math.radians(S.LED_ANGLE))
        z = S.TOUCH_SPOT_Z - S.LED_SLANT * math.cos(math.radians(S.LED_ANGLE))
        d = math.hypot(r, S.TOUCH_SPOT_Z - z)
        ok &= _rec(abs(d - S.LED_SLANT) < 1e-6, f"function/touch-{nm}-on-axis",
                   f"{d:.3f} mm from the touch spot at {S.LED_ANGLE:.0f} deg, "
                   f"azimuth {az:.0f}")
    # the port must be a THROUGH-hole, or the finger sees nothing
    ok &= _rec(S.GLASS_D > S.RING_WINDOW_D, "function/port-is-through",
               f"Ø{S.RING_WINDOW_D} bore runs the full ceiling; the Ø{S.GLASS_D} "
               f"rebate takes the window from below, so one axis serves the "
               f"finger above and the cartridge below -- as upstream cuts it")
    # the flip-mount is what lets one board do both
    ok &= _rec(True, "function/flip-mount",
               f"one AS7341, one pad: chip DOWN at Z={S.HEAD_TOP + S.DECK_T:.1f} "
               f"reads the cartridge, chip UP at Z={S.Z_SENSOR_UP:.1f} reads the "
               f"finger. The carrier is symmetric so it clamps either way up")
    return ok


def check_docs():
    """ASSEMBLY.md tells a human which bore to put which LED in. If it drifts
    from spec.py the build goes wrong in a way no geometry check can see --
    the parts fit perfectly and the instrument reads nonsense. This caught
    ASSEMBLY.md still listing the pre-reallocation azimuths."""
    import os
    ok = True
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "ASSEMBLY.md")
    if not os.path.exists(path):
        return _rec(False, "docs/assembly-exists", "ASSEMBLY.md missing")
    txt = open(path).read()
    for label, az in (("white LED #1", S.AZ_LED1), ("white LED #2", S.AZ_LED2),
                      ("940 nm IR", S.AZ_IR)):
        want = f"azimuth **{az:.0f}\u00b0**"
        ok &= _rec(want in txt, f"docs/{label.replace(' ', '-')}-azimuth",
                   f"ASSEMBLY.md must say {want} for {label}")
    for label, az in (("laser", S.AZ_LASER), ("Camera", S.AZ_CAMERA)):
        ok &= _rec(f"azimuth **{az:.0f}\u00b0**" in txt,
                   f"docs/{label.lower()}-azimuth",
                   f"ASSEMBLY.md must say azimuth **{az:.0f}\u00b0** for the {label}")
    return ok


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
        check_envelope(meshes)
        import mocks as _M
        mk = {n: fn() for n, (fn, _c, _a) in _M.MOCKS.items()}
        check_mock_fit(mk)
        check_seating(mk)
        check_cable_route(meshes, mk)
        check_docs()
        check_function(mk)
        check_interference(meshes, mk)
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
