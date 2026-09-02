# Findings against upstream CELL

Everything here came out of trying to *build* `z0r0z/cell`'s optical head
around real parts. Each one is reproducible from this repo — `cad/audit.py`
re-derives them on every run, and the arithmetic is in `cad/spec.py`.

`BOUNTY.md` asks claimants to "say what you had to change to make it work, if
anything". This is that list.

---

## 1. The 9 mm sensor standoff cannot be built with 5 mm LEDs at 45° / 12 mm

**Severity: blocking. The optical head as specified does not assemble.**

`BUILD.md` §9 fixes three numbers at once:

| | |
|---|---|
| AS7341 face above the sample | **9.0 mm** |
| White LEDs | **45°**, **12 mm** from the spot centre |
| LED part | 5 mm through-hole (`BOM.csv`) |

Take the LED axis through the read spot at 45°. Its **tip** sits at
`r = 12·sin45 = 8.49`, `z = 12·cos45 = 8.49`. A 5 mm through-hole LED is about
**8.6 mm** long behind the dome, so the body runs on to slant 20.6, i.e.
`r = 14.57`, `z = 14.57`.

The AS7341 breakout is a **30.5 × 23 mm** board that has to sit centred on the
aperture at z = 9.00…10.60. The LED axis crosses that slab at **r = 9.00…10.60**
— and the *narrowest* half-width of a 30.5 × 23 board is **11.5 mm**. So the LED
body passes through the board's footprint **at every azimuth**. There is no
rotation of the board that avoids it.

Solving for the longest LED body that would clear a board at 9 mm:

```
L_max = 9.0 / cos(45°) − 12.0 = 0.73 mm
```

**0.73 mm.** No through-hole LED exists at that length.

Reproduce:

```bash
python3 cad/audit.py | grep -A2 sensor-standoff
```

### What CELL-4B does instead

Keeps the **Ø3 × 6 aperture tube at the sample end unchanged** and raises the
sensor to **28 mm**, with a Ø5 relief shaft above the tube so the tube is still
the narrowest element in the path.

This matters because the tube — not the sensor distance — is what fixes the
3 mm spot inside the Ø4 well, which is the property §9 actually argues for
("the sensor never sees the meniscus"). What is lost is collected flux, down by
`(28/9)² ≈ 9.7×`, and that is recoverable twice over:

- `ATIME`/`ASTEP` are software. §7 already spends 281 ms on a chemistry read
  that happens once per cartridge.
- Every gate normalises against the printed white patch, which divides the
  illumination-and-collection constant out entirely. Gate 2 is explicitly a
  *white-normalised* NIR/Clear ratio; Gate 3 is a normalised difference index;
  Gate 4 is a spectral **angle**. None of them has an absolute-radiance term.

