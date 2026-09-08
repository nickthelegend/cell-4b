"""CELL-4B printable parts. Every part is a watertight mesh in case coords.

Print orientations are set here (parts are modelled where they ASSEMBLE, and
`build.py` lays them flat on plates), so `assembly()` and the plates come from
one source and cannot drift.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, box
from shapely.ops import unary_union

import bodies as BD
import lettering as LT
import partlib as pl
from partlib import Bore, Mesh, circle, ellipse, layered, prism, rounded_rect
import spec as S


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def tilt_pad(tilt_deg):
    """Extra bore DIAMETER a tilted bore needs to print to size.

    [FINDING] optical_head() sweeps its profile in HEAD_DZ slabs and cuts each
    one with the bore's ellipse AT THE SLAB MIDPOINT. A tilted bore's axis
    moves sideways by (HEAD_DZ/2)*tan(tilt) between the midpoint and either
    face of the slab, so the hole that actually gets cut is narrower than the
    bore by that much on each side. At 45 deg that is 0.175 mm a side, which
    turned the LEDs' nominal 0.2 mm slip fit into a measured 0.07 mm -- an
    interference fit for a bought 5 mm LED. Same family as the camera pocket's
    0.13 mm; see spec.HEAD_DZ.
    """
    return 2.0 * (S.HEAD_DZ / 2.0) * math.tan(math.radians(tilt_deg))


def head_radius(z):
    """The head's outer radius at height z: Ø44 to the shoulder, then the dome.

    Module level rather than a closure inside optical_head() because the audit
    has to test bore exits against the SAME curve the head is built from. When
    it had its own copy of "R = HEAD_DIA/2" it went on reporting that the laser
    left through a flat top face that the dome had already removed.
    """
    dome_z0 = S.HEAD_TOP - S.DOME_H
    r_bot, r_top = S.HEAD_DIA / 2.0, S.DOME_TOP_D / 2.0
    if z <= dome_z0:
        return r_bot
    t = min(1.0, (z - dome_z0) / S.DOME_H)
    return math.sqrt(r_bot ** 2 - (r_bot ** 2 - r_top ** 2) * t * t)


def square_section(side, tilt_deg, az_deg, x0, y0, z0, z):
    """Horizontal cross-section of a SQUARE prism laid on a tilted axis.

    The Bore class only makes round bores. The lensless camera's sensor is a
    square package, so its seat has to be square too -- cut round, the die
    would sit on the lip of a circle instead of flat in a pocket.
    """
    run = (z - z0) * math.tan(math.radians(tilt_deg))
    cx = x0 + run * math.cos(math.radians(az_deg))
    cy = y0 + run * math.sin(math.radians(az_deg))
    major = side / math.cos(math.radians(tilt_deg))   # stretched along the lean
    r = box(-major / 2.0, -side / 2.0, major / 2.0, side / 2.0)
    r = pl.affinity.rotate(r, az_deg, origin=(0.0, 0.0))
    return pl.affinity.translate(r, cx, cy)


def _bores():
    """The five optical bores as partlib.Bore, axes through the read spot."""
    out = {}
    for name, d, tilt, az in S.OPTICAL_BORES:
        out[name] = Bore(d + tilt_pad(tilt), S.RS_X, S.RS_Y, S.Z_SAMPLE,
                         tilt_deg=tilt, az_deg=az)
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


# --------------------------------------------------------------------------
# front wordmark
#
# The mark lives in the X-Z plane, but this kernel only extrudes X-Y profiles
# along Z, and it has no CSG -- so the recess cannot be a solid subtracted from
# the wall. Instead the wall is already built by layered(), and each layer
# subtracts the wordmark's HORIZONTAL SLICE at that height. Cut finely enough
# and the stack is the letterform.
# --------------------------------------------------------------------------

_BRAND_FRONT_G = LT.text_polygon(S.BRAND_FRONT, S.BRAND_FRONT_CAP,
                                 stroke=S.BRAND_STROKE,
                                 cx=0.0, cy=S.BRAND_FRONT_Z)
_BRAND_FRONT_BOX = _BRAND_FRONT_G.bounds        # (x0, z0, x1, z1)


def _front_mark_cut(z):
    """The wordmark's slice at height z, as a cut into the FRONT wall."""
    x0, mz0, x1, mz1 = _BRAND_FRONT_BOX
    if not (mz0 <= z <= mz1):
        return None
    sl = _BRAND_FRONT_G.intersection(box(x0 - 1.0, z - 0.02, x1 + 1.0, z + 0.02))
    if sl.is_empty:
        return None
    yf = -S.ENV_Y / 2
    parts = []
    for g in (sl.geoms if hasattr(sl, "geoms") else [sl]):
        if g.is_empty:
            continue
        gx0, _, gx1, _ = g.bounds
        parts.append(box(gx0, yf - 1.0, gx1, yf + S.BRAND_DEPTH))
    return unary_union(parts) if parts else None


