"""G3, measured properly: two illuminants, one white patch, one well.

G3 is (R630 - R415)/(R630 + R415), and each R is the sample over the printed
white patch AT THE SAME WAVELENGTH. So 415 comes from the violet emitter and
630 from the white, and each ratio cancels its own illumination geometry --
which is exactly why the patch exists, and why the two LEDs sitting in
different bores does not matter.

Park on the white patch when asked, then on the well.
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
I415, I630 = BANDS.index(415), BANDS.index(630)

def bands():
    time.sleep(0.6)
    r = s.read()
    return np.array([r.channels[x] for x in BANDS], float)

def park(label, secs):
    b.white_1.on()
    print(f"\n  >>> {label} -- {secs}s")
    t0 = time.time()
    while time.time() - t0 < secs:
        r = s.read()
        print(f"      clear {r.clear:6d}")
    b.all_off()

try:
    if b.violet is None:
        raise SystemExit("  set hw.WHITE2_IS_VIOLET = True first")
    dark = bands()

    park("PARK ON THE WHITE PATCH (brightest)", 15)
    with b.white():
        pw = bands()
    with b.ultraviolet():
        pv = bands()

    park("NOW PARK ON THE WELL (darkest)", 20)
    with b.white():
        sw = bands()
    with b.ultraviolet():
        sv = bands()
finally:
    b.all_off(); b.close()

r415 = (sv[I415] - dark[I415]) / max(pv[I415] - dark[I415], 1e-9)
r630 = (sw[I630] - dark[I630]) / max(pw[I630] - dark[I630], 1e-9)
idx = (r630 - r415) / max(r630 + r415, 1e-9)

print(f"\n  415 nm   patch {pv[I415]-dark[I415]:8.0f}   sample {sv[I415]-dark[I415]:8.0f}   R415 {r415:.4f}")
print(f"  630 nm   patch {pw[I630]-dark[I630]:8.0f}   sample {sw[I630]-dark[I630]:8.0f}   R630 {r630:.4f}")
print(f"\n  soret index = (R630 - R415)/(R630 + R415) = {idx:.4f}")
print(f"  G3 needs >= {TH.soret_index_min}")
print()
if pv[I415] - dark[I415] < 15:
    print("  NO 415 REFERENCE. The patch returns nothing at 415, so the ratio")
    print("  has no denominator and this number means nothing.")
elif idx >= TH.soret_index_min:
    print("  [PASS] G3. The sample absorbs at 415 far more than at 630 --")
    print("  a Soret band. That is a porphyrin, which no red dye has.")
else:
    print("  [FAIL] G3. Not enough 415 nm absorption relative to 630 for haem.")
    print("  A red dye absorbs blue-green broadly; haem absorbs 415 ferociously")
    print("  and narrowly. This sample does not.")
