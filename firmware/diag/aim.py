"""Live readout for seating the emitters. Both whites on, sample in place.

Runs at the console's sensitivity -- gain 256 -- because at gain 8 a real
return through the Dia-3 aperture reads 1-2 counts and looks like noise.
Integration is shortened to 200 ms so it responds while you move something.

Move ONE emitter at a time and watch the number. Seated in its bore aiming
at the read spot it should climb hard; pointing at a wall it will not.
"""
import sys, time
import numpy as np
from cell4b import hw
from cell4b.spectro import Spectrometer, BANDS

s = Spectrometer(); s.set_timing(atime=39, astep=1799, gain=256)
b = hw.Bench(); b.all_off()
SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0

b.white_1.on(); b.white_2.on()
print("  Both whites ON, gain 256. Seat one emitter at a time.\n")
print(f"  {'total':>7} {'415':>6} {'630':>6}  {'peak':>7}  colour")

def colour(v):
    if v.sum() < 40: return "--"
    B, G, R = v[[0,1,2]].mean(), v[[3,4]].mean(), v[[6,7]].mean()
    if max(R,G,B)/max(min(R,G,B),1e-6) < 1.35: return "NEUTRAL/WHITE"
    if R > 1.5*G and R > 1.5*B: return "RED" if G < 1.3*B else "ORANGE-RED"
    if G > 1.3*R and G > 1.3*B: return "GREEN"
    if B > 1.3*R and B > 1.3*G: return "BLUE"
    if R > 1.3*B and G > 1.3*B: return "YELLOW/WARM"
    return "MIXED"

best, t0, last = 0, time.time(), None
try:
    while time.time() - t0 < SECS:
        v = np.array([s.read().channels[x] for x in BANDS], float)
        tot = int(v.sum()); best = max(best, tot); last = v
        bar = "#" * min(40, tot // 40)
        print(f"  {tot:7d} {v[0]:6.0f} {v[6]:6.0f}  {BANDS[int(v.argmax())]:5d}nm"
              f"  {colour(v):<14} |{bar:<40}| best {best}")
except KeyboardInterrupt:
    pass
finally:
    b.all_off(); b.close()

print(f"\n  best total {best}")
if last is not None and last.sum() > 40:
    hi = max(float(last.max()), 1.0)
    for band, x in zip(BANDS, last):
        print(f"  {band:>4} nm {x:7.0f}  {'#' * int(40 * x / hi)}")
    print(f"\n  630/415 = {last[6]/max(last[0],1):.1f}   COLOUR: {colour(last)}")
    print("\n  Ketchup should read RED with a steep 415->630 rise. That 415 nm")
    print("  channel is the one G3 lives on: haem absorbs hard there, and so")
    print("  does a red dye -- which is exactly why M5 has to tell them apart.")
