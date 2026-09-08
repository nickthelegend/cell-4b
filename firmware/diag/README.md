# Bench diagnostics

Single-purpose scripts for one question each, written while bringing the
optical head up. They exist because the failures on this instrument look
alike from the outside: a blocked aperture, a dead emitter, a disabled ADC
and an empty chamber all read as **zero**, and zero is the value the blood
gate has to trust absolutely.

Each script is built to separate one of those from the others.

| | asks |
|---|---|
| `as7341probe.py` | is the chip alive? Dumps ID, ENABLE, ATIME/ASTEP, gain, and polls STATUS2 for AVALID |
| `aperture.py` | is it blind, or is the chamber dark? Its own LED at ~0 mm against the room |
| `ledspot.py` | does an emitter light, and where? Per-pixel difference with the global level removed, so room light cannot fake it |
| `borecheck.py` | is there an optical path between the sensor and the chamber at all? |
| `torchhunt.py` | can *any* external light reach the die, at 100 ms for live hunting |
| `aim.py` | live readout at the console's gain, for seating an emitter and watching the return climb |

## The one that matters

`aim.py` runs at **gain 256**, deliberately. At gain 8 a real return through
the Ø3 aperture reads 1–2 counts and is indistinguishable from noise — which
is exactly how an earlier version of this script hid a working optical path
and cost an afternoon of chasing the wrong fault.

```bash
.venv/bin/python diag/aim.py 180
```

Both whites come on and it prints a bar at ~5 reads/s with a running best.
Move **one** emitter at a time. Put something reflective at the read spot
first — an empty chamber returns nothing however well aligned it is.
