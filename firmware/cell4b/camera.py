"""Speckle capture from the lensless OV5647.

The lens is removed (ASSEMBLY.md section 3), so this is not a camera in the
usual sense -- there is no focus and no image, just a bare sensor 20 mm from
the spot at 45 degrees, reading the interference pattern the 650 nm laser makes
in the sample. Frames are saved raw and unprocessed; M6 is a 600 s series, and
what you do with it is analysis, not acquisition.

Capture never fires the laser itself. The caller holds the interlock, so the
laser cannot be on without a cartridge and cannot outlive the block.
"""
from __future__ import annotations

import time
from pathlib import Path


class Speckle:
    def __init__(self, out_dir: str | Path = "data/speckle"):
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.cam = None
        try:
            from picamera2 import Picamera2
            self.cam = Picamera2()
            # Fixed everything. Auto-exposure and auto-gain would chase the
            # speckle pattern and make consecutive frames incomparable, which
            # is the one property a time series needs.
            cfg = self.cam.create_still_configuration(
                raw={"size": self.cam.sensor_resolution})
            self.cam.configure(cfg)
            self.cam.set_controls({"AeEnable": False, "AwbEnable": False,
                                   "ExposureTime": 20000, "AnalogueGain": 1.0})
            self.cam.start()
            time.sleep(1.0)
        except Exception as e:
            self.error = str(e)

    @property
    def ok(self) -> bool:
        return self.cam is not None

    def frame(self, tag: str) -> Path | None:
        if not self.ok:
            return None
        p = self.out / f"{int(time.time()*1000)}-{tag}.dng"
        self.cam.capture_file(str(p), name="raw")
        return p

    def series(self, tag: str, seconds: int = 600, every: float = 2.0,
               bench=None) -> list[Path]:
        """M6's 600 s series. Requires a live Bench for the interlock."""
        if not self.ok:
            raise RuntimeError(f"camera unavailable: {getattr(self, 'error', '?')}")
        if bench is None:
            raise ValueError("pass the Bench -- the laser must stay interlocked")
        shots, t0 = [], time.time()
        with bench.laser():
            while time.time() - t0 < seconds:
                shots.append(self.frame(tag))
                time.sleep(every)
        return [s for s in shots if s]

    def close(self) -> None:
        if self.ok:
            try:
                self.cam.stop()
                self.cam.close()
            except Exception:
                pass

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()
