"""Bring-up checks, in the order that isolates faults fastest.

Each check assumes the ones before it passed, so the first failure is the one
worth acting on. That ordering matters more than it sounds: a light leak and a
dead LED both show up as "415 nm reads nothing", and telling them apart after
the fact costs an hour.

These are bench checks for a build you just wired. The milestones they feed
(M2, M4, M5) are upstream BUILD.md section 15, and this file deliberately stops
short of M5 -- that one needs blood, consent and SAFETY.md, not a script.
"""
from __future__ import annotations

import subprocess

from .hw import Bench, InterlockError
from .spectro import FLOOR, FULL_SCALE, Spectrometer

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


def _line(tag, name, detail=""):
    print(f"  [{tag:4s}] {name}" + (f" -- {detail}" if detail else ""))
    return tag


def check_i2c() -> str:
    """Both devices answer. 0x39 is the AS7341; 0x3C/0x3D is the OLED."""
    try:
        out = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception as e:
        return _line(FAIL, "I2C bus", f"i2cdetect failed: {e}")
    found = "39" in out
    oled = ("3c" in out) or ("3d" in out)
    if not found:
        return _line(FAIL, "AS7341 at 0x39", "not on the bus -- check SDA/SCL, "
                     "3V3, and that raspi-config enabled I2C")
    _line(PASS, "AS7341 at 0x39")
    _line(PASS if oled else WARN, "OLED at 0x3C/0x3D",
          "" if oled else "absent; measurements still work")
    return PASS


def check_interlock() -> str:
    """The laser must refuse to fire with the slot empty.

    Tested by asking it to, with no cartridge in, and requiring the refusal.
    A pass here means the SOFTWARE interlock works; it says nothing about the
    hardware one through the microswitch, which you verify with a meter.
    """
    with Bench() as b:
        if b.seated:
            return _line(WARN, "laser interlock",
                         "a cartridge is seated -- remove it and re-run to "
                         "actually test the refusal")
        try:
            with b.laser():
                pass
        except InterlockError:
            return _line(PASS, "laser interlock", "refused with slot empty")
        return _line(FAIL, "laser interlock",
                     "LASER FIRED WITH NO CARTRIDGE. Stop and fix GPIO22 "
                     "before anything else.")


def check_cartridge_switch() -> str:
    """GPIO22 must change state when you seat a cartridge."""
    with Bench() as b:
        empty = b.seated
        input("  seat a cartridge, then press Enter... ")
        seated = b.seated
        if empty == seated:
            return _line(FAIL, "cartridge switch",
                         f"GPIO22 did not change (still {'LOW' if seated else 'HIGH'})")
        if not seated:
            return _line(FAIL, "cartridge switch",
                         "reads HIGH when seated -- switch is wired inverted")
        return _line(PASS, "cartridge switch", "LOW when seated")


def check_emitters() -> str:
    """Each emitter must raise Clear above dark. Catches a dead LED or a
    swapped rail before it looks like a light leak."""
    with Bench() as b, Spectrometer() as s:
        with b.dark():
            dark = s.read().clear
        rows, bad = [], []
        for name, cm in (("white", b.white), ("940 nm IR", b.infrared)):
            with cm():
                lit = s.read().clear
            gain = lit - dark
            rows.append(f"{name} +{gain}")
            if gain < 200:
                bad.append(name)
        detail = ", ".join(rows) + f" (dark {dark})"
        if bad:
            return _line(FAIL, "emitters", detail +
                         f" -- no response from {', '.join(bad)}: check the "
                         "FET, the resistor, and which rail it went to")
        return _line(PASS, "emitters", detail)


def check_headroom(n: int = 20) -> str:
    """M2's precondition: 415 nm comfortably off the floor on a white card.

    At SENSOR_STANDOFF = 28 mm this is the check most likely to fail, and
    ASSEMBLY.md is explicit that a failure here is a result to report rather
    than a defect to bury.
    """
    with Bench() as b, Spectrometer() as s:
        with b.white():
            avg, rsd = s.average(n)
        pct = avg.channels[415] / FULL_SCALE * 100.0
        detail = f"415 nm at {pct:.1f}% of full scale, RSD {rsd[415]:.2f}% over {n}"
        if avg.channels[415] <= FLOOR:
            return _line(FAIL, "415 nm headroom", detail +
                         " -- on the ADC floor. Raise ATIME/ASTEP or gain, and "
                         "if it will not lift, SAY SO in the writeup")
        if pct < 10:
            return _line(WARN, "415 nm headroom", detail + " -- thin but usable")
        return _line(PASS, "415 nm headroom", detail)


def check_light_tight(n: int = 10) -> str:
    """M4: Clear under 0.5% of full scale with the chamber shut and lit."""
    print("  put the case under the brightest light you have, lid ON.")
    input("  press Enter when it is... ")
    with Bench() as b, Spectrometer() as s:
        with b.dark():
            avg, _ = s.average(n)
    pct = avg.clear / FULL_SCALE * 100.0
    detail = f"Clear at {pct:.3f}% of full scale"
    if pct >= 0.5:
        return _line(FAIL, "light-tight (M4)", detail +
                     " -- over 0.5%. Paint the bores matte black, check the "
                     "slot baffle and the lap joint")
    return _line(PASS, "light-tight (M4)", detail)


ORDER = [
    ("i2c", check_i2c, False),
    ("interlock", check_interlock, False),
    ("switch", check_cartridge_switch, True),
    ("emitters", check_emitters, False),
    ("headroom", check_headroom, False),
    ("lighttight", check_light_tight, True),
]


def main(only: str | None = None, skip_prompts: bool = False) -> int:
    print("CELL-4B self-test\n")
    results = {}
    for name, fn, interactive in ORDER:
        if only and name != only:
            continue
        if interactive and skip_prompts:
            _line(WARN, name, "skipped (needs you at the bench)")
            continue
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = _line(FAIL, name, f"{type(e).__name__}: {e}")
        if results.get(name) == FAIL:
            print("\n  stopping at the first failure -- later checks assume "
                  "this one passed.")
            break
    bad = sum(1 for v in results.values() if v == FAIL)
    print(f"\n{len(results)} checks, {bad} failed")
    return 1 if bad else 0
