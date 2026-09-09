"""First contact with the 400 nm emitter. Two questions, in order.

  1. Does F1 (415 nm) come off zero?  Without that, G3 cannot run for any
     sample -- the white LEDs are blue-pump phosphor and emit nothing there.

  2. Is what F1 sees actually 415 nm light, or is it the HOUSING GLOWING?
     PLA and PET fluoresce under near-UV, and that emission is broadband and
     comes from the chamber itself rather than the sample. It would look like
     signal and be worth nothing. A real reflectance signal rises at 415 and
     leaves the other bands alone; fluorescence lifts everything together.

Run with the chamber EMPTY. Nothing to reflect off means any rise in the
visible bands has to be the housing.
"""
import time
import numpy as np
from cell4b import hw
from cell4b.spectro import Spectrometer, BANDS, atime_for, EMITTER_OHMS

s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
b = hw.Bench(); b.all_off()

def read():
    time.sleep(0.6)
    r = s.read()
    return np.array([r.channels[x] for x in BANDS], float), float(r.clear)

try:
    if b.violet is None:
        raise SystemExit("  set hw.WHITE2_IS_VIOLET = True first")
    d8, dc = read()
    with b.ultraviolet():
        time.sleep(0.8)
        v8, vc = read()
    with b.white():
        time.sleep(0.8)
        w8, wc = read()
finally:
    b.all_off(); b.close()

net_v, net_w = v8 - d8, w8 - d8
print(f"  {'band':>6} {'dark':>8} {'violet':>8} {'net':>8}   {'white net':>9}")
for i, band in enumerate(BANDS):
    print(f"  {band:>6} {d8[i]:8.0f} {v8[i]:8.0f} {net_v[i]:+8.0f}   {net_w[i]:+9.0f}")

f1 = net_v[0]
rest = net_v[1:]
print(f"\n  F1 (415) under violet : {f1:+.0f}")
print(f"  mean of 445..680      : {rest.mean():+.0f}")
print(f"  selectivity F1/rest   : {f1/max(abs(rest.mean()), 1e-9):.2f}")
print()
if f1 < 15:
    print("  NO 415 SIGNAL. Either the LED is not lit, not aimed at the read")
    print("  spot, or its wavelength is too short for F1's 402-428 nm window.")
elif f1 > 2.0 * abs(rest.mean()):
    print("  CLEAN 415 CHANNEL. F1 rises and the other bands do not follow, so")
    print("  this is 400 nm light being returned -- not the housing glowing.")
    print("  G3 is measurable.")
else:
    print("  F1 RESPONDS, BUT SO DOES EVERYTHING ELSE. That pattern is the")
    print("  housing fluorescing under near-UV, which is emission from the")
    print("  chamber rather than reflectance from the sample. A longer")
    print("  wavelength (405-415) would cut it. Treat G3 as unproven for now.")
