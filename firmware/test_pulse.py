"""The pulse gate, against signals whose answer is known.

The sensor is not here yet, and the maths does not need it. Every case below
is a thing the gate will actually meet: a finger, a finger held badly, an
empty ring, a bright surface, mains hum, and someone waving.
"""
import sys, math, numpy as np
sys.path.insert(0, ".")
from cell4b.pulse import analyse, SAMPLE_RATE as SR

rng = np.random.default_rng(7)


def ppg(bpm, seconds=10, dc=120000, perfusion=1.0, noise=0.02):
    """A synthetic PPG. Not a sine -- a real pulse has a sharp systolic rise
    and a dicrotic notch, so the harmonics matter to anything frequency-based."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = bpm / 60.0
    wave = (np.sin(2 * np.pi * f * t)
            + 0.45 * np.sin(2 * np.pi * 2 * f * t + 0.9)
            + 0.18 * np.sin(2 * np.pi * 3 * f * t + 1.7))
    wave /= np.abs(wave).max()
    ac = dc * perfusion / 100.0
    return dc + ac * wave + rng.normal(0, ac * noise + dc * 1e-5, n)


CASES = [
    # label,                        signal,                                  expect
    ("finger, 72 bpm",              ppg(72),                                 True),
    ("finger, 48 bpm (resting)",    ppg(48),                                 True),
    ("finger, 180 bpm (exercise)",  ppg(180),                                True),
    ("finger, weak perfusion 0.15%", ppg(72, perfusion=0.15),                True),
    ("finger, noisy grip",          ppg(72, noise=0.55),                     True),
    ("empty ring (dark)",           np.full(10 * SR, 300.0)
                                    + rng.normal(0, 12, 10 * SR),            False),
    ("bright flat surface",         np.full(10 * SR, 240000.0)
                                    + rng.normal(0, 40, 10 * SR),            False),
    ("50 Hz mains hum",             120000 + 900 * np.sin(
                                        2 * np.pi * 50 * np.arange(10 * SR) / SR), False),
    # Rhythmic motion whose SECOND HARMONIC lands in the pulse band. Frequency
    # cannot reject this -- only amplitude can, which is what the ceiling is for.
    ("rhythmic motion, harmonic",   ppg(24, perfusion=9.0),                  False),
    ("finger tapping at 66 bpm",    ppg(66, perfusion=14.0),                 False),
    ("finger settling (big ramp)",  ppg(72) + np.linspace(0, 60000, 10 * SR), True),
    ("too short, 2 s",              ppg(72, seconds=2),                      False),
]

print("CELL-4B pulse gate\n")
print(f"  {'case':<30} {'bpm':>7} {'conf':>6} {'perf%':>7}  verdict")
print("  " + "-" * 66)
ok = 0
for label, sig, expect in CASES:
    p = analyse(sig)
    good = p.present == expect
    ok += good
    mark = "ok " if good else "BAD"
    print(f"  {label:<30} {p.bpm:>7.1f} {p.confidence:>6.2f} {p.perfusion:>7.3f}  "
          f"{'PULSE' if p.present else 'none ':<6} {mark}")
    if not good or p.reason:
        print(f"  {'':<30} {p.reason or '(expected ' + str(expect) + ')'}")

print()
print("  bpm accuracy on the clean cases:")
for bpm in (48, 60, 72, 90, 120, 180):
    p = analyse(ppg(bpm))
    err = abs(p.bpm - bpm)
    print(f"    {bpm:>3} bpm -> {p.bpm:>6.1f}   error {err:>4.1f}  "
          f"{'ok' if err <= 3 else 'DRIFT'}")

print(f"\n  {ok}/{len(CASES)} classified correctly")
sys.exit(0 if ok == len(CASES) else 1)
