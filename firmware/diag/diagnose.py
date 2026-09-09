"""Is the AS7341 damaged, leaking light, or offset? Three signatures.

  dark current   linear in integration time, through the ORIGIN, and doubles
                 roughly every 8 C
  light leak     also linear through the origin, but indifferent to sensor
                 temperature and it changes when the aperture is blocked
  ADC offset     NOT linear -- a fixed pedestal that survives integration
                 going to zero

Only the intercept separates the third from the first two, and only
temperature separates the first from the second. This measures the intercept;
the temperature leg needs a human with an ice pack.
"""
import subprocess, time
import numpy as np
from cell4b import hw
from cell4b.spectro import Spectrometer

# Bench must exist for the whole run: it drives every emitter pin to its
# inactive level and HOLDS it. Without it the pins are inputs, and a floating
# sink pin lights its own LED -- so the "dark" floor silently includes the
# 940 nm emitter, which is exactly what happened the first time this ran.
_bench = hw.Bench(); _bench.all_off()

def temp():
    try:
        out = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True,
                             text=True).stdout
        return float(out.split("=")[1].split("'")[0])
    except Exception:
        return float("nan")

print(f"  SoC temperature: {temp():.1f} C   (all emitter pins HELD off)\n")
print(f"  {'ATIME':>6} {'ms':>7} {'clear':>8} {'nir':>8}")
pts = []
for atime in (9, 24, 49, 99, 149, 182):
    s = Spectrometer(); s.set_timing(atime=atime, astep=1799, gain=256)
    time.sleep(0.3)
    r = s.read()
    ms = (atime + 1) * 1800 * 2.78 / 1000
    pts.append((ms, float(r.clear), float(r.nir)))
    print(f"  {atime:6d} {ms:7.0f} {r.clear:8d} {r.nir:8d}")
    s.close()

ms = np.array([p[0] for p in pts])
for name, idx in (("clear", 1), ("nir", 2)):
    y = np.array([p[idx] for p in pts])
    slope, intercept = np.polyfit(ms, y, 1)
    resid = y - (slope * ms + intercept)
    print(f"\n  {name}:  slope {slope:8.2f}/ms   intercept {intercept:9.1f}")
    print(f"          worst residual {np.abs(resid).max():.0f} counts")
    frac = abs(intercept) / max(y.max(), 1)
    if frac > 0.15:
        print(f"          -> {frac*100:.0f}% of the signal is a FIXED PEDESTAL.")
        print("             That is an ADC/offset fault, not dark current.")
    else:
        print("          -> passes through the origin: it INTEGRATES.")
        print("             Dark current or light, not an offset fault.")

print()
print("  NEXT, and only a human can do these:")
print("   1. COOL IT. Ice pack in a bag against the sensor, 5 min, re-run.")
print("      dark current halves per ~8 C. Light will not move at all.")
print("   2. BLOCK IT. Opaque tape over the aperture, re-run.")
print("      a leak drops; dark current does not care.")

_bench.all_off(); _bench.close()
