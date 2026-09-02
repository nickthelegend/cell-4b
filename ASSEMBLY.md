# CELL-4B assembly

Open the viewer alongside this; every step names the part as it appears in the
parts list.

```bash
cd cell4b && python3 -m http.server 8731
# then http://localhost:8731/viewer/index.html
```

Coordinates: **X** right, **Y** back, **Z** up. The **front** (−Y) is the
cartridge slot. The **back** (+Y) carries the Pi's USB-C, HDMI and audio.

---

## 0. Before you print

**Measure these five and edit `cad/spec.py`, then re-run the build.** They are
the ones I could not confirm against a datasheet, and they are marked `VERIFY`
in the file:

| Constant | Default | What to measure |
|---|---|---|
| `OLED_PCB_L/W`, `OLED_HOLE_DX/DY` | 35.5 × 33.5, 30 × 28 | 1.3" 4-pin OLED modules vary by vendor more than any other part here |
| `OLED_ACTIVE_OFF_Y` | 2.0 | glass centre offset from PCB centre, away from the pins |
| `CAM_HOLE_DX/DY` | 21.0 × 12.5 | your OV5647 clone's mounting holes |
| `AS_HOLE_DX/DY` | 25.5 × 18.0 | Waveshare AS7341 hole pitch |
| `LASER_BODY_D/L` | Ø6 × 10 | the brass barrel on your module |
| `PI_SD_H` = 2.0 | how far the microSD hangs below the board — not on the official drawing |
| `CAM_PCB_L/W` | 25 × 24 | sets the drop-in pocket the camera lowers into |

```bash
python3 cad/build.py     # re-runs the audit, then rewrites STLs + plates
```

The build **refuses to write** if any check fails, so a plate that reaches your
slicer has already passed all 304.

---

## 1. Print

Four plates, all inside the P1S bed. `MANIFEST.md` carries the settings table.

| Plate | Parts | Filament |
|---|---|---|
| 1 | `shell_lower` | black |
| 2 | `shell_upper` | black |
| 3 | `optical_head`, `sensor_deck`, `aperture_tube`, `slot_baffle`, `oled_bezel`, `sensor_carrier`, `window_jig` | black |
| 4 | 20 × `cartridge` + `cartridge_reference` + `cartridge_null` | **white** |

Three rules that are not style preferences:

1. **Plate 4 in one session, from one white spool, ironing ON.** The 4 × 4 mm
   patch on every cartridge is the photometric reference every gate normalises
   against. Switching filament mid-batch walks your thresholds silently.
2. **Cartridges well-side up, no supports.** The well floor and the patch must
   both be top surfaces or ironing does nothing for them.
3. **`aperture_tube` flange DOWN.** The flange seats in the head's counterbore
   and the barrel hangs at the standoff, rather than being glued at it.

Then **paint every bore in `optical_head` and `aperture_tube` matte black**,
and the inside of the head's chamber. This is not cosmetic: §9's light-tightness
test is Clear < 0.5 % of LEDs-on at 10,000 lux, and thin dark PLA passes more
light than you expect.

---

## 2. Lower shell

1. Four **M2.5 × 6 self-tapping** screws hold the Pi. The bosses are already at
   the 58 × 49 mm pitch — check with calipers before you force anything.
2. Drop the **Pi 4B in GPIO-header-forward**: the header faces the front (−Y),
   toward the optical head, so the jumper runs are short. USB-C, HDMI and audio
   end up at the back wall; Ethernet and USB on the left; microSD on the right.
3. Press `slot_baffle` into its slot behind the front mouth, 6 mm back.
4. Four **M2.5 heat-set inserts** into the corner bosses, 6 mm deep.

## 3. Optical head — the part that matters

Fit everything into the head **before** it goes into the shell, and before
`sensor_deck` caps it. Once the deck is on, the LED bores are unreachable.

1. **Three LEDs**, from outside, into the three 45° side bores:
   - azimuth **45°** — white LED #1
   - azimuth **225°** — white LED #2 (opposed, cancels droplet shading)
   - azimuth **135°** — **940 nm IR**
   Push each until the dome bottoms at slant 12. Leads trail out behind.
