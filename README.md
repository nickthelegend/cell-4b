# CELL-4B

A blood-gated, airgapped hardware wallet on a Raspberry Pi **4B** — a fork of
[z0r0z/cell](https://github.com/z0r0z/cell) rebuilt around a board you can
actually buy.

The device signs Ethereum transactions, but only after proving that a living
human is present: either a **pulse** at the touch tier, or **fresh blood** in a
cartridge. It never touches the network. Only pixels cross the airgap — a QR
code in, a QR code out.

```
92 × 128 × 42 mm   ·   12 printed parts   ·   6 optical gates   ·   0 network interfaces
```

Upstream's shells are hard-coded to a 65 × 30 mm Pi Zero bay; the Pi Zero 2 W is
unobtainable in India. Everything upstream calls **optics** is preserved exactly.
Everything it calls **derived** — walls, bosses, bays, towers — is rebuilt.

---

## The idea

A hardware wallet proves you have a *key*. This one also proves you are *alive*.

The instrument is a reflectance spectrometer and a laser speckle sensor pointed
at a 3 mm spot. To authorise a signature it has to see something that behaves
like whole blood, across six independent gates:

| gate | measures | passes when |
|---|---|---|
| **G1** return signal | reflectance vs the cartridge's printed white patch | ≤ 0.35 — dark, not an empty well |
| **G2** cellular scatter | NIR / Clear ratio | ≥ 2.2 — cells scatter, solutions don't |
| **G3** haem Soret band | absorption at **415 nm** | ≥ 0.75 — porphyrin, not just red dye |
| **G4** spectral shape | angle against oxygenated whole blood | ≥ 0.995 |
| **G5** free motion | laser speckle decorrelation *D* | ≥ 0.6 — still flowing |
| **G6** motion arrested | *D* after clotting | ≤ 0.25 — it clotted, so it was alive |

G5 and G6 together are the interesting pair: **liquid, then clotting** is very
hard to fake, because it requires the sample to change over time in the way only
real blood does.

The pulse tier is simpler and reusable — a MAX3010x reads bpm, confidence and
perfusion, and refuses anything outside 40–200 bpm or a perfusion ratio outside
0.05–8.0. A perfusion of 10 % is not a heart; it's a finger moving.

## Layout

```
cad/          pure-python CAD kernel -> watertight shells, manifold validator,
              STL/GLB writers, angled-bore mesher. spec.py is the dimensional
              contract; every number tagged [OPTICS] / [HARDWARE] / [DERIVED]
firmware/     what runs on the Pi: gates, spectrometer, pulse, signing, console
firmware/diag/ single-question bench diagnostics (see its own README)
bridge/       browser extension + dApp: captures a transaction, renders a QR,
              never holds a key
viewer/       three.js viewer, vendored, works offline
out/stl/      printable STLs
FINDINGS.md   what broke when upstream's head met real parts
ASSEMBLY.md   step by step
VERIFICATION.md  what has actually been measured, versus claimed
```

## Quick start

**Build the parts:**

```bash
python3 -m venv .venv && .venv/bin/pip install shapely numpy
.venv/bin/python cad/build.py          # audit -> STLs -> plates -> MANIFEST.md
```

`cad/build.py` **refuses to write anything** if `cad/audit.py` reports a failure,
so any plate reaching your slicer has already passed every check.

**Run the instrument:**

```bash
.venv/bin/python firmware/gate_console.py
```

Full-screen live console on the Pi's own display: camera, live colour with the
eight-band spectrum, pulse gate, G1–G6, and the speckle plot with both gate
thresholds shaded.

```
D  chemistry    S  speckle    T  sign with pulse    L  dry/live    W  lights    Q  quit
```

`D` runs the chemistry read in two stages — the white patch at the first stop
(34.6 mm), then **space**, then the sample well at the second (42.1 mm). Both
reads are needed because every chemistry gate is a **ratio**, which is also why
they survive dim emitters: 120 Ω resistors change the illumination constant,
and a ratio divides it out.

## The airgap

The bridge half never holds a key.

```
browser ──► extension ──► QR on screen ──► [ CELL-4B camera ]
                                                   │
                                            gates + signature
                                                   │
[ browser camera ] ◄── QR on the OLED ◄────────────┘
```

The extension announces itself over **EIP-6963** as a walletless provider
holding only an address. It refuses `personal_sign` (4200), refuses to switch
chains (4902), and refuses calldata it cannot read (4100) unless blind signing
is explicitly enabled.

When blind signing *is* enabled, `blindtx.py` renders **"UNREAD CONTRACT CALL"**
plus a hash of the calldata, rather than a friendly summary it cannot justify.
The principle: **refuse to pretend, rather than refuse to sign.** Flip one bit
of calldata and the displayed hash changes.

## How the geometry is checked

Watertight is not the same as buildable, so the audit runs two kinds of check.

**Analytic** — arithmetic on `spec.py`: bore separation at each entry, bore
exits, the six cartridge distances, Pi hole pitch, wall minimums, blind-vent
depth, OLED window inside the PCB, the speckle axis vs the specular lobe in 3-D.

**Sampled** — point-in-solid against real triangles, used where only the
geometry can answer: the cartridge corridor stays open to stop 2, the Pi and its
13.5 mm port stack have somewhere to be, no point is solid in both shells at
once, every part fits the bed.

Bugs the audit caught, each of which would have been a wasted print:

- two screw bosses standing **inside the Pi's footprint**
- a 0.45 mm wall at the part line, from splitting a 2.4 mm wall for a centred
  tongue-and-groove (now a lap joint, 1.0 / 1.25)
- a ceiling built in the wrong Z order, because the finger well is *deeper* than
  the dish it sits in — one prism came out inverted
- the ring collar with `RING_OD` equal to the well diameter, so it was an empty
  solid
- the camera board swinging **below the case floor** at 58°
- the read spot one wall thickness too far in, which silently makes **both
  cartridge stops read the wrong feature**

## What changed from upstream, and why

Upstream's optical head **cannot be assembled as specified**. At a 9 mm sensor
standoff with 5 mm LEDs at 45° / 12 mm, the longest LED body that would clear the
AS7341 board is **0.73 mm**. Full derivation and four other findings in
**[FINDINGS.md](FINDINGS.md)**.

CELL-4B keeps the Ø3 × 6 aperture at the sample end — which is what actually
fixes the 3 mm spot — and moves the sensor to 28 mm on the **flank** at 60°,
behind a wider relief shaft, freeing the vertical axis for the camera.

Untouched: cartridge and well geometry, the white patch, the aperture, 45°/12 mm
LEDs, the 30° laser, the 20 mm lensless camera standoff, travel and both stops.

## Hardware

| | |
|---|---|
| Raspberry Pi 4B | 85 × 56, on 58 × 49 mm bosses, GPIO header facing the optics |
| AS7341 spectrometer | flank boss, 60° off vertical, 28 mm from the read spot |
| 3 × 5 mm LED | 2 white opposed + 1 × 940 nm IR, all at 45° / 12 mm |
| 650 nm laser module | 30° off normal, hardware-interlocked to the cartridge switch |
| OV5647 camera | **lens removed** — a bare die, 45° / 20 mm, 68.8° off the specular lobe |
| MAX3010x | touch tier, pulse and perfusion |
| 1.3" I²C OLED | 4-pin, under the top face with a printed bezel |
| Cartridges | upstream's 51 × 14 × 2.4, unchanged |

Emitters are **sink-driven with 120 Ω and no transistors** — the GPIO sinks the
current, so a lit LED means its pin is *low*. Longer integration buys back what
the resistors cost.

## Notes from the bench

Things that cost real time, recorded so they don't cost it again:

- **The AS7341's channels are a `Reading`, its gain is an enum index.** A `gain`
  of 8 means *index* 8 — 128× — not 8×. `GAIN_STEPS` maps multipliers to indices.
- **A brownout leaves the chip ACKing on I²C with its ADC off**, and every
  channel then reads a hard zero — indistinguishable from a dark chamber, which
  is the reading this device must trust. `Spectrometer.wake()` now forces
  `PON|SP_EN` on construction and raises if it can't.
- **One I²C bus, two libraries, two `busio.I2C` objects.** Their internal locks
  guard nothing against each other, and pulse traffic interleaving into an
  AS7341 SMUX-then-read returns zeros. Everything on the bus takes one lock.
- **The signature fields of an EIP-1559 transaction start at index 9**, not 8 —
  index 8 is `accessList`. Off by one recovers a valid signature for the *wrong
  address*.
- **A QR format string is written MSB-first.** LSB-first produces codes that
  scan 0 of 4 times and look plausible.
- **Sink drive means the short leg goes to the GPIO.** A leg shorting the rail
  will reset the board and can take the pin's output driver with it.

## Credits

- Instrument, physics, and every `[OPTICS]` number:
  [z0r0z/cell](https://github.com/z0r0z/cell) (CC0)
- CAD kernel adapted from
  [nickthelegend/orchestrator-pad](https://github.com/nickthelegend/orchestrator-pad)
  `cad/partlib.py`
- three.js r160, vendored under `viewer/vendor/`
