"""All four chemistry gates, with 415 nm taken under the violet emitter.

chemistry_gates() reads eight bands from one illumination. That works for a
head whose white LEDs cover the band -- and these do not: they are blue-pump
phosphor and emit nothing at 415, so G3 reads a hard zero however good the
sample is (FINDINGS 12).

So the capture is assembled from TWO illuminations: 445..680 under white, and
415 under the 400 nm violet that now sits in white #2's bore. Both are divided
by the same printed white patch measured under the SAME emitter, so each
channel's ratio cancels its own illumination geometry -- which is the property
the patch exists to provide, and the reason two LEDs in different bores is not
a problem.

Nothing about the gates or their thresholds is touched. Only where the 415
photons come from.
"""
import sys, time
import numpy as np
sys.path.insert(0, "upstream")
import blood_gate as bg
from cell4b import hw
from cell4b.display import Display
from cell4b.spectro import Spectrometer, BANDS, atime_for, EMITTER_OHMS

TH = bg.Thresholds()
I415 = BANDS.index(415)
s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
b = hw.Bench(); b.all_off()
OLED = Display()

def read():
    time.sleep(0.6)
    r = s.read()
    return np.array([r.channels[x] for x in BANDS], float), float(r.clear), float(r.nir)

def park(l1, l2, want, secs=30):
    b.white_1.on()
    print(f"\n  >>> {l1} {l2}")
    t0, best = time.time(), (0 if want == "high" else 10**9)
    while time.time() - t0 < secs:
        r = s.read()
        best = max(best, r.clear) if want == "high" else min(best, r.clear)
        OLED.lines(l1, l2, "", f"now {r.clear}",
                   f"{want} {best}  {int(secs-(time.time()-t0))}s")
        print(f"      clear {r.clear:6d}  {'#' * min(58, r.clear//5)}")
    OLED.lines(l1, l2, "", "READING", "hold still")
    b.all_off()

def capture_at(label):
    """White for the band shape, violet for 415, IR for the scatter gate."""
    with b.white():
        f8, clear, _ = read()
    with b.ultraviolet():
        v8, _, _ = read()
    b.ir_940.on(); time.sleep(0.7)
    _, _, nir = read()
    b.ir_940.off()
    f8 = f8.copy()
    f8[I415] = v8[I415]              # 415 comes from the violet, nowhere else
    print(f"  {label:12} clear {clear:7.0f}  nir {nir:7.0f}  415 {f8[I415]:6.0f}")
    return f8, clear, nir

try:
    if b.violet is None:
        raise SystemExit("  set hw.WHITE2_IS_VIOLET = True first")
    OLED.lines("CHEMISTRY", "", "reading dark", "hold still", "")
    b.all_off()
    dark = capture_at("dark")

    park("SLIDE TO THE", "WHITE PATCH", "high")
    white = capture_at("white patch")

    park("PUSH FURTHER IN", "TO THE WELL", "low")
    chem = capture_at("sample")
finally:
    b.all_off(); b.close()

if abs(white[1] - chem[1]) < 5:
    print("\n  STOPPED: patch and sample read the same spot.")
    raise SystemExit(1)

print()
gates = bg.chemistry_gates({"dark": dark, "white": white, "chem": chem}, TH)
for g in gates:
    print(f"  [{'PASS' if g.passed else 'FAIL'}] {g.name:22} {g.value:10.4f}"
          f"  limit {g.threshold:.4f}")
npass = sum(g.passed for g in gates)
print(f"\n  {npass}/4 chemistry gates passed")
OLED.lines("CHEMISTRY", "", f"{npass} of 4", "gates passed", "")