2. **Laser** into the 30° bore at azimuth **270°**. This is the one bore that
   leaves through the **top** face, which is why the AS7341's narrow side has
   to face 90/270 — do not rotate the board.
3. **Camera** on the 45° bore at azimuth **0°**, lens **removed**, sensor
   facing the spot at 20 mm. It ends up **inside** the head, in a drop-in
   pocket cut for it — lower it straight down before the deck goes on.
4. **Route the CSI ribbon before the deck goes on.** This is the step that is
   easy to leave until too late. The camera sits at r = 14.1 mm from the read
   spot — **inside** the Ø44 head — so 96% of it is buried and its ribbon
   starts in a blind pocket. It leaves through the head's +X side wall, turns
   **on edge** to drop down the channel between the head and the case wall,
   crosses the 12 mm gap between the head and the Pi still on edge, then lies
   **flat** again and goes up and over the GPIO header into the CSI socket.
   That is a **110 mm** run; a 150 mm ribbon is comfortable, a 100 mm one will
   not reach. `cad/spec.py: CABLE_ROUTE` has the waypoints and
   `audit.check_cable_route()` verifies the whole corridor is clear.
5. **`aperture_tube`**, flange up, into the central counterbore.
6. **`sensor_deck`** on top. Its three **ears** line up with the head's three
   lugs — see below. Nothing screws down through the middle of the deck, so
   the AS7341 lands on a flat face.
7. **AS7341** on `sensor_carrier`, chip **DOWN** over the relief shaft, then
   onto the deck. **Long axis along X.**

Then drop the head onto the **three lugs** in `shell_lower` and screw down.
Its skirt closes to 0.2 mm above the cartridge, everywhere except the corridor
the cartridge itself sweeps.

**Three lugs, not four, and they are outside the head — not through it.** The
fastening used to run through the optical body and could not be built: two of
the four posts opened straight into the camera pocket, and all four left
0.08 mm of wall to an LED bore where the minimum is 1.0. Four interior
positions are impossible at any radius, because the camera pocket and the 45°
LED bore between them own that whole quadrant. So the screws moved out:

| Lug | Azimuth | Clearance to the nearest thing |
|---|---|---|
| 1 | **115°** | 2.5 mm (the CSI ribbon owns +Y, which is why not 90°) |
| 2 | **180°** | 12.8 mm |
| 3 | **305°** | 5.9 mm (only free because the switch moved to −X) |

One M2.5 per lug runs **deck ear → head lug → shell boss**, so a single screw
column clamps the whole stack and never crosses a bore. Three is also the right
number: it cannot rock, and the read spot sits inside the triangle they form.
See `FINDINGS.md` §9.

### Buy these, and do not over-torque them

The screw column is 33.4 mm of stack, so the lug screws are **long**:

| Screw | Length | Passes through | Threads into | Engagement |
|---|---|---|---|---|
| Head lugs × 3 | **M2.5 × 35** | deck ear 2.4 + head lug 27.2 | shell boss | **3.8 mm** |
| AS7341 × 4 | **M2 × 8** | carrier 1.4 + board 1.6 | sensor deck | **2.4 mm** |
| Pi × 4 | M2.5 × 6 | — | shell bosses | 4.0 mm |
| Lid × 4 | M2.5 × 8 | counterbores | shell bosses | — |

Engagement on the lugs is 1.5 × diameter and on the AS7341 1.2 ×, which is
below the usual 2 × rule. The loads are grams, so it holds — but these are
self-tapped into PLA, so run them in **by hand** and stop at first resistance.
A stripped boss is not repairable. `audit.check_screws()` recomputes every
number in this table from the geometry, so it cannot drift from the parts.

The microswitch sits on the **−X** side of the slot. It moved there to free
the 305° lug; the cartridge channel is symmetric, so nothing else changed.

