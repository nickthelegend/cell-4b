"""Measure with the IR pin actively held OFF the whole time.

A released sink pin lights its LED, so every reading today has had the 940 nm
sitting underneath it. Holding the pin high for the duration removes that one
source. Whatever floor survives is not the IR emitter.
"""
import time
import numpy as np
from cell4b import hw
from cell4b.spectro import Spectrometer, BANDS, atime_for, EMITTER_OHMS

s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
# Bench already owns GPIO23, and all_off() drives every emitter pin to its
# inactive level and HOLDS it there. That is the point: a released sink pin
# floats and lights its own LED, so the floor can only be measured while
# something is actively holding the pins off.
b = hw.Bench(); b.all_off()
time.sleep(0.8)

def read():
    time.sleep(0.4)
    r = s.read()
    return np.array([r.channels[x] for x in BANDS], float), float(r.clear)

try:
    d8, dc = read()
    b.white_1.on()
    if b.white_2 is not None:
        b.white_2.on()      # None once the violet took its bore
    time.sleep(1.0)
    w8, wc = read()
    b.all_off()
    print(f"  dark   clear {dc:8.0f}   bands {d8.astype(int)}")
    print(f"  white  clear {wc:8.0f}   bands {w8.astype(int)}")
    net = w8 - d8
    print(f"  net                        {net.astype(int)}")
    print(f"\n  white signal above the floor: {wc-dc:+.0f} counts on a floor of {dc:.0f}")
    ratio = (wc - dc) / max(dc, 1)
    print(f"  signal / floor = {ratio:.4f}")
    print()
    if ratio < 0.05:
        print("  NOT MEASURABLE. The floor is more than 20x the signal, so every")
        print("  gate -- all of them ratios against that floor -- would be")
        print("  reporting noise. No conclusion about the cartridge is possible.")
    else:
        print("  Signal is above the floor; a chemistry read is worth running.")
finally:
    b.all_off(); b.close()
