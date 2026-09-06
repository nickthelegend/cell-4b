# CELL-4B firmware

Bench software for the CELL-4B instrument. Pinout, rails and milestones come
from the enclosure repo's `ASSEMBLY.md` — nothing here re-derives them.

## Install

```bash
./scripts/setup.sh
```

Installs `gpiozero`, `picamera2`, `python3-pil` and `i2c-tools` from **apt**,
enables I²C, then builds a venv with `--system-site-packages` and pip-installs
the three things apt does not carry. The apt-vs-pip split matters: a pip copy of
`picamera2` or `gpiozero` cannot reach the hardware, and the failure looks
exactly like a wiring fault.

## Bring-up, in this order

```bash
.venv/bin/python -m cell4b selftest
```

The checks run in the order that isolates faults fastest, and stop at the
first failure, because each one assumes the ones before it passed.

| # | Check | What a failure means |
|---|---|---|
| 1 | I²C bus | 0x39 absent → SDA/SCL, 3V3, or I²C not enabled |
| 2 | Laser interlock | **fires with slot empty → stop, fix GPIO22 first** |
| 3 | Cartridge switch | no change → not wired; HIGH when seated → inverted |
| 4 | Emitters | no Clear rise → dead FET, wrong resistor, or wrong rail |
| 5 | 415 nm headroom | on the ADC floor → raise ATIME/ASTEP or gain |
| 6 | Light-tight (M4) | Clear ≥ 0.5 % → paint the bores, check baffle and lap |

Checks 2 and 4 are the two that catch a wiring mistake before it looks like
optics. A light leak and a dead LED both read as "415 nm sees nothing".

## Wiring

`ASSEMBLY.md` §5. Repeated here because getting a rail wrong is the one
mistake that destroys a part:

| Pin | Function | Resistor | Rail |
|---|---|---|---|
| GPIO2/3 | I²C1 — AS7341 0x39, OLED 0x3C | — | 3V3 |
| GPIO12 | white LED #1 | **220 Ω** | **+5 V** |
| GPIO16 | white LED #2 | **220 Ω** | **+5 V** |
| GPIO23 | 940 nm IR | **220 Ω** | **+3V3** |
| GPIO6 | laser ENABLE | — | module off +5 V |
| GPIO22 | cartridge switch | internal pull-up | LOW when seated |

**120 Ω, not the 68/47 the optical design asks for.** Those assume a transistor
in the ground return. `EMITTER_SINK = True`, so the **GPIO carries the current**
and a Pi pin is rated 16 mA — 68 Ω would be 27.9 mA and 47 Ω would be 41.5 mA,
straight past it. Do not "correct" the resistors without also fitting
transistors and setting the flag to `False`.

**The two rails are different rails.** The white LEDs must be on **+5 V**: their
V<sub>f</sub> is ~3.1 V, so from +3V3 they barely conduct. The 940 nm must stay
on **+3V3**: in a sink build the pin floats to (rail − V<sub>f</sub>) while it is
an input, and at V<sub>f</sub> 1.35 V from +5 V that is 3.65 V, over the 3.3 V
pad limit.

Only **one** 2.2 kΩ pull-up pair on the I²C bus — keep the one the breakout
ships with.

## Use

```bash
.venv/bin/python -m cell4b status              # pins, switch, OLED
.venv/bin/python -m cell4b read -n 20          # one averaged reading
.venv/bin/python -m cell4b measure blood-01    # dark / white / sample -> JSON
.venv/bin/python -m cell4b speckle run-01      # M6, 600 s series
```

## Why the integration time is so long

`spectro.py` defaults to ATIME 99 / ASTEP 999 — about 278 ms. The sensor sits
at **28 mm** from the sample, not upstream's 9 mm, so it receives roughly
(28/9)² ≈ 9.7× less light. Short integrations put 415 nm on the ADC floor.

415 nm is the channel the instrument exists to read: it is where haemoglobin
absorbs and red food dye does not. If it will not lift off the floor on a white
card, **say so in the writeup** — per `ASSEMBLY.md` §6 that is a result, not a
defect to bury.

## What this deliberately does not do

There is no threshold anywhere in this code and no verdict. `measure.py`
returns reflectance and writes JSON; it does not tell you what the numbers
mean. Upstream `BUILD.md` §15 M7 is where `thresholds.json` gets earned — from
data, with an ROC. A number hard-coded now would be inventing the answer.

Read upstream `SAFETY.md` before any of this involves blood. One device, one
person, one lancet per use, sharps container.
