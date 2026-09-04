"""AS7341 spectrometer, wrapped for a 28 mm standoff.

The wrapping is the point. ASSEMBLY.md section 6 says raise ATIME/ASTEP before
M2 because this sensor sits at SENSOR_STANDOFF = 28 mm rather than upstream's
9 mm. Irradiance falls with the square of that distance, so the same integration
that lands mid-scale upstream lands near the ADC floor here -- roughly (28/9)^2
= 9.7x less light. Every default in this file is chosen for that, and
`headroom()` exists so you can prove it on a white card instead of trusting it.

Channels are F1..F8 (415, 445, 480, 515, 555, 590, 630, 680 nm) plus Clear and
NIR. 415 nm is the one M5 turns on: it is where haemoglobin absorbs and red
food dye does not.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field

import board
import busio
from adafruit_as7341 import AS7341

I2C_ADDR = 0x39

# 415 nm first, because it is the channel the whole instrument exists to read.
BANDS = (415, 445, 480, 515, 555, 590, 630, 680)

# 16-bit ADC. Above this we call it saturated and refuse to trust the number.
FULL_SCALE = 65535
SATURATED = 0.95 * FULL_SCALE
# Below this a channel is in the noise and any ratio built on it is fiction.
FLOOR = 0.02 * FULL_SCALE

# The Adafruit driver's `gain` is an ENUM INDEX, not a multiplier -- setting it
# to 8 selects index 8, which is 128x. That silently ran this file at 16x the
# intended gain until an out-of-range value (64) finally raised. Everything
# here speaks in multipliers and converts at the boundary.
GAIN_STEPS = {0.5: 0, 1: 1, 2: 2, 4: 3, 8: 4, 16: 5, 32: 6,
              64: 7, 128: 8, 256: 9, 512: 10}


@dataclass
class Reading:
    """One set of channels, with the gain and timing that produced it."""
    channels: dict[int, int]
    clear: int
    nir: int
    atime: int
    astep: int
    gain: int
    t: float = field(default_factory=time.time)

    @property
    def integration_ms(self) -> float:
        """(ATIME+1) * (ASTEP+1) * 2.78 us, per the AS7341 datasheet."""
        return (self.atime + 1) * (self.astep + 1) * 2.78 / 1000.0

    def saturated(self) -> list[int]:
        return [b for b, v in self.channels.items() if v >= SATURATED]

    def on_floor(self) -> list[int]:
        return [b for b, v in self.channels.items() if v <= FLOOR]


class Spectrometer:
    """The AS7341 at 0x39, with defaults for a 28 mm standoff."""

    # ATIME 99 / ASTEP 1799 is ~500 ms: long, deliberately, and for two
    # independent reasons that stack.
    #
    #   1. The sensor is at 28 mm, not upstream's 9 mm -- about 9.7x less light.
    #   2. This build runs 120 ohm emitter resistors rather than the 68/47 the
    #      design calls for, which is 15.0 mA into the whites (59% of design)
    #      and 15.4 mA into the 940 nm (43%).
    #
    # (2) alone wants 1.7x more integration for the whites, so 278 ms became
    # 500 ms. If you fit the design resistors later this can go back down --
    # but verify with headroom() rather than assuming, in either direction.
    def __init__(self, atime: int = 99, astep: int = 1799, gain: int = 8):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.dev = AS7341(self.i2c, address=I2C_ADDR)
        self.set_timing(atime, astep, gain)

    def set_timing(self, atime: int, astep: int, gain: float) -> None:
        if gain not in GAIN_STEPS:
            raise ValueError(
                f"gain must be one of {sorted(GAIN_STEPS)} (a multiplier, "
                f"not the register index) -- got {gain}")
        self.atime, self.astep, self.gain = atime, astep, gain
        self.dev.atime = atime
        self.dev.astep = astep
        self.dev.gain = GAIN_STEPS[gain]
        # One integration plus slack, so the first read after a change is not
        # a leftover from the old timing.
        self._wait = ((atime + 1) * (astep + 1) * 2.78 / 1e6) + 0.05

    def read(self) -> Reading:
        time.sleep(self._wait)
        ch = self.dev.all_channels          # F1..F8 in order
        return Reading(channels=dict(zip(BANDS, ch)),
                       clear=self.dev.channel_clear,
                       nir=self.dev.channel_nir,
                       atime=self.atime, astep=self.astep, gain=self.gain)

    def average(self, n: int = 10) -> tuple[Reading, dict[int, float]]:
        """n reads averaged, plus per-band relative standard deviation in %.

        RSD is what M2 is stated in ("< 1 % RSD over 100 reads"), so it is
        returned rather than left for the caller to recompute.
        """
        runs = [self.read() for _ in range(n)]
        mean = {b: int(statistics.fmean(r.channels[b] for r in runs))
                for b in BANDS}
        rsd = {}
        for b in BANDS:
            vals = [r.channels[b] for r in runs]
            m = statistics.fmean(vals)
            rsd[b] = (statistics.stdev(vals) / m * 100.0) if m and n > 1 else 0.0
        last = runs[-1]
        avg = Reading(channels=mean,
                      clear=int(statistics.fmean(r.clear for r in runs)),
                      nir=int(statistics.fmean(r.nir for r in runs)),
                      atime=last.atime, astep=last.astep, gain=last.gain)
        return avg, rsd

    def headroom(self, r: Reading) -> dict[int, float]:
        """Each band as a percentage of full scale.

        ASSEMBLY.md section 6: confirm 415 nm is comfortably off the floor on a
        white card, and if it is not, say so in the writeup -- that is a
        result, not a bug to hide.
        """
        return {b: v / FULL_SCALE * 100.0 for b, v in r.channels.items()}

    def close(self) -> None:
        try:
            self.i2c.deinit()
        except Exception:
            pass

    def __enter__(self) -> "Spectrometer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
