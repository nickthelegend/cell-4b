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
