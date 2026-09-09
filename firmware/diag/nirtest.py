"""Does the 940 nm LED reach the sensor? G2 is dead without it.

G2 is the cell-scatter gate: NIR over Clear, both normalised against the
white patch. It is the discriminator that a dye cannot beat -- ketchup has
no cells and scored 0.0000. But it can only work if the 940 nm emitter
actually illuminates the read spot AND the AS7341's NIR channel sees it.
"""
import time
import numpy as np
from cell4b import hw
from cell4b.spectro import Spectrometer, atime_for, EMITTER_OHMS

s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
b = hw.Bench(); b.all_off()

def read():
    time.sleep(0.5)
    r = s.read()
    return float(r.clear), float(r.nir)

try:
    b.all_off(); c0, n0 = read()
    print(f"  all off         clear {c0:7.0f}   nir {n0:7.0f}")

    b.white_1.on(); b.white_2.on(); time.sleep(0.8)
    cw, nw = read(); b.all_off()
    print(f"  whites on       clear {cw:7.0f}   nir {nw:7.0f}")

    b.ir_940.on(); time.sleep(0.8)
    ci, ni = read(); b.all_off()
    print(f"  940 nm on       clear {ci:7.0f}   nir {ni:7.0f}")

    print()
    print(f"  940 nm net on the NIR channel: {ni - n0:+.0f}")
    if ni - n0 >= 5:
        print("  IR REACHES THE SENSOR -- G2 is measurable.")
        print("  Cell scatter can be tested, and that is the gate a dye")
        print("  cannot fake: ketchup has no cells to scatter with.")
    else:
        print("  IR DOES NOT REACH THE SENSOR. G2 cannot pass either --")
        print("  so today the device has NO working discriminator against a")
        print("  red dye. G3 needs 415 nm light it does not have, and G2")
        print("  needs 940 nm light that is not arriving.")
finally:
    b.all_off(); b.close()
