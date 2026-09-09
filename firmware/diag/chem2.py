"""Chemistry read with live positioning. You park; it reads when you say.

Last night's read returned white == sample == 96 because both stops landed on
the same feature. Rather than trust two nominal depths, this shows the return
live and takes each reading only when told, so the white patch and the well
are each measured where they actually are.
"""
import sys, time
import numpy as np
sys.path.insert(0, "upstream")
import blood_gate as bg
from cell4b import hw
from cell4b.spectro import Spectrometer, BANDS, atime_for, EMITTER_OHMS

TH = bg.Thresholds()
s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
b = hw.Bench(); b.all_off()

def read3(which):
    if which == "dark":
        b.all_off()
    else:
        b.white_1.on(); b.white_2.on()
    time.sleep(0.5)
    r = s.read()
    f8 = np.array([r.channels[x] for x in BANDS], float)
    b.all_off()
    return f8, float(r.clear), float(r.nir)

def park(label, secs):
    """Show the live return for `secs` so the cartridge can be positioned."""
    b.white_1.on(); b.white_2.on()
    print(f"\n  >>> {label} -- {secs}s to position")
    t0 = time.time()
    while time.time() - t0 < secs:
        v = np.array([s.read().channels[x] for x in BANDS], float)
        print(f"      total {int(v.sum()):5d}   {'#' * min(46, int(v.sum())//3)}")
    b.all_off()

try:
    print("  dark reference (all emitters off)")
    dark = read3("dark")
    print(f"      dark clear = {dark[1]:.0f}")

    park("PARK ON THE WHITE PATCH -- the BRIGHTEST spot", 18)
    white = read3("white")
    print(f"      white clear = {white[1]:.0f}")

    park("NOW PARK ON THE WELL -- the DARKEST spot", 25)
    chem = read3("white")
    if abs(white[1] - chem[1]) < 5:
        print()
        print(f"  STOPPED. white {white[1]:.0f} vs sample {chem[1]:.0f} -- the")
        print("  cartridge did not move between the two reads, so both are the")
        print("  same spot. Four gates computed from one measurement look like")
        print("  a result and are not one. Slide it and run again.")
        raise SystemExit(1)
    print(f"      sample clear = {chem[1]:.0f}")

    cap = {"dark": dark, "white": white, "chem": chem}
    print(f"\n  white {white[1]:.0f}   sample {chem[1]:.0f}   "
          f"ratio {chem[1]/max(white[1],1):.4f}")
    if abs(white[1] - chem[1]) < 3:
        print("  !! still the same spot -- the two positions did not differ")
    print()
    for g in bg.chemistry_gates(cap, TH):
        print(f"  [{'PASS' if g.passed else 'FAIL'}] {g.name:24} "
              f"{g.value:9.4f}  limit {g.threshold:.4f}   {g.detail[:40]}")
finally:
    b.all_off(); b.close()
