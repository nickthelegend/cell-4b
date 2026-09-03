"""Command line: python3 -m cell4b <command>."""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cell4b", description="CELL-4B bench tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("selftest", help="bring-up checks, in fault-isolating order")
    t.add_argument("--only", help="run just one: i2c interlock switch emitters "
                                  "headroom lighttight")
    t.add_argument("--no-prompts", action="store_true",
                   help="skip the checks that need you at the bench")

    r = sub.add_parser("read", help="one averaged reading under white light")
    r.add_argument("-n", type=int, default=10)

    m = sub.add_parser("measure", help="a full dark/white/sample run")
    m.add_argument("label")
    m.add_argument("-n", type=int, default=10)
    m.add_argument("--out", default="data")

    s = sub.add_parser("speckle", help="M6 speckle series (needs a cartridge)")
    s.add_argument("tag")
    s.add_argument("--seconds", type=int, default=600)

    sub.add_parser("status", help="show pins, switch state and OLED presence")

    a = p.parse_args(argv)

    if a.cmd == "selftest":
        from .selftest import main as st
        return st(only=a.only, skip_prompts=a.no_prompts)

    if a.cmd == "status":
        from .display import Display
        from .hw import Bench
        with Bench() as b:
            print(f"  cartridge (GPIO22): {'SEATED' if b.seated else 'empty'}")
            print(f"  laser (GPIO6):      {'ON' if b.laser_on else 'off'}")
        d = Display()
        print(f"  OLED:               {'present' if d.ok else 'absent'}")
        if d.ok:
            d.lines("CELL-4B", "status ok")
        return 0

    if a.cmd == "read":
        from .hw import Bench
        from .spectro import Spectrometer
        with Bench() as b, Spectrometer() as s:
            with b.white():
                avg, rsd = s.average(a.n)
            hr = s.headroom(avg)
        print(f"  integration {avg.integration_ms:.0f} ms, gain {avg.gain}x, "
              f"n={a.n}")
        for band, v in avg.channels.items():
            print(f"   {band:>4} nm  {v:>6}  {hr[band]:5.1f}% FS  "
                  f"RSD {rsd[band]:5.2f}%")
        print(f"   clear    {avg.clear:>6}\n   nir      {avg.nir:>6}")
        if avg.saturated():
            print(f"  SATURATED: {avg.saturated()} -- lower gain or ATIME")
        if avg.on_floor():
            print(f"  ON THE FLOOR: {avg.on_floor()} -- raise ATIME/ASTEP")
        return 0

    if a.cmd == "measure":
        from .measure import run
        r = run(a.label, n=a.n, out_dir=a.out)
        print("  reflectance:")
        for band, v in r.reflectance().items():
            print(f"   {band:>4} nm  {v:.4f}")
        return 0

    if a.cmd == "speckle":
        from .camera import Speckle
        from .hw import Bench
        with Bench() as b, Speckle() as cam:
            if not cam.ok:
                print(f"  camera unavailable: {getattr(cam, 'error', '?')}")
                return 1
            shots = cam.series(a.tag, seconds=a.seconds, bench=b)
        print(f"  {len(shots)} frames -> data/speckle/")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