**Open question for a panel run:** whether 9.7× less flux pushes the 415 nm
channel far enough down that the Gate 3 index gets noisy. 415 nm is already
expected to sit near the ADC floor for whole blood (§7: "roughly 4,600
absorbance units per centimetre"), which is exactly why Gate 3 is a bounded
index rather than an absorbance. This is the first thing to measure.

---

## 2. The AS7341 breakout does not break out the LDR / LED driver pin

**Severity: the buying guide names a part that does not exist as described.**

`BUILD.md` §6, "Buying it":

> **AS7341** — Adafruit 4698, or a clone that brings out the **LDR/LED driver
> pin**. […] Boards that omit that pin cannot drive LED #1 directly and §9's
> wiring does not apply.

Checked against both candidate boards:

| Board | Pins actually broken out | LDR? |
|---|---|---|
| Adafruit 4698 | VIN, GND, SCL, SDA, **INT**, **GPIO** | no |
| Waveshare AS7341 | VCC, GND, SDA, SCL, **INT**, **GPIO** | no |

Sources: Adafruit's own pinout page for 4698, and the Waveshare AS7341 wiki
pinout table. Neither exposes LDR; both expose INT and GPIO instead. Adafruit
4698 is also out of stock at Adafruit and at Robu.

**Workaround, and it is cheap:** drive white LED #1 from its own GPIO through a
2N7000, exactly like LED #2. Cost is one MOSFET and one GPIO; what you lose is
the AS7341's synchronised flash/measure timing, which you then sequence in
firmware. `diagrams/wiring.svg` should be regenerated — it currently annotates
the AS7341 with "Drives white LED #1 on its LDR pin."

Note also that the Waveshare board carries **two onboard white LEDs**. They are
unusable here: they sit on the PCB beside the sensor, i.e. at near-normal
incidence, which is the geometry §9 exists to avoid ("a normal-incidence lamp
would swamp the sensor with surface reflection carrying zero chemical
information").

---

## 3. "Co-siting" the IR LED with white LED #1 is not physically possible

`BUILD.md` §9 and `BOM.csv` both say the 940 nm LED is "co-sited with LED #1".

At `LED_SLANT = 12` and `LED_BORE = 5.4`, two bores at the same slant and the
same azimuth **are the same hole**. Any real separation has to be angular. The
required separation, for a printable 1.0 mm wall between two Ø5.4 bores whose
45° sections are 7.64 mm across, is **≥ 57.4°** at the 9 mm entry radius.

CELL-4B puts the whites opposed at 0° / 180° (which §9 does require — "two
opposed LEDs cancel directional shading from droplet asymmetry") and the IR at
**90°**. All three still illuminate at 45° / 12 mm and all three are normalised
against the same printed white patch, so Gate 2's white-normalised NIR/Clear
ratio is unchanged.

---

## 4. The camera and the AS7341 both want the vertical axis

§9 draws the chemistry path with the AS7341 "0°" above the spot, and draws the
speckle path with the camera vertical at "~20 mm from the spot". Both diagrams
put their sensor on the same axis. They cannot both have it.

CELL-4B tilts the speckle path to **45°** and places it at azimuth 225°. The
angle is pinned between two hard limits:

- **≥ 42.9°**, or the bore leaves through the head's top face and lands under
  the AS7341 board;
- **≤ ~48°**, or the 25 × 24 mm camera PCB — which hangs perpendicular to the
  axis only 20 mm from the spot — swings down through the case floor. At the
  58° I first tried, its lowest corner reached **Z = 1.3 mm**, below a 2.4 mm
  floor.

45° satisfies the property §9 actually asks for: it is **68.8° off the laser's
specular lobe in 3-D**, checked in `audit.check_optics()` as a direction
comparison rather than an azimuth difference (azimuth alone flatters any design
where the two tilts differ).

---

## 5. Ø8 is too big for the speckle bore

At a 58° tilt a Ø8 bore has a **15.1 mm** elliptical cross-section, which
crowds every other bore out of a Ø52 head. Reduced to Ø6, which still
over-fills an OV5647 die (3.6 × 2.7 mm) by a wide margin.

---

## 6. TRAVEL and the two stops have to share one datum

Not an upstream error — an ambiguity that is easy to get wrong, and I did get
it wrong first.

§8 gives `travel 31.6` as "front face to read spot", and gives the stops as
insertion depths (34.6 and 42.1). Those only agree if **both** are measured
from the **outer** front face:

```
STOP2 − WELL_FROM_TIP = 42.1 − 10.5 = 31.6 = TRAVEL   ✓
STOP1 − PATCH_FROM_TIP = 34.6 −  3.0 = 31.6 = TRAVEL  ✓
```

Measuring TRAVEL from the inner wall face instead puts the read spot one wall
thickness too far in, and **both stops then read the wrong feature** — the
patch reads partly moat, the well reads partly body. Nothing about the part
looks wrong. `audit.check_cartridge()` pins both identities.

---

## 7. A Ø52 head leaves no room for the cartridge switch

**Severity: functional. The laser interlock had nothing to interlock.**

The cartridge is only exposed *inside* the case in one strip: between the inner
front wall and the optical head.

```
TRAVEL - head radius - wall  =  31.6 - 26 - 2.4  =  3.2 mm
```

3.2 mm. Everywhere else along its travel the head is directly over it. So the
cartridge-present microswitch — which upstream also makes the **hardware laser
interlock**, wired in series with the laser's supply — had nowhere to sit where
the cartridge could ever press it.

This is worth stating plainly because it is a *functional* failure, not a fit
failure: the switch sat in the case with 1.9 mm of clearance on every side and
315 geometry checks were perfectly happy. It simply was never going to be
touched. `audit.check_function()` now asserts the lever actually overlaps the
channel, at cartridge height, over the cartridge's travel.

**Fix:** the head shrinks to **Ø44**. Every bore exit stays valid — the LEDs and
the speckle path still leave through the side wall at z = 27.4, and the laser
still leaves through the top at r = 16.2 with 2.1 mm of wall — and the front
strip opens to **7.2 mm**, which takes a subminiature switch body with its
lever in the channel.

Two knock-on fixes fell out of it: the head's mounting posts moved to r = 15 at
30° off the X axis (at r = 19 they fouled the smaller skirt, and at the old
azimuths they fouled the cartridge channel), and the slot baffle gained a notch
for the switch body, which then fills the notch and keeps it light-tight.

## 8. Upstream's touch tier has no drawn optical path — and the fix is a flip

`BUILD.md` §4 says photoplethysmography happens "through the same ring bore the
cartridge sits under", and `hardware.py`'s `RealTouchSensor` says it "shares the
spectrometer head", driving the same white and IR LEDs. Upstream's CAD backs the
first half of that up exactly:

```
DISH_X = 28.5     ring / dish centre
SLOT_X = 28.5     cartridge slot centre      ONE AXIS
```

and it cuts the port as a **through-hole** — `s.hole(circ(PORT_D, …), top −
DISH_DEPTH − CEIL − 1.0, top + 1.0)` — so a finger above and a cartridge below
genuinely share one optical path.

What is never drawn is how the sensor sees both. `build-sheet.svg` labels the
head **"AS7341 / aperture Ø3.0 × 6.0 / 0° observe"** sitting above the
cartridge, facing **down**:

| | |
|---|---|
| cartridge well | **15.80** — below the sensor ✅ |
| finger on the glass | **25.72** — **above** it ❌ |

A single AS7341 aperture cannot look both ways, and the three blood LEDs are
aimed 45° **downward** at a spot 9 mm below the sensor, so neither the emitters
nor the detector face the finger. The touch tier is specified in prose and in
firmware, and has no geometry.

### What CELL-4B does: the flip-mount

One board, one pad, two orientations:

```
chip DOWN  at Z=35.8  ->  down the relief shaft, reads the cartridge
chip UP    at Z=37.4  ->  up the ring port, reads a fingertip
```

`sensor_carrier` is deliberately **symmetric** about its own mid-plane — same
four M2 holes, same central window — so it clamps the board either way up
without a second part. That symmetry is the whole trick: without it the touch
tier needs a second AS7341, which is another ~₹2,000 for a board you already
own.

`touch_collar` carries the white and IR LEDs at the **same 45° / 12 mm** the
blood tier uses, aimed **up** at the finger. It is Ø24 rather than the head's
Ø44 for a concrete reason: a 45° bore aimed at a spot above only leaves through
the **side** wall if the wall is nearer than the standoff. At Ø44 the bores
would exit the collar's underside and the LEDs could never be inserted.

The port is now a real through-hole with a Ø10.4 × 0.6 rebate at the ceiling's
inner face, so the Ø10 window drops in from below and seals the chamber —
exactly as upstream cuts it.

### And it hits the same wall as §1

This is the part worth noticing. The touch side runs into **precisely the
constraint that breaks upstream's blood side**: 5 mm LEDs at 45° / 12 mm have
to clear a 30.5 × 23 board.

```
standoff  9 mm -> LED body ends  -5.57 mm  THROUGH the board
standoff 14 mm -> LED body ends  -0.57 mm  THROUGH the board
standoff 16 mm -> LED body ends  +1.43 mm  clears
standoff 19 mm -> LED body ends  +4.43 mm  clears, and clears the carrier too
```

Same geometry, same failure, same resolution — a longer standoff. That the
constraint reappears independently on the other tier is decent evidence §1 is a
real property of the specified optics and not an artefact of how I built it.

**Cost:** the case grows to 59.8 mm tall, because the finger has to sit 19 mm
above a sensor that is itself 35.8 mm up.

## Not changed

For the avoidance of doubt, these are untouched from `BUILD.md` §8/§9:

| | |
|---|---|
| Cartridge | 51 × 14 × 2.4 |
| Well | Ø4.0 × 0.55 deep, 10.5 from the tip |
| Moat | Ø7.0 annulus, 0.4 deep |
| White patch | 4 × 4, 3.0 from the tip, coplanar with the well rim |
| Aperture | Ø3.0 × 6.0 |
| LED angle / slant | 45° / 12 mm |
| Laser angle | 30° off normal |
| Camera slant | 20 mm, lensless |
| Travel / stops | 31.6 / 34.6 / 42.1 |
| Front slot | 34.0 × 3.0, baffle 6.0 behind |

`cad/spec.py` marks each of these `[OPTICS] — DO NOT EDIT`, and notes that the
fit checks deliberately will **not** catch damage to them: a bore at the wrong
angle still assembles perfectly and reads garbage.
