"""CELL-4B dimensional contract. Every number the parts are built from.

Coordinates: X right, Y back, Z up. Origin at the centre of the case
footprint, Z = 0 at the underside of the base.

    FRONT  (-Y) .. cartridge slot, optical chamber above it
    BACK   (+Y) .. Raspberry Pi 4B, its USB-C / HDMI / audio edge
    TOP    (+Z) .. sensor dish + ring, OLED window

THREE TIERS OF NUMBER, and the difference matters:

  [OPTICS]  Taken from upstream CELL BUILD.md sections 8 and 9. These are the
            physics. Changing one changes what the instrument measures, and
            the fit checks in audit.py will NOT catch the damage -- a bore at
            the wrong angle still assembles perfectly and reads garbage.
            DO NOT EDIT.

  [HARDWARE] Measured/published dimensions of the parts being housed. Edit to
            match what you actually bought, then re-run the build. Anything
            marked VERIFY is one I could not confirm against a datasheet and
            you should check with calipers before printing.

  [DERIVED] This design's own invention -- walls, bosses, towers, clearances.
            Edit freely; audit.py checks them.
"""
from __future__ import annotations

import math

# ==========================================================================
# [OPTICS] -- upstream CELL BUILD.md 8 and 9. DO NOT EDIT.
# ==========================================================================

CART_L, CART_W, CART_T = 51.0, 14.0, 2.4     # cartridge body
WELL_D, WELL_DEPTH = 4.0, 0.55               # sample well, ~7 uL
MOAT_D, MOAT_DEPTH = 7.0, 0.40               # overflow annulus
PATCH = 4.0                                  # white reference patch, 4 x 4
PATCH_FROM_TIP = 3.0                         # patch centre from cartridge tip
WELL_FROM_TIP = 10.5                         # well centre from cartridge tip
DETENT_PROUD, DETENT_L = 0.35, 1.2           # first-stop tactile ridge
GRIP_T = 3.6                                 # grip tab thickness > SLOT_H
WINDOW_L, WINDOW_W, WINDOW_T = 12.0, 10.0, 0.10   # PET window blank
TRAVEL = 31.6                                # front face to read spot
STOP1, STOP2 = 34.6, 42.1                    # insertion at patch / at well

APERTURE_BORE, APERTURE_LEN = 3.0, 6.0       # aperture tube, 3 dia x 6 long
SENSOR_STANDOFF_UPSTREAM = 9.0               # what BUILD.md 9 states

# [FINDING -- see FINDINGS.md] Upstream's 9.0 mm standoff CANNOT be built with
# 5 mm LEDs at 45 deg / 12 mm. The LED tip sits at (r 8.49, z 8.49); its body
# runs on to (r 14.57, z 14.57). It therefore crosses the z = 9.00..10.60 slab
# at r = 9.00..10.60 -- inside the AS7341 breakout's own footprint at EVERY
# azimuth, because the narrowest half-width of a 30.5 x 23 board is 11.5 mm.
# The longest LED body that would clear a board at 9 mm is 0.73 mm.
#
# CELL-4B raises the sensor and keeps the Ø3 x 6 tube at the SAMPLE end as the
# limiting aperture, with a wider relief shaft above it. The 3 mm spot on the
# sample is therefore unchanged -- the tube still defines it. What changes is
# collected flux, down by (28/9)^2 ~ 9.7x, which is bought back with the
# AS7341's integration time (ATIME/ASTEP are software, and BUILD.md 7 spends
# 281 ms on a chemistry read that happens once) and then divided out entirely
# by the printed white patch, which every gate normalises against.
SENSOR_STANDOFF = 28.0                       # AS7341 face above the sample
SHAFT_D = 5.0                                # relief shaft, wider than the tube

# Radius within which bores are ALLOWED to merge: that volume is the optical
# chamber, not a wall. Outside it every pair must keep MIN_WALL.
CHAMBER_R = 10.0
LED_ANGLE, LED_SLANT = 45.0, 12.0            # 45 deg, 12 mm from spot centre
LASER_ANGLE = 30.0                           # 30 deg off normal
CAMERA_SLANT = 20.0                          # lensless sensor, 20 mm from spot
SLOT_W, SLOT_H = 34.0, 3.0                   # front cartridge slot
BAFFLE_OFFSET = 6.0                          # light baffle behind the slot

