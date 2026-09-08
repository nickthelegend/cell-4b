"""Is the aperture bore open? Fire the AS7341's LED, look with the camera.

The camera is inside the chamber. The AS7341 is outside it, on the flank.
The only path between them is the Dia-3 x 6 waist. So if firing the sensor's
own LED makes a localised spot appear in the camera's view, that light came
down the bore -- and the bore is open. Ambient is removed per-frame, so room
light cannot fake it.
"""
import time
import numpy as np
from picamera2 import Picamera2
from cell4b.spectro import Spectrometer

s = Spectrometer()
cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (320, 240)}))
cam.start(); time.sleep(2.0)
cam.set_controls({"AeEnable": False, "AwbEnable": False,
                  "ExposureTime": 200000, "AnalogueGain": 16.0})
time.sleep(2.0)

def grab(n=14):
    fs = []
    for _ in range(n):
        f = cam.capture_array()[:, :, :3].astype(float).mean(axis=2)
        fs.append(f - f.mean())          # remove uniform ambient
    return np.stack(fs).mean(axis=0)

def lamp(on):
    try:
        if on: s.dev.led_current = 100     # hard as it will go
        s.dev.led = on
    except Exception:
        s._poke(0x70, (s._peek(0x70) | 0x08) if on else (s._peek(0x70) & ~0x08))
        s._poke(0x74, (0x80 | 0x1F) if on else 0x00)
    time.sleep(0.4)

try:
    lamp(False); a = grab()
    lamp(True);  time.sleep(1.0); lit = grab()
    lamp(False); time.sleep(0.8); b = grab()
finally:
    cam.stop(); cam.close()

diff = lit - (a + b) / 2
noise = float(np.std((a - b) / 2))
peak = float(diff.max())
top = float(np.sort(diff.ravel())[-int(diff.size * 0.01):].mean())
snr = top / max(noise, 1e-6)
iy, ix = np.unravel_index(int(np.argmax(diff)), diff.shape)

print(f"\n  peak {peak:+.2f}   top1% {top:+.2f}   noise {noise:.2f}   SNR {snr:.1f}")
print(f"  brightest at x={ix} y={iy}\n")
h, w = diff.shape
bh, bw = h // 12, w // 16
small = diff[:bh*12, :bw*16].reshape(12, bh, 16, bw).mean(axis=(1, 3))
lo, hi = float(small.min()), float(small.max())
ramp = " .:-=+*#%@"
for row in small:
    print("    " + "".join(ramp[min(9, int(9*(v-lo)/max(hi-lo, 1e-6)))] for v in row))
print()
if snr > 4:
    print("  LIGHT CAME THROUGH. The Dia-3 waist is OPEN -- the bore is clear")
    print("  and the sensor is on it. The zeros are NOT a blocked aperture:")
    print("  there is simply nothing at the read spot returning light.")
else:
    print("  NO LIGHT THROUGH THE BORE. Either the waist is blocked, or the")
    print("  sensor's LED is entirely over plastic and never reaches its mouth")
    print("  -- so this is suggestive, not proof. But combined with zero from")
    print("  both chamber LEDs, a blocked waist is now the leading explanation.")
