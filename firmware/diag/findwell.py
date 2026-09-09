"""Slide the cartridge slowly. Blood under the aperture is a MINIMUM.

The chemistry read returned white == sample == 96, identical, which means it
measured the same spot twice. Rather than guess which stop is wrong, this
watches the return continuously while the cartridge moves: the white patch
is the brightest thing on the card and the blood-filled well is the darkest,
so both positions announce themselves.
"""
import sys, time
import numpy as np
from cell4b import hw
from cell4b.spectro import Spectrometer, BANDS

s = Spectrometer(); s.set_timing(atime=39, astep=1799, gain=256)
b = hw.Bench(); b.all_off()
b.white_1.on(); b.white_2.on()
SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 75.0

print("  Slide the cartridge SLOWLY all the way in, then back out.")
print("  Watching for the bright patch and the dark well.\n")
print(f"  {'total':>7} {'415':>5} {'630':>5}  bar")
lo, hi, t0 = 10**9, 0, time.time()
try:
    while time.time() - t0 < SECS:
        v = np.array([s.read().channels[x] for x in BANDS], float)
        tot = int(v.sum())
        lo, hi = min(lo, tot), max(hi, tot)
        print(f"  {tot:7d} {v[0]:5.0f} {v[6]:5.0f}  {'#' * min(50, tot // 8)}")
except KeyboardInterrupt:
    pass
finally:
    b.all_off(); b.close()
print(f"\n  brightest {hi}   darkest {lo}   contrast {hi / max(lo,1):.1f}x")
if hi / max(lo, 1) < 2.0:
    print("  NO FEATURE PASSED UNDER THE APERTURE. The reading barely changed")
    print("  across the whole travel, so the aperture is not looking at the")
    print("  card at all -- it is seeing something that does not move with it.")
else:
    print("  Two distinct levels seen. The DARKEST is the well; stop there.")
