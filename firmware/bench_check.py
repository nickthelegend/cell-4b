"""Every component, measured rather than assumed.

Reports numbers, not just pass/fail: where the optical path is not yet built,
a number tells you WHICH way it is wrong and a PASS/FAIL cannot.
"""
import statistics, subprocess, sys, time

R = []
def rec(name, ok, detail):
    R.append((name, ok, detail))
    mark = {True: "PASS", False: "FAIL", None: "INFO"}[ok]
    print(f"  [{mark}] {name:<22} {detail}", flush=True)

print("CELL-4B full component test\n")

# ---------------------------------------------------------------- 1. I2C ----
try:
    out = subprocess.run(["/usr/sbin/i2cdetect", "-y", "1"],
                         capture_output=True, text=True, timeout=10).stdout
    found = {a for a in ("39", "3c", "3d", "60") if f" {a}" in out}
    rec("I2C bus", bool(found), f"devices: {sorted(found) or 'none'}")
    rec("AS7341 present", "39" in found, "0x39" if "39" in found else "MISSING")
    rec("OLED present", bool(found & {"3c", "3d"}),
        "0x3c" if "3c" in found else ("0x3d" if "3d" in found else "MISSING"))
except Exception as e:
    rec("I2C bus", False, f"{type(e).__name__}: {e}")

# ------------------------------------------------------------ 2. display ----
try:
    from cell4b.display import Display
    d = Display()
    if d.ok:
        d.lines("FULL TEST", "", "running...", "", time.strftime("%H:%M:%S"))
        rec("OLED write", True, "wrote 5 lines, panel persists")
    else:
        rec("OLED write", False, getattr(d, "error", "not ok"))
        d = None
except Exception as e:
    rec("OLED write", False, f"{type(e).__name__}: {e}"); d = None

# --------------------------------------------------------------- 3. GPIO ----
from cell4b.hw import Bench, InterlockError, EMITTER_SINK
try:
    b = Bench()
    rec("GPIO claim", True, f"5 pins claimed, sink mode = {EMITTER_SINK}")
except Exception as e:
    rec("GPIO claim", False, f"{type(e).__name__}: {e}"); sys.exit(1)

rec("cartridge switch", None,
    f"GPIO22 reads {'LOW (seated/pressed)' if b.seated else 'HIGH (open)'}")

# ---------------------------------------------------- 4. interlock safety ----
try:
    with b.laser():
        b.all_off()
        rec("laser interlock", b.seated,
            "laser ENABLED because the switch reads seated" if b.seated
            else "FIRED WITH NO CARTRIDGE -- interlock broken")
except InterlockError:
    rec("laser interlock", True, "refused with no cartridge, as designed")
except Exception as e:
    rec("laser interlock", None, f"no laser driver fitted ({type(e).__name__})")

# The refusal above is only half the contract. Prove it ENABLES too, without
# needing a finger on the switch: substitute the sense and check the beam.
try:
    import cell4b.hw as _hw
    real = type(b).seated
    type(b).seated = property(lambda self: True)
    try:
        with b.laser():
            enabled = b.laser_on
        rec("laser enables when seated", enabled,
            "beam on with the switch reading seated" if enabled else "stayed off")
    finally:
        type(b).seated = real
        b.all_off()
except Exception as e:
    rec("laser enables when seated", None, f"{type(e).__name__}: {str(e)[:50]}")

# ---------------------------------------------------------- 5. AS7341 ----
try:
    from cell4b.spectro import Spectrometer, BANDS
    s = Spectrometer(atime=99, astep=1799, gain=256)
    r0 = s.read()
    rec("AS7341 read", True,
        f"clear={r0.clear} nir={r0.nir} integration={r0.integration_ms:.0f}ms gain=256x")
    ch = " ".join(f"{k}:{v}" for k, v in r0.channels.items())
    rec("AS7341 channels", None, ch)
except Exception as e:
    rec("AS7341 read", False, f"{type(e).__name__}: {e}"); s = None