**Wire the laser interlock in hardware.** The cartridge microswitch contacts go
**in series with the laser module's supply**, not in the GPIO6 gate line. An
interlock the firmware can talk its way past is not an interlock.

## 3b. Touch tier — the flip-mount

The **same AS7341** serves both tiers. Which one you are building decides which
way up it goes:

| Tier | Board | Reads |
|---|---|---|
| **Blood** | chip **DOWN** on the deck at Z 35.8 | the cartridge, down the relief shaft |
| **Touch** | chip **UP** at Z 37.4 | a fingertip, up the ring port |

`sensor_carrier` is symmetric — same four M2 holes either way round — so it
clamps the board in both orientations without a second part.

For touch, add:

1. **`touch_collar`** on top of the carrier. Two 45° bores, inserted from
   outside:
   - azimuth **0°** — white LED (this is the red channel)
   - azimuth **180°** — **940 nm IR**
   Push each until it bottoms at slant 12, same as the blood LEDs.
2. **Ø10 × 0.5 window** into the Ø10.4 × 0.6 rebate at the ceiling's **inner**
   face — it goes in from underneath, and it seals the chamber.

The finger presses on that glass through the ring bore. The port is a
**through-hole**: one optical axis serves the finger above and the cartridge
below, which is how upstream cuts it too.

Wire the touch LEDs to their own GPIOs — the blood LEDs point the other way and
cannot be shared.

## 4. Upper shell

1. **OLED** on the four posts under the ceiling, glass up to the window.
2. **`oled_bezel`** into the top-face recess — it masks the window down to the
   29.42 × 14.7 mm active area.
3. **Ø10 × 0.5 window** into the seat at the bottom of the finger well.
4. Close the lap joint and four M2.5 × 8 through the counterbores.

## 5. Wiring

| Pin | Function |
|---|---|
| GPIO2/3 | I²C1 — AS7341 at 0x39 |
| GPIO12 | white LED #1 — 2N7000, 68 Ω to **+5 V** |
| GPIO16 | white LED #2 — 2N7000, 68 Ω to **+5 V** |
| GPIO23 | 940 nm IR — 2N7000, **47 Ω to +3V3** |
| GPIO6 | laser gate — 2N7000, interlocked through the microswitch |
| GPIO22 | cartridge microswitch, internal pull-up, LOW when seated |
| CSI | camera |

GPIO16 is CELL-4B's addition — upstream drove white LED #1 from the AS7341's
LDR pin, which no available breakout exposes (`FINDINGS.md` §2).

**The two rails are different rails.** 68 Ω on +5 V gives a white LED ≈ 28 mA;
the same resistor on +3V3 gives ≈ 3 mA and it barely lights. 47 Ω on +3V3 gives
the 940 nm part ≈ 41 mA; on +5 V it passes ≈ 78 mA and cooks it.

Only **one** 2.2 kΩ pull-up pair on the I²C bus. With a single breakout you
keep the one it ships with — the classic first-build failure needs two boards
fighting each other, which does not apply until you add the ATECC.

---

## 6. First light

```bash
sudo raspi-config          # Interface Options -> I2C -> enable
sudo i2cdetect -y 1        # AS7341 answers at 0x39
```

Then work the milestones in upstream `BUILD.md` §15:

- **M2** — AS7341 on a white card, < 1 % RSD over 100 reads
- **M3** — 20 cartridges, < 3 % white-patch spread. Fix your printer here
- **M4** — chamber light-tight, Clear < 0.5 % at 10,000 lux
- **M5** — **415 nm separates red food dye from your blood.** The "it works"
  moment, and the first thing this whole build exists to answer
- **M6** — 600 s speckle series, both classes
- **M7** — spoof panel, `thresholds.json`, ROC. This is the partial claim

Because the sensor sits at 28 mm rather than 9 mm, **raise `ATIME`/`ASTEP`
before M2** and confirm the 415 nm channel is comfortably off the ADC floor on
a white card. If it is not, say so in the writeup — that is a result.

Read upstream `SAFETY.md` before any of this involves blood. One device, one
person, one lancet per use, sharps container.