LED_BORE = 5.4                               # 5 mm LED slip fit
LASER_BORE = 6.4                             # 6 mm laser module slip fit
CAMERA_BORE = 6.0                            # lensless CSI clear aperture.
#   A Ø8 bore at 58 deg has a 15.1 mm elliptical section and crowds the head;
#   the OV5647 die is 3.6 x 2.7 mm, so Ø6 still over-fills the sensor.

# Azimuths, degrees from +X toward +Y. [DERIVED from the OPTICS angles]
#
# Upstream co-sites the 940 nm IR LED with white LED #1. Two co-sited bores at
# LED_SLANT = 12 and LED_BORE = 5.4 are the SAME hole, so the IR LED is moved
# to 90 deg -- perpendicular to the opposed white pair. All three still
# illuminate at 45 deg / 12 mm and all three are normalised against the same
# printed white patch, so Gate 2's white-normalised NIR/Clear ratio is
# unchanged. DOCUMENTED DEVIATION -- goes in the build writeup.
#
# The AS7341 board's LONG axis runs along X (azimuth 0/180), so its narrowest
# half-width (11.5 mm) faces azimuth 90/270 -- which is where the laser's top
# exit lands. That orientation is load-bearing; see audit bore-exit checks.
AZ_LED1, AZ_LED2, AZ_IR = 45.0, 225.0, 135.0
AZ_LASER = 270.0
AZ_CAMERA = 0.0

# Camera tilt follows from CAMERA_SLANT and the lateral offset that keeps the
# sensor clear of the aperture tower. Upstream draws the camera vertical, but
# the AS7341 already owns the vertical axis, so the speckle path is tilted off
# it. Azimuth 0 puts it 90 deg away from the laser's specular lobe (which
# leaves at AZ_LASER + 180 = 90 deg), which is the property that matters.
# Upstream fixes only the 20 mm lensless standoff and "off the specular axis";
# the ANGLE is ours, and it is pinned between two limits:
#   >= 42.9 deg, or the bore leaves through the TOP face and lands under the
#              AS7341 board;
#   <= ~48 deg, or the 25 x 24 camera PCB -- which hangs perpendicular to the
#              axis, only 20 mm from the spot -- swings down through the case
#              floor. At 58 deg its lowest corner reached Z = 1.3, below the
#              2.4 mm floor.
# 45 deg sits in the middle and puts the sensor at (r 14.14, z 19.54).
CAMERA_ANGLE = 45.0
CAMERA_OFFSET_R = CAMERA_SLANT * math.sin(math.radians(CAMERA_ANGLE))   # 16.96
CAMERA_H = CAMERA_SLANT * math.cos(math.radians(CAMERA_ANGLE))          # 10.60

LASER_SLANT = 22.0                                           # [DERIVED]

# ==========================================================================
# [HARDWARE] -- what is being housed. Edit to match your parts.
# ==========================================================================

# --- Raspberry Pi 4B --------------------------------------------------------
# [VERIFIED] against the OFFICIAL mechanical drawing,
# RP-008343-DS-1-raspberry-pi-4-mechanical-drawing.pdf, read at 3400 px.
# Board datum: x=0 is the microSD short edge, y=0 is the USB-C long edge.
PI_L, PI_W, PI_PCB_T = 85.0, 56.0, 1.4
PI_CORNER_R = 3.0                            # drawing: "CORNER RADIUS = 3.0mm"
PI_HOLE_D = 2.7                              # M2.5 clearance
PI_HOLE_INSET = 3.5                          # 3.5 from the x=0 and y=0 edges
PI_HOLE_DX, PI_HOLE_DY = 58.0, 49.0          # drawing: 58 (29+29) and 49

