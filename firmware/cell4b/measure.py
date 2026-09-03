"""One measurement run: dark, white, and the sample -- in that order.

The order is not arbitrary. Dark first, because every later number is a
difference against it and the sensor's own offset drifts with temperature.
White second, on the reference cartridge, because that is what turns raw
counts into something comparable between runs and between machines. Sample
last, so the two references were taken with the chamber at the temperature the
sample sees.

Nothing here interprets a result. There is no threshold in this file and no
verdict; M7 in upstream BUILD.md is where thresholds.json gets earned, from
data, with an ROC to justify it. Writing a number in here now would be
inventing the answer the instrument exists to measure.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .hw import Bench, InterlockError
from .spectro import BANDS, Reading, Spectrometer


@dataclass
class Run:
    label: str
    dark: dict
    white: dict
    sample: dict
    rsd: dict
    started: float = field(default_factory=time.time)
    notes: str = ""

    def reflectance(self) -> dict[int, float]:
        """(sample - dark) / (white - dark), per band.

        Returns nan for a band where the white reference is not meaningfully
        above dark -- a zero denominator there would manufacture a ratio out
        of two noise figures.
        """
        out = {}
        for b in BANDS:
            k = str(b)
            num = self.sample["channels"][k] - self.dark["channels"][k]
            den = self.white["channels"][k] - self.dark["channels"][k]
            out[b] = (num / den) if den > 64 else float("nan")
        return out


def _as_dict(r: Reading) -> dict:
    d = asdict(r)
    d["channels"] = {str(k): v for k, v in r.channels.items()}
    d["integration_ms"] = round(r.integration_ms, 2)
    return d


def run(label: str, n: int = 10, out_dir: str | Path = "data",
        require_seated: bool = True) -> Run:
    """Take a full dark/white/sample set and write it to out_dir as JSON."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with Bench() as bench, Spectrometer() as spec:
        if require_seated and not bench.seated:
            raise InterlockError(
                "no cartridge seated (GPIO22 high). Seat one before measuring.")

        with bench.dark():
            dark = spec.read()

        with bench.white():
            white, rsd = spec.average(n)

        # The sample read reuses the same white illumination: a reflectance
        # ratio is only meaningful if numerator and denominator saw the same
        # source. Swap the cartridge between these two and the ratio is void.
        input("  seat the SAMPLE cartridge, then press Enter... ")
        if require_seated and not bench.seated:
            raise InterlockError("sample cartridge not seated.")
        with bench.white():
            sample, _ = spec.average(n)

    r = Run(label=label, dark=_as_dict(dark), white=_as_dict(white),
            sample=_as_dict(sample), rsd={str(k): round(v, 3)
                                          for k, v in rsd.items()})
    path = out / f"{int(r.started)}-{label}.json"
    path.write_text(json.dumps(asdict(r) | {"reflectance":
                    {str(k): v for k, v in r.reflectance().items()}}, indent=1))
    print(f"  wrote {path}")
    return r