def _front_mark_fill(z):
    """The wordmark's slice at z, as the SOLID that fills the recess.

    The mirror of _front_mark_cut: same slice, but bounded at the face
    instead of running 1 mm proud of it, so it fills the recess and stops
    flush rather than standing on the wall.
    """
    x0, mz0, x1, mz1 = _BRAND_FRONT_BOX
    if not (mz0 <= z <= mz1):
        return None
    sl = _BRAND_FRONT_G.intersection(box(x0 - 1.0, z - 0.02, x1 + 1.0, z + 0.02))
    if sl.is_empty:
        return None
    yf = -S.ENV_Y / 2
    parts = []
    for g in (sl.geoms if hasattr(sl, "geoms") else [sl]):
        if g.is_empty:
            continue
        gx0, _, gx1, _ = g.bounds
        parts.append(box(gx0, yf, gx1, yf + S.BRAND_DEPTH))
    return unary_union(parts) if parts else None


def brand_front_inlay():
    """Second-colour solid filling the front wordmark recess, flush.

    Built on the SAME 0.2 mm ladder as the cut, evaluated at the same layer
    midpoints, so it fills the recess exactly -- no gap for the slicer to
    bridge and no interference for it to resolve.
    """
    mz0, mz1 = _BRAND_FRONT_BOX[1] - 0.3, _BRAND_FRONT_BOX[3] + 0.3
    return pl.layered(_front_mark_fill, mz0, mz1, dz=0.2)


def brand_top_inlay():
    """Second-colour solid filling the top line's recess, flush.

    A plain X-Y extrusion: the ceiling recess is one too, so this is simply
    the same polygon over the same BRAND_DEPTH.
    """
    brand = LT.text_polygon(S.BRAND_TOP, S.BRAND_TOP_CAP,
                            stroke=S.BRAND_STROKE_TOP,
                            cx=0.0, cy=S.BRAND_TOP_Y)
    return pl.prism(brand, S.ENV_Z - S.BRAND_DEPTH, S.ENV_Z)


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
# --------------------------------------------------------------------------
# head fastening  --  OUTSIDE the optical body, see FINDINGS.md section 9
#
# These used to be four posts at r=15 INSIDE the head, and that could not be
# built. Four interior positions are provably impossible: the +x/+y quadrant
# is empty at every radius and azimuth, because the camera pocket and the 45
# deg LED bore between them own that sector. The old positions left 0.08 mm of
# wall to an LED bore (MIN_WALL is 1.0) and two of them opened straight into
# the camera pocket.
#
# So the fastening leaves the optical volume entirely. Three lugs on the
# OUTSIDE of the head, at the only three azimuth zones that clear every bore,
# every component body, every insertion corridor, the cartridge and the walls:
#
#     az 115  edge clearance  2.5 mm      az 180  12.8 mm      az 305  5.9 mm
#
# az 305 only exists because the microswitch moved to -X; the CSI ribbon owns
# the +Y annulus, which is why 115 rather than 90.
#
# Three, not four, because those are the only zones that exist -- and three is
# the right number anyway: it cannot rock, and the read spot sits inside the
# triangle they form. One M2.5 per lug runs deck ear -> head lug -> shell boss,
# so a single screw column clamps the whole stack and never crosses a bore.
HEAD_LUG_R = 28.0
HEAD_LUG_AZ = [115.0, 180.0, 305.0]
LUG_PAD_D = 9.0
Z_TUBE_TOP = S.Z_SAMPLE + 9.0         # top of the Ø3 x 6 aperture tube
# The tube sits at the SAMPLE end of the spectro axis, measured ALONG it: the
# barrel runs APT_S0..APT_S0+APERTURE_LEN, the flange the millimetre above it.
#
# 4.4, not the 2.0 a vertical axis allowed. Tilted 45 deg, the Ø6 barrel's
# lowest point sits (APT_BARREL_D/2)*cos(45) = 2.12 mm BELOW its axis point, so
# at s=2.0 the barrel's lower lip came through the head's underside and into
# the cartridge. Clearing HEAD_Z0 needs s >= 4.13; 4.4 takes it with margin.
APT_S0 = 4.4
APT_S1 = APT_S0 + S.APERTURE_LEN

