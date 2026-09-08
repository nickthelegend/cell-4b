"""Find an LED by its SPOT, not by frame brightness.

Whole-frame mean fails in room light: the LED's contribution is diluted
and ambient drift swamps it. A localised source still shows up as
spatial structure once the global level is removed from every frame.
"""
import time
import numpy as np
from gpiozero import DigitalOutputDevice
from picamera2 import Picamera2
from cell4b.display import Display

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (320, 240)}))
cam.start(); time.sleep(2.0)
cam.set_controls({"AeEnable": False, "AwbEnable": False,
                  "ExposureTime": 200000, "AnalogueGain": 16.0})
time.sleep(2.0)

def grab(n=12):
    """Mean frame with its own global level removed -> ambient-immune."""
    fs = []
    for _ in range(n):
        f = cam.capture_array()[:, :, :3].astype(float).mean(axis=2)
        fs.append(f - f.mean())          # kill uniform drift, keep structure
    return np.stack(fs).mean(axis=0)

d = Display()
TESTS = [("white #2", 16, "pin36"), ("white #1", 13, "pin33")]
out = []
try:
    for name, pin, hdr in TESTS:
        led = DigitalOutputDevice(pin, active_high=False, initial_value=False)
        time.sleep(0.8)
        a = grab()
        led.on()
        d.lines(name.upper(), hdr, "", "LIT", "")
        time.sleep(1.5)
        lit = grab()
        led.off(); led.close()
        time.sleep(1.2)
        b = grab()
        diff = lit - (a + b) / 2
        noise = float(np.std((a - b) / 2))      # what two dark frames disagree by
        out.append((name, hdr, diff, noise))
finally:
    cam.stop(); cam.close()
    d.lines("SPOT TEST", "DONE", "", "", "")

for name, hdr, diff, noise in out:
    h, w = diff.shape
    peak = float(diff.max())
    top = float(np.sort(diff.ravel())[-int(diff.size * 0.01):].mean())
    snr = top / max(noise, 1e-6)
    iy, ix = np.unravel_index(int(np.argmax(diff)), diff.shape)
    print(f"\n  === {name}  {hdr} ===")
    print(f"  peak {peak:+7.2f}   top1% {top:+7.2f}   dark-noise {noise:5.2f}"
          f"   SNR {snr:6.1f}")
    print(f"  brightest pixel at x={ix} y={iy}  (frame is 320x240)")
    print(f"  VERDICT: {'LIGHTS' if snr > 4 else 'no light detected'}")
    # coarse map so the aim is visible
    bh, bw = h // 12, w // 16
    small = diff[:bh * 12, :bw * 16].reshape(12, bh, 16, bw).mean(axis=(1, 3))
    lo, hi = float(small.min()), float(small.max())
    rng = max(hi - lo, 1e-6)
    ramp = " .:-=+*#%@"
    print("  where the light landed:")
    for row in small:
        print("    " + "".join(ramp[min(9, int(9 * (v - lo) / rng))] for v in row))