# Component heights above the PCB, all read off the drawing's Z= callouts.
PI_HDR_H = 8.5                               # Z=8.5, 40-pin GPIO
PI_ETH_H = 13.5                              # Z=13.5, Ethernet
PI_USB_H = 16.0                              # Z=16.0, BOTH USB stacks
PI_TALLEST = 16.0                            # <- the USB stacks, not Ethernet
PI_SOC_H = 2.4                               # Z=2.4
PI_USBC_H, PI_HDMI_H, PI_AV_H = 3.2, 3.0, 6.0    # Z=3.2 / Z=3.0 / Z=6.0
PI_FFC_H = 5.5                               # Z=5.5, the DSI and CSI FFC
#   connectors -- BOTH top-side. I first read one of these as the microSD.
# [UNVERIFIED] The drawing does not dimension how far the microSD slot hangs
# BELOW the board. ~2 mm is the usual figure for the Pi 4B's push-fit slot,
# and the inserted card adds a little. Measured clearance under the PCB is
# PI_STANDOFF, so there is margin; audit.check_port_windows() holds it against
# the floor rather than against zero. CHECK WITH CALIPERS.
PI_SD_H = 2.0                                # protrusion BELOW the PCB

PI_HDR_L, PI_HDR_W = 50.8, 5.1               # 2x20 at 2.54 -> 50.8 body
PI_HDR_CX, PI_HDR_CY = 32.5, 52.5            # header centred on the hole row

# Connector centres in the BOARD frame. The drawing dimensions the bottom edge
# as a CHAIN from the x=3.5 mounting hole: 7.7, then 14.8, then 13.5.
PI_USBC_CX = PI_HOLE_INSET + 7.7             # 11.2
PI_HDMI0_CX = PI_USBC_CX + 14.8              # 26.0
PI_HDMI1_CX = PI_HDMI0_CX + 13.5             # 39.5
PI_CSI_CX = PI_HDMI1_CX + 7.5                # 47.0, the Z=5.5 CSI FFC
PI_DSI_CX = 17.0                             # [UNVERIFIED] the other Z=5.5 FFC
PI_AV_CX = 54.0                              # 3.5 mm A/V jack, Z=6.0

# Right-edge stack, centres measured from the y=0 edge (drawing: 45.75/27/9)
PI_ETH_CY, PI_USB3_CY, PI_USB2_CY = 45.75, 27.0, 9.0
PI_ETH_W, PI_USB_W = 16.0, 15.5              # connector widths in Y
PI_PORT_PROUD = 3.0                          # how far they overhang x=85

# microSD, on the x=0 edge, underside. Drawing puts it at 3.5 + 24.5 = 28.0.
PI_SD_CY, PI_SD_W = 28.0, 12.0

# Wall-window spans, derived from the centres above with clearance.
PI_PORTS_Y0 = (5.5, 58.5)      # USB-C .. A/V, along the y=0 edge
PI_PORTS_Y0_H = 8.0            # > PI_AV_H = 6.0, the tallest of that group
PI_PORTS_X85 = (1.0, 54.0)     # Ethernet + 4x USB, along the x=85 edge

# --- OV5647 camera module (v1-style, lens REMOVED) -------------------------
# VERIFY: the bare OV5647 board is 25 x 24 mm on most clones; some are 25 x 25.
CAM_PCB_L, CAM_PCB_W, CAM_PCB_T = 25.0, 24.0, 1.0
CAM_HOLE_D = 2.2
CAM_HOLE_DX, CAM_HOLE_DY = 21.0, 12.5        # VERIFY with calipers
CAM_SENSOR = 8.5                             # bare sensor package, square
CAM_FFC_W, CAM_FFC_T = 16.0, 0.3             # ribbon at the board

# --- Waveshare AS7341 breakout ---------------------------------------------
# Wiki gives 30.5 x 23 mm and 2.0 mm mounting holes. VERIFY hole pitch.
AS_PCB_L, AS_PCB_W, AS_PCB_T = 30.5, 23.0, 1.6
AS_HOLE_D = 2.4
AS_HOLE_DX, AS_HOLE_DY = 25.5, 18.0          # VERIFY with calipers
AS_CHIP_OFF = (0.0, 0.0)                     # sensor aperture vs board centre