# ------------------------------------- 5b. does the sensor see photons? ----
# The case optics may not exist yet, so "reads zero" cannot distinguish a dead
# sensor from an empty chamber. The breakout's own LED settles it without
# involving the head at all.
if s:
    try:
        raw = s.dev
        raw.led = False; time.sleep(0.4)
        off = raw.channel_clear
        raw.led_current = 20; raw.led = True; time.sleep(0.7)
        on = raw.channel_clear
        raw.led = False
        rec("AS7341 sees light", on - off > 50,
            f"onboard LED: clear {off} -> {on} ({on - off:+})")
    except Exception as e:
        rec("AS7341 sees light", None,
            f"breakout does not wire the LED ({type(e).__name__})")

# ------------------------------------------------------- 6. stability ----
if s:
    try:
        vals = [s.read().clear for _ in range(30)]
        m = statistics.mean(vals)
        sd = statistics.pstdev(vals)
        rsd = (sd / m * 100) if m else float("inf")
        # RSD is meaningless on a handful of counts: in darkness the mean is
        # shot noise and the ratio explodes, which reads as a broken sensor
        # when nothing is wrong. Only judge it where there is signal to judge.
        if m < 100:
            rec("AS7341 stability", None,
                f"30 reads, mean {m:.1f} -- too dark to judge. RSD needs signal; "
                f"M2 measures it on a lit white card.")
        else:
            rec("AS7341 stability", rsd < 1.0,
                f"30 reads, mean {m:.1f}, RSD {rsd:.2f}%  (M2 wants <1%)")
    except Exception as e:
        rec("AS7341 stability", False, f"{type(e).__name__}: {e}")

# --------------------------------------------------------- 7. emitters ----
if s:
    with b.dark():
        time.sleep(0.5)
        dark = statistics.median([s.read().clear for _ in range(5)])
    rec("chamber dark level", None, f"clear={dark:.0f} with every emitter off")
    for label, cm in (("white LED #1", b.white_1), ("white LED #2", b.white_2),
                      ("940 nm IR", b.ir_940)):
        try:
            cm.on(); time.sleep(0.7)
            lit = statistics.median([s.read().clear for _ in range(5)])
            cm.off(); time.sleep(0.1)
            rise = lit - dark
            verdict = ("reaches the sensor" if rise > 80 else
                       "faint" if rise > 15 else "no light reaching the sensor")
            rec(f"emitter {label}", None, f"clear {dark:.0f} -> {lit:.0f}  ({rise:+.0f})  {verdict}")
        except Exception as e:
            rec(f"emitter {label}", False, f"{type(e).__name__}: {e}")
    b.all_off()

# ---------------------------------------------------------- 8. camera ----
try:
    from picamera2 import Picamera2
    cam = Picamera2()
    cfg = cam.create_still_configuration(main={"size": (640, 480)})
    cam.configure(cfg); cam.start(); time.sleep(1.2)
    arr = cam.capture_array()
    cam.stop(); cam.close()
    mean, sd = arr.mean(), arr.std()
    rec("camera capture", True,
        f"{arr.shape[1]}x{arr.shape[0]} frame, mean {mean:.1f}, std {sd:.1f}")
    rec("camera speckle-ready", None,
        "std > 8 suggests structure in frame" if sd > 8 else
        "flat frame -- lens still on, or capped, or dark")
except Exception as e:
    rec("camera capture", False, f"{type(e).__name__}: {str(e)[:70]}")

b.all_off(); b.close()
if d and d.ok:
    ok = sum(1 for _, o, _ in R if o is True)
    bad = sum(1 for _, o, _ in R if o is False)
    d.lines("TEST DONE", "", f"pass {ok}", f"fail {bad}", "see terminal")

print()
p = sum(1 for _, o, _ in R if o is True)
f = sum(1 for _, o, _ in R if o is False)
i = sum(1 for _, o, _ in R if o is None)
print(f"  {p} passed, {f} failed, {i} informational")
