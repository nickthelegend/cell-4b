# Verification status

You asked me not to say "verified" unless I mean it. So here is every
dimension in `cad/spec.py`, split by **how I actually know it**.

Three states, and only the first one is verified:

| | |
|---|---|
| **[V]** | Read off a manufacturer drawing / datasheet / official wiki that I fetched and looked at in this session. Cited. |
| **[A]** | **Assumed.** A plausible figure from a typical part. Nothing checked it. |
| **[U]** | Depends on a part whose exact model I do not know yet. |

**Nothing marked [A] or [U] should be printed against without calipers.**
`cad/audit.py` checks that the numbers are *self-consistent* — it cannot tell
you a number is *wrong*.

---

## [V] Verified

### Raspberry Pi 4B — official mechanical drawing

Source: `RP-008343-DS-1-raspberry-pi-4-mechanical-drawing.pdf`
(pip-assets.raspberrypi.com), rasterised to 3400 px and read directly.

| Dimension | Value | Where on the drawing |
|---|---|---|
| Board | 85 × 56 mm | top and right dimension lines |
| Corner radius | 3.0 mm | callout "CORNER RADIUS = 3.0mm" |
| Mounting holes | 3.5 mm from the x=0 and y=0 edges | four 3.5 dimensions |
| Hole pitch | 58 × 49 mm | "58" shown as 29 + 29; "49" |
| GPIO header height | **8.5 mm** | `Z=8.5` |
| Ethernet height | **13.5 mm** | `Z=13.5` |
| **USB stacks height** | **16.0 mm** | `Z=16.0`, on **both** blocks |
| SoC height | 2.4 mm | `Z=2.4` |
| USB-C / micro-HDMI / A/V heights | 3.2 / 3.0 / 6.0 mm | `Z=3.2`, `Z=3.0`, `Z=6.0` |
| DSI + CSI FFC height | 5.5 mm | `Z=5.5` (two of them, both top-side) |
| USB-C centre | 11.2 mm | chain from the 3.5 hole: **+7.7** |
| micro-HDMI 0 | 26.0 mm | **+14.8** |
| micro-HDMI 1 | 39.5 mm | **+13.5** |
| CSI connector | 47.0 mm | **+7.5** |
| Ethernet / USB3 / USB2 centres | 45.75 / 27.0 / 9.0 mm | right-edge dimensions |

**This pass found two real errors in my earlier model:**

1. I had `PI_TALLEST = 13.5`. The USB stacks are **16.0 mm**. Their tops reach
   Z = 23.8, which is **above the 20 mm part line I had** — the port window
   would have been sliced in half by the shell joint, opening only the bottom
   of each USB port. Part line moved to 26.0.
2. I read a `Z=5.5` callout as the microSD. Both `Z=5.5` items are **top-side
   FFC connectors** (DSI and CSI). The microSD's under-board protrusion is not
   dimensioned on the drawing at all, so it is now marked [A].

`audit.check_port_windows()` is new and now holds every connector against both
its wall window and the part line — 16 checks that did not exist before.

### AS7341 breakout pinouts

Fetched and read this session:

- Adafruit AS7341 pinout page → **VIN, GND, SCL, SDA, INT, GPIO**
- Waveshare AS7341 wiki pinout table → **VCC, GND, SDA, SCL, INT, GPIO**

Neither exposes the LDR pin that upstream's buying guide requires. That is
`FINDINGS.md` §2 and it is solid.

### Geometry that is arithmetic, not measurement

The optical layout, bore separations, cartridge stop identities, wall
thicknesses and plate fits are all *derived* from the numbers above plus
upstream's `[OPTICS]` constants. Those derivations are checked by the 125
assertions in `cad/audit.py`, and I trust them **to the extent I trust their
inputs**.

---

## [A] Assumed — measure before printing