# --- 1.3 in I2C OLED, 4-pin (SH1106/SSD1306, 128x64) -----------------------
# VERIFY ALL FOUR: 4-pin 1.3" modules vary by vendor more than any other part
# in this build. Measure yours, edit here, re-run. audit.py re-checks the
# bezel against the window every build.
OLED_PCB_L, OLED_PCB_W, OLED_PCB_T = 35.5, 33.5, 1.6
OLED_HOLE_D = 2.4                            # M2 clearance
OLED_HOLE_DX, OLED_HOLE_DY = 30.0, 28.0      # hole pitch
OLED_ACTIVE_L, OLED_ACTIVE_W = 29.42, 14.70  # 128 x 64 active area
OLED_ACTIVE_OFF_Y = 2.0                      # active centre vs PCB centre,
#                                              positive = away from the pins
OLED_GLASS_L, OLED_GLASS_W = 33.0, 20.0      # glass panel, for the recess

# --- 650 nm laser module ----------------------------------------------------
LASER_BODY_D, LASER_BODY_L = 6.0, 10.0       # brass barrel, VERIFY

# --- discretes --------------------------------------------------------------
LED_BODY_D = 5.0
# [ASSUMED] Body length behind the dome of a 5 mm through-hole LED. This is
# the number FINDINGS.md section 1 turns on -- but the conclusion survives any
# real LED: the longest body that clears an AS7341 board at a 9 mm standoff is
# 0.73 mm, so even a 3 mm LED breaks it.
LED_BODY_L = 8.6
# Subminiature SPDT snap-action with a lever, e.g. Omron D2F-01L class.
# The 20 x 6.4 full-size part does not fit the 7.2 mm front strip. VERIFY.
SWITCH_L, SWITCH_W, SWITCH_H = 12.8, 6.0, 5.8
SWITCH_LEVER = 5.0          # how far the lever reaches past the body
SWITCH_FREE_TRAVEL = 1.2    # how far it protrudes into the channel when
#                             undepressed -- this is what the cartridge presses
RING_WINDOW_D, RING_WINDOW_T = 10.0, 0.5          # touch-tier window

# --- fasteners --------------------------------------------------------------
M25_TAP = 2.2        # self-tapping into plastic
M25_CLEAR = 2.8
M25_HEAD = 5.0
M2_TAP = 1.7
M2_CLEAR = 2.3
HEATSET_D, HEATSET_L = 3.6, 6.0     # M2.5 brass insert

# ==========================================================================
# [DERIVED] -- this design's invention. Edit freely; audit.py checks it.
# ==========================================================================

WALL = 2.4                  # 6 perimeters at 0.4
FLOOR = 2.4
CEIL = 2.4
FIT = 0.30                  # generic slip clearance
PCB_FIT = 0.40              # around a PCB in a recess
# Lap joint at the part line, NOT a centred tongue-and-groove: a 2.4 wall
# split down the middle leaves two 0.45 mm rings, which is one perimeter at a
# 0.4 nozzle and prints as air. The lap puts LAP_INNER on the lower shell and
# the rest on the upper, so neither side is below 1.0 mm.
LAP_INNER = 1.0             # lower shell's tongue thickness
LAP_H = 2.0                 # how far it rises past the part line
LAP_FIT = 0.15              # clearance between the two
MIN_WALL = 1.0              # audit fails below this

# ENV_Z 44 (was 42): the AS7341 retainer tops out at 39.2 and the ceiling
# inner face has to clear it by MIN_CLEAR, not by 0.4 mm.
ENV_X, ENV_Y, ENV_Z = 92.0, 128.0, 44.0
CORNER_R = 5.0
# The USB stacks are 16.0 mm tall and sit on a PCB at PI_PCB_Z + PI_PCB_T, so
# their tops reach 23.8. The part line has to sit ABOVE that or the port window
# would be cut in half by the joint -- the lower shell would open only the
# bottom of each USB port.
PART_LINE_Z = 26.0          # lower/upper split

