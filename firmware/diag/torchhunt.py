"""Shine a torch up the cartridge slot and hunt for ANY light path.

The emitters are aimed at the read spot; a torch is not, so this asks a much
weaker question than a real measurement: is there ANY optical path at all
from the sample chamber to the die? If a bright torch waved across the slot
cannot put a single count on the sensor, the path is closed -- either the
Dia-3 x 6 aperture tube is blocked, or the breakout is glued off its axis.
"""
import time
from cell4b.spectro import Spectrometer, BANDS
from cell4b.display import Display

s = Spectrometer()
s.set_timing(atime=19, astep=1799, gain=8)   # ~100 ms, so it responds live
d = Display()

print("  SHINE A TORCH INTO THE CARTRIDGE SLOT.")
print("  Sweep it around -- angle it, move it closer, try the top hole too.")
print("  30 seconds. Watching every band.\n")
d.lines("TORCH TEST", "", "shine into", "the slot", "sweep around")

best, best_at, t0 = 0, 0.0, time.time()
n = 0
while time.time() - t0 < 30:
    r = s.read()
    tot = sum(r.channels.values()) + r.clear
    n += 1
    if tot > best:
        best, best_at = tot, time.time() - t0
        d.lines("TORCH", f"{tot}", "", "keep going", "")
    if n % 5 == 0:
        print(f"  t={time.time()-t0:5.1f}s  now={tot:7d}  best={best:7d}"
              f"  clear={r.clear:6d} nir={r.nir:5d}")

print(f"\n  {n} reads over 30 s.  BEST total = {best} at t={best_at:.1f}s\n")
if best > 200:
    print("  THERE IS A LIGHT PATH. The chamber can reach the die, so the")
    print("  sensor does not need to come out. What is wrong is aim: the")
    print("  emitters are not putting light on the read spot the sensor sees.")
    d.lines("PATH OK", f"{best}", "", "sensor stays", "aim emitters")
elif best > 20:
    print("  A trace got through -- there is a path, but it is nearly closed.")
    print("  Suspect a partly blocked aperture tube. Try passing a 2.5 mm")
    print("  drill bit or a paperclip down the bore by hand before unglueing.")
    d.lines("PATH WEAK", f"{best}", "", "clear the", "aperture")
else:
    print("  NO PATH AT ALL. A torch at point blank puts zero counts on a")
    print("  sensor that reads 1991 from its own LED. The die is sealed off.")
    print("  Check in this order, cheapest first:")
    print("    1. hold the head up to a lamp and look down the sensor bore --")
    print("       you should see daylight through the Dia-3 tube")
    print("    2. pass a 2.5 mm drill bit through the tube by hand")
    print("    3. only then unglue the AS7341 and check it is centred on the")
    print("       bore, window facing down, no glue across the die")
    d.lines("NO PATH", "", "die is", "sealed off", "check bore")