| Constant | Current | Why it matters |
|---|---|---|
| `PI_SD_H` = 2.0 | protrusion of the microSD below the PCB | not dimensioned on the drawing; 4.0 mm of standoff gives 2.0 mm of margin |
| `PI_DSI_CX` = 17.0 | DSI connector X | cosmetic in the mock only |
| `CAM_PCB_L/W` = 25 × 24 | OV5647 clone board | sets the camera pocket |
| `CAM_HOLE_DX/DY` = 21 × 12.5 | its mounting holes | **no source at all** |
| `CAM_SENSOR` = 8.5 | bare die package | affects the bore only loosely |
| `OLED_PCB_L/W` = 35.5 × 33.5 | 1.3" 4-pin module | **highest-variance part in the build** |
| `OLED_HOLE_DX/DY` = 30 × 28 | its mounting holes | posts will miss if wrong |
| `OLED_ACTIVE_OFF_Y` = 2.0 | glass offset from PCB centre | window will be off-centre if wrong |
| `LASER_BODY_D/L` = Ø6 × 10 | brass barrel | sets the laser bore |
| `SWITCH_L/W/H` = 20 × 6.4 × 10 | SPDT microswitch | mount only |
| `LED_BODY` = 8.6 long | 5 mm through-hole LED | **load-bearing** — it is the number `FINDINGS.md` §1 turns on |

The `LED_BODY` figure deserves a note: 8.6 mm is a typical 5 mm LED body
length behind the dome. Even if yours is 7 mm, the §1 conclusion is unchanged —
the limit is **0.73 mm**, so the contradiction survives any real LED.

---

## Component placement and clearance

Added after the first pass, because bounding boxes cannot see a collision.
`cad/clearance.py` measures two things per pair, with different machinery:

- **penetration depth** — a point counts as overlapping only when it is inside
  the other solid *and* further than 0.15 mm from its surface. Without that
  tolerance every designed contact reads as a collision: a board on a deck, a
  shell on a shell, share a face, and half the sampled points on it classify
  as "inside".
- **minimum gap** — exact point-to-triangle distance (Ericson §5.1.5), both
  directions, from a sampled surface point set. Validated against four cases
  with known answers before it was trusted: 15.000, 2.500, 0.000 and 20.000.

**52 pairs measured surface-to-surface. Every emitter checked on its own axis.**

| Component | Placement | Measured |
|---|---|---|
| White LED 1 / 2 | opposed, az 45 / 225 | **12.000 mm @ 45°** from the read spot |
| 940 nm IR | az 135 | **12.000 mm @ 45°** |
| 650 nm laser | az 270 | **22.000 mm @ 30°** |
| Camera, lensless | az 0 | **20.000 mm @ 45°** |
| AS7341 | on the deck, die into the shaft | board 35.80–37.40, die to 34.80 |
| Cartridge well | at STOP2 | **on the read spot**, Y = −32.40 |
| Pi 4B | on four bosses | PCB at Z 6.40, microSD to 4.40 |
| OLED | under the ceiling | 1.90 mm clear |

Tightest ten, contacts excluded:

| Pair | Gap |
|---|---|
| cartridge ↔ slot baffle | 0.30 mm *(sliding fit)* |
| optical head ↔ slot baffle | 1.00 mm |
| camera ↔ LEDs | 1.14 mm |
| laser ↔ sensor deck | 1.19 mm |
| AS7341 ↔ optical head | 1.72 mm |
| aperture tube ↔ cartridge | 2.06 mm |
| aperture tube ↔ LEDs | 2.14 mm |
| Pi 4B ↔ shell upper | 2.20 mm |
| AS7341 ↔ laser | 2.27 mm |
| sensor carrier ↔ shell upper | 2.40 mm |

### The CSI ribbon — the gap the render exposed

"Where is the camera?" turned out to be the right question. It is at r = 14.1
from the read spot, **inside** the Ø52 head, so **96% of its vertices sit
within the head's outer radius** and it is invisible from every angle. That is
forced by the optics: upstream fixes the lensless sensor at 20 mm from the
spot, and at 45° that lands inside the block.

The consequence was not cosmetic. **Nothing in the design accounted for the
ribbon.** No route, no channel, no check — the camera could not have been
connected.

`CABLE_ROUTE` now declares a 9-waypoint centreline, and each waypoint carries
the ribbon's orientation, because an FFC is **flat** (16 × 0.3 mm), not round:

| | |
|---|---|
| `'h'` | flat, width horizontal — on the floor, or over the Pi |
| `'v'` | on edge, width vertical — threading a narrow but tall gap |

That distinction is load-bearing. Demanding an 18 mm round corridor fails in
the gap between the head's back edge (Y = −6.4) and the Pi's near edge
(Y = +5.6): it is only **12 mm wide but 20 mm tall**, so a ribbon on edge goes
through untouched while a round cable cannot.