# Wide enough to carry the AS7341's 25.5 x 18 hole pitch across its short axis
# with wall to spare, and to buttress the pad back into the flank.
SPECTRO_BOSS_D = 16.0


def head_lugs_xy():
    return [S.polar(HEAD_LUG_R, a) for a in HEAD_LUG_AZ]


LUG_WEB_D = 7.0          # width of the web tying each lug back to the body


def _lug_pads(cx=S.RS_X, cy=S.RS_Y):
    """The three lug pads, each WEBBED back to the body, about (cx, cy).

    The web is not decoration. A bare Ø9 pad at r=28 spans r 23.5..32.5 and
    never reaches the Ø44 body at r=22, so the deck printed as four loose
    pieces and the head's lugs were floating cylinders -- and `validate()` was
    satisfied, because each piece is independently manifold. See
    audit.check_connected().
    """
    out = []
    for az in HEAD_LUG_AZ:
        px, py = S.polar(HEAD_LUG_R, az)
        # anchor the web INSIDE the body wall so it fuses rather than touches
        ax, ay = S.polar(S.HEAD_DIA / 2 - 2.0, az)
        pad = circle(LUG_PAD_D, 40, cx + px - S.RS_X, cy + py - S.RS_Y)
        anch = circle(LUG_WEB_D, 24, cx + ax - S.RS_X, cy + ay - S.RS_Y)
        out.append(pad.union(unary_union([pad, anch]).convex_hull))
    return unary_union(out)


def _lug_holes(cx=S.RS_X, cy=S.RS_Y, d=None):
    d = S.M25_CLEAR if d is None else d
    return unary_union([circle(d, 24, cx + dx - S.RS_X, cy + dy - S.RS_Y)
                        for dx, dy in head_lugs_xy()])