# Pi bay -- the board is rotated 180 deg about Z so its GPIO header faces the
# optical chamber (short jumper runs) and its power edge faces the back wall.
PI_STANDOFF = 4.0                       # boss height above the inner floor
PI_PCB_Z = FLOOR + PI_STANDOFF          # underside of the PCB
PI_Y_PORT = ENV_Y / 2 - WALL            # board y=0 edge lands here
PI_X_ORIGIN = PI_L / 2                  # board x=0 edge maps to +PI_X_ORIGIN

# Cartridge / optical stack
SLOT_Z0 = 3.0                           # slot floor
SLOT_Z1 = SLOT_Z0 + SLOT_H              # slot ceiling
Z_SAMPLE = SLOT_Z0 + CART_T             # PET window / well rim plane = 5.4
HEAD_GAP = 0.80                         # head underside above the window
HEAD_Z0 = Z_SAMPLE + HEAD_GAP           # 6.2
# Ø44, not Ø52. At Ø52 the space between the inner front wall and the head is
# TRAVEL - R - WALL = 31.6 - 26 - 2.4 = 3.2 mm, and that strip is the ONLY
# place the cartridge is exposed inside the case -- so there was nowhere to put
# a cartridge-present switch, and the laser interlock had nothing to interlock.
# R=22 keeps every bore's exit valid (LEDs and camera still leave through the
# side at z=27.4, the laser still leaves through the top at r=16.2 with 2.1 mm
# of wall) and opens the front gap to 7.2 mm.
HEAD_DIA = 44.0
HEAD_WALL = 2.4

RS_X = 0.0                                        # read spot, X
# TRAVEL and the two stops share ONE datum: the OUTER front face. At STOP2 the
# tip is 42.1 mm in and the well, 10.5 mm behind the tip, is 31.6 mm in -- so
# the read spot is TRAVEL from the outer face, not from the inner wall face.
# Measuring it from the inner face put the spot 2.4 mm out and would have made
# both stops read the wrong feature.
RS_Y = -ENV_Y / 2 + TRAVEL                        # read spot, Y  = -32.4

Z_SENSOR = Z_SAMPLE + SENSOR_STANDOFF             # 14.4  AS7341 face
Z_LED = Z_SAMPLE + LED_SLANT * math.cos(math.radians(LED_ANGLE))       # 13.89
R_LED = LED_SLANT * math.sin(math.radians(LED_ANGLE))                  # 8.49
Z_LASER = Z_SAMPLE + LASER_SLANT * math.cos(math.radians(LASER_ANGLE)) # 24.45
R_LASER = LASER_SLANT * math.sin(math.radians(LASER_ANGLE))            # 11.00
Z_CAMERA = Z_SAMPLE + CAMERA_H                                         # 23.73
R_CAMERA = CAMERA_OFFSET_R                                             # 8.00

HEAD_BASE_Z1 = Z_SENSOR                 # = HEAD_TOP, the AS7341 deck
HEAD_TOP = Z_SAMPLE + SENSOR_STANDOFF   # 33.4, the sensor deck

# Top-face dish and ring (the sensor port), upstream's visual language
DISH_D = 47.2
DISH_DEPTH = 1.6
RING_OD = 19.0                          # collar OD; ID is the finger well
RING_ID = RING_WINDOW_D
TICKS = 60

# OLED window on the top face, behind the dish
OLED_CX, OLED_CY = 0.0, 36.0
OLED_RECESS_D = OLED_PCB_T + 0.6        # from the inside face of the ceiling

# Screw bosses -- six, clear of the Pi footprint and the optical head
BOSS_OD = 6.4
# Bosses must clear BOTH the Pi footprint and the Ø52 head. Upstream's real
# bug was two insert bosses standing inside the Pi's footprint; audit.py
# check_bosses_clear_pi() is the check that would have caught it.
BOSS_XY = [(-38.0, -58.0), (38.0, -58.0),
           (-38.0, -30.0), (38.0, -30.0),
           (-38.0, 1.0), (38.0, 1.0)]

# Vents -- BLIND pockets, never through. One through-hole and the 415 nm gate
# stops working. Upstream learned this the hard way; the depth is checked.
VENT_DEPTH = 1.2
VENT_W, VENT_L = 2.0, 14.0

PLATE_MAX = 250.0           # Bambu P1S usable bed, with margin off 256