**Route: 110 mm.** A 150 mm ribbon is comfortable; 100 mm will not reach.

Three real blockages found and fixed while getting it clear:

1. The descent down the +X channel was flat, wanting 18 mm of width — the
   head's shoulder is at X = 23 and a boss starts at X = 34.8. Turned on edge.
2. Turning north at Y = 4 put the on-edge ribbon's lower half at **Z = 10.5,
   inside the GPIO header** (top 16.3). The turn now happens at Y = 0.
3. The microswitch sat **0.33 mm** from the ribbon. Moved to −X entirely.

One "failure" was the check being wrong, not the route: the last few samples
land inside the CSI socket, because that is where the ribbon is *going*. The
plug neighbourhood is now excluded and replaced with a positive
`cable/reaches-connector` assertion.

### What this pass found

Seven more defects, all of which would have printed:

1. **Four Ø2.2 spikes on the underside of the case.** Pi standoff pilot holes
   added as *solid* prisms below the floor. The case would not sit flat.
2. **The head's mounting posts drove 0.4 mm into its own skirt** — post OD 6.4
   at r = 21 reaches r = 22.2 against a skirt starting at 23.0. Moved to r = 19.
3. **The slot baffle drove into the head skirt.** A baffle tall enough to look
   right on its own hits the skirt; it now stops 1.0 mm below it.
4. **The camera board and the laser barrel overlapped** at 45° azimuth
   separation. Azimuths reallocated: LEDs to 45/135/225, camera to 0.
5. **The sensor deck's laser cutout was sized off the light bore, not the
   barrel** — 0.69 mm clearance on a Ø6 barrel. Now sized off the body.
6. **The AS7341 retainer sat 0.4 mm under the ceiling.** Case raised to 44 mm.
7. **The microswitch had nowhere to go.** A 20 mm body across X does not fit
   between the Ø52 head and the wall, and every azimuth clearing the head hit
   a corner boss. Turned 90° and placed at (34, −44).

Also fixed structurally: several parts were modelled in their own frame rather
than assembly coordinates, so the checker had been comparing *unplaced* parts.
`parts.place()` is now the single source of truth for where each one goes, and
the laser and camera pockets in the head are **derived from** the component
bodies in `cad/bodies.py` — change a board dimension and the pocket that
clears it changes with it.

---

## [U] Blocked on which part you actually bought

**The AS7341 board.** You said the spectral sensor you received is "kinda
different". These four numbers set the sensor deck's mounting pattern and
nothing else in the build can substitute for them:

```
AS_PCB_L, AS_PCB_W   currently 30.5 x 23.0   (Waveshare wiki figure)
AS_HOLE_DX, AS_HOLE_DY  currently 25.5 x 18.0   (my assumption, no source)
AS_PCB_T             currently 1.6
AS_CHIP_OFF          currently (0, 0)  -- where the sensor die sits on the board
```

`AS_CHIP_OFF` is the one that actually matters optically: the die has to sit
over the aperture. If it is off-centre on your board, the deck's hole pattern
has to shift by the same amount, or the instrument reads the wrong spot.

**Tell me the exact board** — vendor and a photo of both faces, or a link — and
I will set these from its real pinout drawing.

---

## Phasing, given the sensor is unresolved

Nothing except the sensor deck depends on the AS7341. So the build splits
cleanly and you can start printing today:

| Phase | Parts | Blocked on AS7341? |
|---|---|---|
| **1** | `shell_lower`, `shell_upper` — Pi 4B fit, ports, cartridge slot | no |
| **2** | `cartridge` × 20, `cartridge_reference`, `cartridge_null`, `window_jig` | no |
| **3** | `optical_head`, `aperture_tube`, `slot_baffle` — LEDs, laser, camera | no |
| **4** | `sensor_deck`, `sensor_carrier` | **yes** |
| **5** | `oled_bezel` + OLED posts | no, but measure the OLED first |

Phase 1 is also the cheapest way to find out whether my Pi numbers are right:
print `shell_lower` alone, drop the board in, check the four bosses and the
port windows. That is one 92 × 128 part, a couple of hours, and it validates
every [V] number above against the board in your hand.