def optical_head():
    """One solid Ø44 block, 6.2 -> 33.4, carrying all five optical paths.

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
    dome_z0 = S.HEAD_TOP - S.DOME_H
    r_bot, r_top = S.HEAD_DIA / 2, S.DOME_TOP_D / 2

    def disc(z):
        return circle(2.0 * head_radius(z), 120, S.RS_X, S.RS_Y)
    # The sensor path is no longer vertical: it leaves along the spectro axis
    # (az 180, 45 deg) so the AS7341 can mount on the FLANK instead of the top
    # deck, which is what frees the vertical axis for the camera. Same stepped
    # column as before -- tube bore, flange counterbore, relief shaft -- just
    # stepped by distance ALONG THE AXIS rather than by height.
    _sp = dict(tilt_deg=S.SPECTRO_ANGLE, az_deg=S.AZ_SPECTRO)
    # The Ø3 x 6 aperture is now CUT INTO the head as a waist in the shaft,
    # rather than being a separate tube dropped into a counterbore. Tilting the
    # axis left no room for the tube: at s ~ 11 the spectro and LED axes are
    # only 6.3 mm apart, and a Ø10 flange (r 5.0) against a Ø5 LED (r 2.5)
    # wanted 8.3. Even a flangeless Ø6 barrel missed. A waist cut straight into
    # the head is r 1.5 and clears with 2.3 mm to spare -- and it is still the
    # limiting aperture, which is the only property that ever mattered.
    aperture = Bore(S.APERTURE_BORE, S.RS_X, S.RS_Y, S.Z_SAMPLE, **_sp)
    shaft = Bore(S.SHAFT_D + tilt_pad(S.SPECTRO_ANGLE),
                 S.RS_X, S.RS_Y, S.Z_SAMPLE, **_sp)
    # The pad the AS7341 sits on, and the buttress carrying it. Unioned along
    # the same axis, so it cannot drift from the bore it surrounds. Inside the
    # Ø44 body this adds nothing -- it only becomes material where the axis
    # leaves the flank, which is exactly where the sensor needs a seat.
    boss = Bore(SPECTRO_BOSS_D, S.RS_X, S.RS_Y, S.Z_SAMPLE, **_sp)
    _cos = math.cos(math.radians(S.SPECTRO_ANGLE))
    # fastening lives OUTSIDE the body: pads added to the profile, clearance
    # holes through them. Nothing is cut through the optical volume any more.
    pads = _lug_pads()
    lug_holes = _lug_holes()
    names = ["led1", "led2", "ir", "laser", "camera"]

    pockets = BD.head_pockets()

    # The pad face is the plane s = SPECTRO_STANDOFF, normal to the axis. At
    # height z that plane cuts the XY plane in a line; everything at or below
    # the pad is on one side of it. az 180 puts the axis along -X, so the test
    # reduces to a bound on x.
    # Pulled back one layer: layered() evaluates the profile at slab MIDPOINTS,
    # so the last slab included can overshoot the pad plane by HEAD_DZ/cos(45)
    # = 0.5 mm, and the board then lands on that overshoot instead of the pad.
    # Back it off and the staircase tips sit at or under the plane, where glue
    # can take up the rest.
    _boss_s = S.SPECTRO_STANDOFF - S.HEAD_DZ / _cos
    _diag = _boss_s / math.sin(math.radians(S.SPECTRO_ANGLE))

    def _halfplane(z, s_lim):
        """Everything at or below `s_lim` along the spectro axis, at height z."""
        x_lim = S.RS_X + (z - S.Z_SAMPLE) \
            - s_lim / math.sin(math.radians(S.SPECTRO_ANGLE))
        return box(x_lim, S.RS_Y - 80.0, S.RS_X + 80.0, S.RS_Y + 80.0)

    # The BODY has to stay off the sensor board; only the BOSS may touch it.
    # Left alone the head's top-outer corner on the -X side reaches s = 35.35,
    # past the board's plane at 35.11, and drove a 0.64 mm interference. This
    # takes a shallow chamfer off that corner and nothing else.
    _body_s = S.SPECTRO_STANDOFF - 0.8

    def profile(z):
        # The lug pads stop at the shoulder. Above it the body is narrowing, so
        # a pad at r=28 webbed back to an anchor at r=20 would lose the wall it
        # anchors INTO and print as a floating ring -- the exact failure
        # _lug_pads() documents.
        g = disc(z)
        if z <= dome_z0:
            g = g.union(pads)
        g = g.intersection(_halfplane(z, _body_s))
        s = (z - S.Z_SAMPLE) / _cos
        if s <= _boss_s:
            # Bore.section() is the cross-section of an INFINITE cylinder, and
            # at 45 deg that ellipse is 1/cos(45) times as long as the bore is
            # wide -- unioned raw it reached r=41.8 and came within 0.08 mm of
            # the upper shell. Clip it to the half-plane s <= SPECTRO_STANDOFF,
            # which is the plane of the pad face itself.
            g = g.union(boss.section(z).intersection(_halfplane(z, _boss_s)))
        for n in names:
            g = g.difference(b[n].section(z))
        # Square seat for the camera's bare sensor package, from its inner
        # face outward. Beyond it the round CAMERA_BORE carries the light.
        s_cam = (z - S.Z_SAMPLE) / math.cos(math.radians(S.CAMERA_ANGLE))
        if s_cam >= S.CAMERA_SLANT - S.CAM_SENSOR_PROUD - S.FIT:
            g = g.difference(square_section(
                S.CAM_SENSOR + 2 * S.FIT + tilt_pad(S.CAMERA_ANGLE),
                S.CAMERA_ANGLE, S.AZ_CAMERA,
                S.RS_X, S.RS_Y, S.Z_SAMPLE, z))
        # drop-in pockets for the laser barrel and the camera board, both of
        # which are wider than the bore that carries their light. Derived from
        # bodies.py, so they cannot drift from the parts they clear.
        for prof, pz0, pz1 in pockets:
            if pz0 <= z <= pz1:
                g = g.difference(prof)
        # central column, stepped along the spectro axis: tube bore, its flange
        # counterbore, then the relief shaft. The Ø3 x 6 tube is still the
        # limiting aperture -- tilting it turns the read spot into a
        # 3.0 x 4.24 ellipse, which the 12 x 10 window blank still contains.
        if APT_S0 <= s < APT_S1:
            g = g.difference(aperture.section(z))
        else:
            g = g.difference(shaft.section(z))
        return g.difference(lug_holes)

    m = Mesh()
    # The base carries the head down to the floor and subsumes what used to be
    # a 0.6 mm skirt over the cartridge -- same job, taken to the floor.
    m += _head_base()
    m += layered(profile, S.HEAD_Z0, S.HEAD_TOP, dz=S.HEAD_DZ)
    return m


def touch_post():
    """Stands a MAX30100 on the head's flat top, facing the finger well.

    The touch tier lost its flip-mount when the AS7341 moved to the flank, but
    the upper shell still has the ring port, the finger well and the window
    ledge. So the sensor does not need a new shell -- it needs to be held at
    the right height under the port it already has, and the head's flat top is
    directly below it on the same axis.

    Height is set so the sensor's OPTICAL FACE lands at the window ledge:
    everything above the post is board and chip, so the post itself is the
    remainder. Trim the top if your breakout is thicker; a shim of card under
    the board is the cheaper adjustment.

    The wire channel exists because the pin header cannot be used -- 8-10 mm
    of header does not fit under a ceiling 23.0 mm up with a 3 mm board on the
    way. Solder flying leads to the pads instead and drop them down this slot.
    """
    z0 = S.HEAD_TOP
    face = S.Z_SAMPLE + (S.ENV_Z - S.WALL - 1.0 - S.Z_SAMPLE)   # window ledge
    top = face - S.MAX30100_T - S.MAX30100_CHIP_H
    base = circle(S.TOUCH_POST_BASE_D, 64, S.RS_X, S.RS_Y)
    shaft = circle(S.TOUCH_POST_D, 48, S.RS_X, S.RS_Y)
    wire = box(S.RS_X - S.TOUCH_WIRE_W / 2, S.RS_Y - 40.0,
               S.RS_X + S.TOUCH_WIRE_W / 2, S.RS_Y - S.TOUCH_POST_D / 2 + 1.2)
    m = Mesh()
    m += prism(base.difference(wire), z0, z0 + S.TOUCH_POST_BASE_T)
    m += prism(shaft.difference(wire), z0 + S.TOUCH_POST_BASE_T - 0.02, top)
    return m


# --------------------------------------------------------------------------
# head legs -- the head stands on the case instead of hanging off three screws
# --------------------------------------------------------------------------

LEG_OD = 13.0                       # leg diameter at the floor; the glue area
LEG_CLEAR = 1.0                     # > audit MIN_CLEAR, with margin to spare


def _head_base():
    """Everything between the floor and the head's underside: the three legs,
    and the fill between them that the cartridge does not sweep.

    THE LEGS. The stock build hangs the head off one M2.5 per lug (deck ear ->
    head lug -> shell boss), so a build with no hardware has nothing holding
    it. These let it stand on the case floor and be glued there instead. Each
    is bored to drop OVER the shell's existing boss, which locates the head off
    the case rather than off a measurement and keeps the screw option intact --
    the boss is still tapped and the lug's 2.8 hole still lands on top of it.

    THE FILL. Legs alone would hold the 44 underside 3.8 mm off the bed with
    nothing under 64% of it -- a 41.8 x 43.2 mm overhang over the very face
    that clears the cartridge by HEAD_GAP, where support scars would rub. So
    the space between the legs is filled wherever the cartridge does not sweep.
    That is the old skirt's job (close the light gap over the cartridge) taken
    to its conclusion, and it leaves one 14.6 mm span to bridge instead of a
    43 mm one to support. It cannot foul the optics: every bore is within
    r 3.8 of the axis by the time it reaches HEAD_Z0, so the channel cut has
    already opened the whole light path to the sample.
    """
    disc = circle(S.HEAD_DIA, 120, S.RS_X, S.RS_Y).union(_lug_pads())
    legs = unary_union([circle(LEG_OD, 48, x, y) for x, y in head_lugs_xy()])
    prof = disc.union(legs).difference(_cart_channel(pad=0.15))
    prof = prof.intersection(
        box(-S.ENV_X / 2 + S.WALL + S.FIT, -S.ENV_Y / 2 + S.WALL + S.FIT,
            S.ENV_X / 2 - S.WALL - S.FIT, S.ENV_Y / 2 - S.WALL - S.FIT))
    prof = prof.difference(unary_union(
        [circle(S.BOSS_OD + 2 * S.FIT, 32, x, y) for x, y in head_lugs_xy()]))

    # The slot baffle crosses this. Notch it over the BAFFLE'S OWN z band --
    # with clearance below it too, because the baffle is the slot's light seal
    # and rests on the slot floor: pressing up on it opens the very leak it
    # exists to close. The base closes back up above the notch, so it bridges
    # rather than breaks and stays one solid.
    baf = place("slot_baffle", slot_baffle())
    blo, bhi = baf.bbox()
    notch = BD.xy_envelope(baf, LEG_CLEAR)
    nz0 = max(S.FLOOR, float(blo[2]) - LEG_CLEAR)
    nz1 = min(S.HEAD_Z0, float(bhi[2]) + LEG_CLEAR)

    m = Mesh()
    for z0, z1, cut in ((S.FLOOR, nz0, False), (nz0, nz1, True),
                        (nz1, S.HEAD_Z0, False)):
        if z1 - z0 < 1e-6:
            continue
        g = prof.difference(notch) if cut else prof
        if not g.is_empty:
            m += prism(g, z0, z1)
    return m


TOUCH_COLLAR_Z0 = None      # set below, after the deck thickness is known


def touch_collar():
    """Touch tier: holds the white + IR LEDs at 45 deg / 12 mm aimed UP at the
    finger, and gives the flipped sensor a clear view of it.

    Ø24 rather than the head's Ø44 for one reason: a 45 deg bore aimed at a
    spot TOUCH_STANDOFF above only leaves through the SIDE wall if the wall is
    closer than that. At Ø44 the bores would exit the collar's underside and
    the LEDs could never be inserted.
    """
    # sits above the flip-mount carrier, which clamps the board from on top
    z0 = S.Z_SENSOR_UP + CARRIER_T + 1.0
    z1 = S.TOUCH_SPOT_Z - 6.0                          # stops short of the glass
    R = S.TOUCH_COLLAR_D / 2
    body = circle(S.TOUCH_COLLAR_D, 96)
    clear = circle(S.GLASS_D + 2.0, 64)                # the finger's sight line

    bores = [Bore(S.LED_BORE, 0.0, 0.0, S.TOUCH_SPOT_Z,
                  tilt_deg=180.0 - S.LED_ANGLE, az_deg=az)
             for az in (S.AZ_TOUCH_W, S.AZ_TOUCH_IR)]

    def profile(z):
        g = body.difference(clear)
        for b in bores:
            g = g.difference(b.section(z))
        return g

    m = layered(profile, z0, z1, dz=0.35)
    return m.translate(S.RS_X, S.RS_Y, 0.0)


def sensor_deck():
    """Caps the head at Z_SENSOR and carries the AS7341. Separate part so the
    LEDs, laser and camera can all be fitted before it goes on."""
    # Ø44 plate plus three EARS out at the lug circle. The fixing screws are
    # at r=28, well outside the 30.5 x 23 board and the 35.5 x 28 carrier, so
    # nothing the AS7341 touches has a screw head under it.
    plate = circle(S.HEAD_DIA, 160).union(_lug_pads(0.0, 0.0))
    shaft = circle(S.SHAFT_D, 48)
    # The AS7341's four M2 holes are gone -- the sensor moved to the flank
    # boss. What the deck needs instead is a CUT where the board now passes
    # through its plane on the way out to that boss. Derived from the body, so
    # the slot cannot drift from the board it clears.
    holes = pl.affinity.translate(
        BD.xy_envelope(BD.as7341_body(), 0.8), -S.RS_X, -S.RS_Y)
    posts = _lug_holes(0.0, 0.0)
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
    # Only cut for the switch if one is actually going in the slot. Otherwise
    # the notch is just a hole -- see spec.SLOT_SWITCH_FITTED.
    notch = (MG.switch_footprint(0.9) if S.SLOT_SWITCH_FITTED
             else box(0.0, 0.0, 0.0, 0.0))
    # ...and the same for any head-lug boss that crosses the baffle line. The
    # az-305 boss does. Same argument as the switch: the boss is solid and
    # fills the notch, so the slot stays light-tight.
    dy = -(-S.ENV_Y / 2 + S.WALL + S.BAFFLE_OFFSET)
    cuts = [pl.affinity.translate(notch, 0.0, dy)]
    # S.FIT, not the switch's 0.9: the boss and this baffle are both printed
    # from this same CAD, so they need a printed fit, not a bought-part
    # tolerance. Every extra 0.1 mm here is 0.1 mm of light straight into the
    # chamber -- see check_slot_light().
    for lx, ly in head_lugs_xy():
        cuts.append(circle(S.BOSS_OD + 2 * S.FIT, 40, lx, ly + dy))
    prof = outer.difference(gap).difference(unary_union(cuts))
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
        #
        # Cut from the FLOOR, not from the board. The ports stand PI_PORT_PROUD
        # into the wall, so in the fitted position they are already inside it --
        # which means the board can only arrive from directly above, with the
        # port blocks travelling down inside this window. Starting the window at
        # the PCB left solid wall underneath, and the board could not be
        # inserted at all: dropping it fouled the ports, and sliding it aside
        # needed 3 mm of lateral room when the cavity offers 1.10.
        if S.FLOOR <= z <= S.PI_PCB_Z + S.PI_PCB_T + S.PI_PORTS_Y0_H:
            x0, _ = S.pi_to_case(S.PI_PORTS_Y0[1], 0.0)
            x1, _ = S.pi_to_case(S.PI_PORTS_Y0[0], 0.0)
            cuts.append(box(x0, S.ENV_Y / 2 - S.WALL - 1, x1, S.ENV_Y / 2 + 1))
        # left wall: Ethernet + 4x USB -- same reasoning as the back wall
        if S.FLOOR <= z <= S.PI_PCB_Z + S.PI_PCB_T + S.PI_USB_H:
            _, y0 = S.pi_to_case(0.0, S.PI_PORTS_X85[1])
            _, y1 = S.pi_to_case(0.0, S.PI_PORTS_X85[0])
            cuts.append(box(-S.ENV_X / 2 - 1, y0, -S.ENV_X / 2 + S.WALL + 1, y1))
        # right wall: microSD, on the board underside
        if S.FLOOR - 0.5 <= z <= S.PI_PCB_Z + S.PI_PCB_T + 0.5:
            _, cy = S.pi_to_case(0.0, S.PI_SD_CY)
            cuts.append(box(S.ENV_X / 2 - S.WALL - 1, cy - S.PI_SD_W / 2,
                            S.ENV_X / 2 + 1, cy + S.PI_SD_W / 2))
        mark = _front_mark_cut(z)
        if mark is not None:
            cuts.append(mark)
        if cuts:
            g = g.difference(unary_union(cuts))
        return g

    # The wordmark band is stepped finely -- at the wall's ordinary 0.5 mm the
    # round terminals of C, B and 4 read as a staircase.
    mz0, mz1 = _BRAND_FRONT_BOX[1] - 0.3, _BRAND_FRONT_BOX[3] + 0.3
    m += layered(wall_profile, S.FLOOR, mz0, dz=0.5)
    m += layered(wall_profile, mz0, mz1, dz=0.2)
    m += layered(wall_profile, mz1, S.PART_LINE_Z, dz=0.5)

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

    # --- optical head lugs -------------------------------------------------
    # Three, outside the optical body. One M2.5 per lug runs deck ear -> head
    # lug -> this boss, so a single screw column clamps the whole stack.
    for x, y in head_lugs_xy():
        m += _screw_column(x, y, S.BOSS_OD, S.M25_TAP, S.FLOOR, S.HEAD_Z0)

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
    assert ceil0 < ceil0 + S.GLASS_REBATE < z_finger < z_dish < z_bezel < z1, \
        "ceiling bands out of order -- see spec.ENV_Z / CEIL"

    # ceil0 -> z_finger : the ring bore is a THROUGH-hole now, exactly as
    # upstream cuts it -- one optical axis serves the finger above and the
    # cartridge below. The Ø10.4 x 0.6 rebate at the ceiling's inner face is
    # where the Ø10 window drops in from underneath, sealing the chamber.
    glass = circle(S.GLASS_D, 64, S.RS_X, S.RS_Y)
    m += prism(inner.difference(glass).difference(oled_win),
               ceil0, ceil0 + S.GLASS_REBATE)
    m += prism(inner.difference(ring_bore).difference(oled_win),
               ceil0 + S.GLASS_REBATE, z_finger)
    # z_finger -> z_dish : the Ø14 finger well is open (it bottoms here)
    m += prism(inner.difference(finger).difference(oled_win), z_finger, z_dish)
    # z_dish -> z_bezel : the dish recess opens (the finger well is inside it)
    m += prism(inner.difference(dish).difference(oled_win), z_dish, z_bezel)
    # z_bezel -> z1 : the bezel recess and the blind vents open at the top face
    # z_bezel -> z1 : split, so the last BRAND_DEPTH carries the top line.
    # Straight 2D subtraction here -- the ceiling is an X-Y extrusion, so the
    # lettering is already in the right plane (unlike the front wordmark).
    top = inner.difference(dish).difference(bezel_recess).difference(vent_g)
    brand = LT.text_polygon(S.BRAND_TOP, S.BRAND_TOP_CAP,
                            stroke=S.BRAND_STROKE_TOP,
                            cx=0.0, cy=S.BRAND_TOP_Y)
    z_mark = z1 - S.BRAND_DEPTH
    m += prism(top, z_bezel, z_mark)
    m += prism(top.difference(brand), z_mark, z1)
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

CARRIER_T = 1.4


def sensor_carrier():
    """THE FLIP-MOUNT. One AS7341, one pad, two orientations.

        chip DOWN -> down the relief shaft at the cartridge   (blood tier)
        chip UP   -> up the ring port at a fingertip          (touch tier)

    It is a frame, not a plate, and it is deliberately SYMMETRIC about its own
    mid-plane: the same four M2 holes, the same central window, so it clamps
    the board either way up without a second part. The window is sized to the
    board's aperture, not to the board, so whichever face the die is on it can
    see through.

    That symmetry is the whole trick. Without it the touch tier needs a second
    AS7341 -- another ~2,000 rupees for a board you already own.
    """
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
    "optical_head": (optical_head, "#2E3238", 1),
    "touch_post": (touch_post, "#3A4048", 1),
    "slot_baffle": (slot_baffle, "#2E3238", 1),
    "window_jig": (window_jig, "#8A9099", 1),
    "shell_lower": (shell_lower, "#3A3F46", 1),
    "shell_upper": (shell_upper, "#3A3F46", 1),
    "oled_bezel": (oled_bezel, "#2E3238", 1),
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
