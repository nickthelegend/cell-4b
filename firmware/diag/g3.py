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
from cell4b.display import Display
from cell4b.spectro import Spectrometer, BANDS, atime_for, EMITTER_OHMS

# The prompts go on the DEVICE's own screen, not the terminal. Whoever is
# sliding the cartridge is looking at the instrument, and an instruction they
# have to read somewhere else is an instruction that arrives late -- which is
# how the last two runs ended up reading one spot twice.
OLED = Display()

TH = bg.Thresholds()
s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
b = hw.Bench(); b.all_off()
I415, I630 = BANDS.index(415), BANDS.index(630)

def bands():
    time.sleep(0.6)
    r = s.read()
    return np.array([r.channels[x] for x in BANDS], float)

def park(label, secs, l1, l2, want):
    b.white_1.on()
    print(f"\n  >>> {label} -- {secs}s")
    t0 = time.time()
    best = 0 if want == "high" else 10 ** 9
    while time.time() - t0 < secs:
        r = s.read()
        best = max(best, r.clear) if want == "high" else min(best, r.clear)
        left = int(secs - (time.time() - t0))
        OLED.lines(l1, l2, "", f"now {r.clear}", f"{want} {best}   {left}s")
        print(f"      clear {r.clear:6d}   {'#' * min(60, r.clear // 4)}")
    OLED.lines(l1, l2, "", "READING", "hold still")
    b.all_off()

try:
    if b.violet is None:
        raise SystemExit("  set hw.WHITE2_IS_VIOLET = True first")
    OLED.lines("G3 SORET", "", "reading dark", "hold still", "")
    dark = bands()

    park("SLIDE TO THE WHITE PATCH -- watch for the HIGHEST number", 30,
         "SLIDE TO THE", "WHITE PATCH", "high")
    with b.white():
        pw = bands()
    with b.ultraviolet():
        pv = bands()

    park("NOW PUSH IT FURTHER IN -- watch for the LOWEST number", 30,
         "PUSH FURTHER IN", "TO THE WELL", "low")
    with b.white():
        sw = bands()
    with b.ultraviolet():
        sv = bands()
finally:
    b.all_off(); b.close()

if abs(sw[I630] - pw[I630]) < 4:
    print(f"\n  STOPPED. white-patch 630 = {pw[I630]-dark[I630]:.0f}, "
          f"sample 630 = {sw[I630]-dark[I630]:.0f} -- the cartridge did not")
    print("  move between the two reads, so both are the same spot. A ratio")
    print("  of a measurement against itself is 1.0 whatever is in the well.")
    raise SystemExit(1)

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

try:
    OLED.lines("G3 DONE", "", f"index {idx:.3f}", f"need {TH.soret_index_min}",
               "PASS" if idx >= TH.soret_index_min else "FAIL")
except Exception:
    pass
