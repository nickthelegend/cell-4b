# CELL-4B

A Raspberry Pi **4B** enclosure for [z0r0z/cell](https://github.com/z0r0z/cell),
generated from Python. Upstream's shells are hard-coded to a 65 × 30 mm Pi Zero
bay; the Pi Zero 2 W is unobtainable in India, so this is the same instrument
around a board you can actually buy.

Everything upstream calls **optics** is preserved exactly. Everything it calls
**derived** — walls, bosses, bays, towers — is rebuilt.

```
92 × 128 × 42 mm    ·    12 printed parts    ·    4 plates, all inside a P1S bed
```

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install shapely numpy
.venv/bin/python cad/build.py          # audit -> STLs -> plates -> MANIFEST.md
python3 -m http.server 8731            # then localhost:8731/viewer/index.html
```

`cad/build.py` **refuses to write anything** if `cad/audit.py` reports a
failure, so any plate that reaches your slicer has already passed every one
of them. `out/manifest.json` records the count for the build you actually ran.

## What's in it

| | |
|---|---|
| Raspberry Pi 4B | 85 × 56, on 58 × 49 mm bosses, GPIO header facing the optics |
| AS7341 spectrometer | on the sensor deck, chip down over the aperture |
| 3 × 5 mm LED | 2 white opposed + 1 × 940 nm IR, all at 45° / 12 mm |
| 650 nm laser module | 30° off normal, hardware-interlocked to the cartridge switch |
| OV5647 camera | lens removed, 45° / 20 mm, 68.8° off the specular lobe |
| 1.3" I²C OLED | 4-pin, under the top face with a printed bezel |
| Cartridges | upstream's 51 × 14 × 2.4, unchanged |

## Layout

```
cad/partlib.py   pure-python CAD kernel: shapely profiles -> watertight shells,
                 manifold validator, STL + GLB writers, angled-bore mesher
cad/spec.py      THE dimensional contract. Every number, tagged [OPTICS] /
                 [HARDWARE] / [DERIVED]
cad/parts.py     the 13 printable parts
cad/mocks.py     dimensional mock-ups of the bought parts, placed where they assemble
cad/audit.py     fit, function, light and doc-drift checks
cad/build.py     STLs, GLBs, plates, MANIFEST.md
viewer/          three.js viewer (vendored, works offline)
out/stl/         printable STLs
FINDINGS.md      what broke when I tried to build upstream's head around real parts
ASSEMBLY.md      step by step
MANIFEST.md      generated: sizes, settings, orientations, filament
```

## How the geometry is checked

Watertight is not the same as buildable, so the audit runs two kinds of check.

**Analytic** — arithmetic on `spec.py`. Bore separation at each entry, bore
exits, the six cartridge distances, Pi hole pitch, wall minimums, blind-vent
depth, OLED window inside the PCB, the speckle axis vs the specular lobe in 3-D.

**Sampled** — point-in-solid against the real triangles, by projecting each
triangle to XY and counting crossings. Used where only the geometry can answer:

- the cartridge corridor stays open from the front face to stop 2
- the Pi board and its 13.5 mm port stack have somewhere to be
- no point is solid in both shells at once
- every part fits the bed

Things the audit caught during development, each of which would have been a
wasted print:

- two screw bosses standing **inside the Pi's footprint** — the same class of
  bug upstream records fixing in its own generator
- a 0.45 mm wall at the part line, from splitting a 2.4 mm wall down the middle
  for a centred tongue-and-groove (now a lap joint, 1.0 / 1.25)
- a ceiling built in the wrong Z order, because the finger well is *deeper*
  than the dish it sits in — one prism came out inverted
- the ring collar modelled with `RING_OD` equal to the well diameter, so it was
  an empty solid
- the camera board swinging **below the case floor** at a 58° tilt
- the read spot placed one wall thickness too far in, which silently makes
  **both cartridge stops read the wrong feature**

## What changed from upstream, and why

Short version: upstream's optical head **cannot be assembled as specified**. At
a 9 mm sensor standoff with 5 mm LEDs at 45° / 12 mm, the longest LED body that
would clear the AS7341 board is **0.73 mm**. Full derivation, plus four other
findings, in **[FINDINGS.md](FINDINGS.md)**.

CELL-4B keeps the Ø3 × 6 aperture tube at the sample end — which is what
actually fixes the 3 mm spot — and raises the sensor to 28 mm behind a wider
relief shaft.

Untouched: cartridge and well geometry, the white patch, the aperture, 45°/12 mm
LEDs, the 30° laser, the 20 mm lensless camera standoff, travel and both stops.

## Credits

- Instrument, physics, and every `[OPTICS]` number:
  [z0r0z/cell](https://github.com/z0r0z/cell) (CC0)
- CAD kernel adapted from
  [nickthelegend/orchestrator-pad](https://github.com/nickthelegend/orchestrator-pad)
  `cad/partlib.py`
- three.js r160, vendored under `viewer/vendor/`