# --- CSI ribbon route -------------------------------------------------------
# The camera sits at 20 mm from the read spot, which is r = 14.14 -- INSIDE the
# Ø52 head. So 96% of it is buried in the block, and its FFC has to get out and
# all the way back to the Pi's CSI connector at case (-4.5, 27.6..49.6, ~7.8).
# That is a 74 mm run and nothing in the design accounted for it.
#
# The route leaves the camera pocket through the head's +X side (the pocket
# already breaches the outer wall there), drops down the channel between the
# head and the wall, crosses the corridor between the head and the Pi, and
# comes up over the board. Waypoints are the ribbon's CENTRELINE.
# An FFC is FLAT -- 16 x 0.3 mm -- not a round cable. Demanding an 18 mm
# circular corridor the whole way is the wrong physical model and fails in
# places a real ribbon passes through easily: the gap between the head's back
# edge (Y = -6.4) and the Pi's near edge (Y = +5.6) is only 12 mm wide, but it
# is 20 mm TALL, so a ribbon standing on edge goes through it without touching
# anything. Each waypoint therefore carries its orientation:
#
#   'h'  flat, width horizontal   -- lying on the floor, or over the Pi
#   'v'  on edge, width vertical  -- threading a narrow but tall gap
CABLE_W = 16.0              # FFC width
CABLE_T = 0.3               # FFC thickness
CABLE_CLEAR = 1.0           # each side of the width
CABLE_BEND = 1.2            # slack across the thickness, for the bend radius

CABLE_ROUTE = [
    (24.0, -32.4, 21.0, 'h'),   # at the camera's FFC connector, in the pocket
    (31.0, -32.4, 17.0, 'v'),   # out through the head's side, turning on edge
    (31.0, -20.0, 15.0, 'v'),   # on edge down the +X channel: flat here would
    #                             need 18 mm of width and the head's shoulder
    #                             is at X = 23 with a boss beyond X = 34.8
    (31.0,   0.0, 15.0, 'v'),   # north, past the head's back edge at Y = -6.4
    ( 0.0,   0.0, 17.0, 'v'),   # west through the 12 mm head/Pi gap, on edge
    (-4.5,   0.0, 19.0, 'h'),   # lie flat at Y = 0, BEFORE turning north. Doing
    #                             this turn at Y = 4 put the on-edge ribbon's
    #                             lower half at Z = 10.5 inside the GPIO header
    (-4.5,  14.0, 21.0, 'h'),   # crossing the header, whose top is at 16.3
    (-4.5,  24.0, 21.0, 'h'),   # across the board, clear of the SoC
    (-4.5,  31.0, 15.0, 'h'),   # stops just above the CSI connector's 13.3 lid
]
# The last 2 mm is the plug going into the socket, so the corridor check stops
# above it -- otherwise the ribbon "collides" with its own destination.
CABLE_PLUG_Z = 13.3


# ==========================================================================
# derived helpers
# ==========================================================================

def pi_to_case(x, y):
    """Board-frame (x, y) -> case XY. 180 deg about Z."""
    return (PI_X_ORIGIN - x, PI_Y_PORT - y)


def pi_holes():
    xs = (PI_HOLE_INSET, PI_HOLE_INSET + PI_HOLE_DX)
    ys = (PI_HOLE_INSET, PI_HOLE_INSET + PI_HOLE_DY)
    return [pi_to_case(x, y) for x in xs for y in ys]


def polar(r, az_deg, cx=RS_X, cy=RS_Y):
    a = math.radians(az_deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


# The five optical bores, as (name, diameter, tilt, azimuth, entry height).
# Each axis passes through the read spot at Z_SAMPLE.
OPTICAL_BORES = [
    ("led1",   LED_BORE,    LED_ANGLE,    AZ_LED1),
    ("led2",   LED_BORE,    LED_ANGLE,    AZ_LED2),
    ("ir",     LED_BORE,    LED_ANGLE,    AZ_IR),
    ("laser",  LASER_BORE,  LASER_ANGLE,  AZ_LASER),
    ("camera", CAMERA_BORE, CAMERA_ANGLE, AZ_CAMERA),
]
