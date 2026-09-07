"""MAX3010x pulse sensor — the touch tier's liveness signal.

WHAT THIS MEASURES, and why it is a gate rather than a novelty. A fingertip on
the ring reflects the sensor's own red and IR LEDs back into its photodiode.
Blood volume in the capillaries rises and falls with every heartbeat, so the
reflected light is modulated at the pulse rate. That modulation is the signal:
a finger has it, a warm object does not, a printed patch does not, and a
photograph of a finger does not.

WHAT IT DOES NOT PROVE: whose finger. This is a liveness check, not identity.
It answers "is something alive touching this", which is exactly what the touch
tier claims and nothing more.

WHY IT IS SEPARATE FROM THE AS7341. The spectrometer answers a question about
COLOUR, at one instant. This answers a question about TIME -- is there periodic
motion in the 0.7-3.5 Hz band. Neither can substitute for the other, which is
the same argument the speckle channel makes for the blood tier.

ADDRESS 0x57 on I2C1, clear of the AS7341 at 0x39 and the OLED at 0x3C.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

I2C_ADDR = 0x57

# --- registers, MAX30102 datasheet table 1 ---------------------------------
REG_INTR_STATUS_1  = 0x00
REG_INTR_ENABLE_1  = 0x02
REG_FIFO_WR_PTR    = 0x04
REG_OVF_COUNTER    = 0x05
REG_FIFO_RD_PTR    = 0x06
REG_FIFO_DATA      = 0x07
REG_FIFO_CONFIG    = 0x08
REG_MODE_CONFIG    = 0x09
REG_SPO2_CONFIG    = 0x0A
REG_LED1_PA        = 0x0C          # red
REG_LED2_PA        = 0x0D          # IR
REG_PART_ID        = 0xFF

PART_MAX30102 = 0x15
PART_MAX30105 = 0x15               # same id; the difference is a green LED
PART_MAX30100 = 0x11

# 100 Hz is the useful floor. A pulse tops out near 3.5 Hz, so 100 Hz is ~28x
# oversampled -- plenty of margin for the filter and for dropped samples,
# without producing more data than a 10 s window needs.
SAMPLE_RATE = 100

# Perfusion index bounds, as AC/DC percent.
#
# The floor rejects things that are not modulating at all. The CEILING rejects
# MOTION, and it is the one that took a test failure to find: rhythmic waving
# over the sensor at 0.4 Hz put its second harmonic at 0.8 Hz, squarely inside
# the pulse band, and the gate called it a 48 bpm heartbeat. Frequency alone
# cannot tell a heartbeat from a hand, because a hand can move at heart rate.
#
# Amplitude can. Blood volume changes modulate reflected light by a fraction of
# a percent to a few percent. A finger physically moving on and off the ring
# changes it by tens of percent -- it is a different SIZE of effect, not a
# different frequency.
#
# 8.0 is a first cut from the literature's range for reflectance PPG and wants
# checking against this sensor on real fingers. M-something should measure it
# rather than inherit it from a comment.
PERFUSION_MIN = 0.05
PERFUSION_MAX = 8.0


@dataclass
class Pulse:
    bpm: float
    confidence: float          # 0..1, how periodic the signal actually is
    perfusion: float           # AC/DC percent -- how much light the pulse moves
    samples: int
    reason: str = ""

    @property
    def present(self) -> bool:
        """A pulse, not merely a number. All four have to hold."""
        return (self.confidence >= 0.5
                and 40.0 <= self.bpm <= 200.0
                and PERFUSION_MIN <= self.perfusion <= PERFUSION_MAX)


class NoSensor(RuntimeError):
    """No MAX3010x answered on the bus."""


class Max3010x:
    def __init__(self, i2c=None, address: int = I2C_ADDR):
        if i2c is None:
            import board, busio
            i2c = busio.I2C(board.SCL, board.SDA)
        self.i2c = i2c
        self.addr = address
        try:
            self.part_id = self._read(REG_PART_ID, 1)[0]
        except Exception as e:
            raise NoSensor(
                f"nothing answered at 0x{address:02x} -- check SDA/SCL and that "
                f"the breakout has power ({type(e).__name__})") from None
        if self.part_id not in (PART_MAX30102, PART_MAX30100):
            raise NoSensor(
                f"0x{address:02x} answered with part id 0x{self.part_id:02x}, "
                f"which is not a MAX3010x")
        self.reset()

    # ---- raw bus ----------------------------------------------------------

    def _write(self, reg: int, val: int) -> None:
        self.i2c.writeto(self.addr, bytes([reg, val]))

    def _read(self, reg: int, n: int) -> bytes:
        buf = bytearray(n)
        self.i2c.writeto_then_readfrom(self.addr, bytes([reg]), buf)
        return bytes(buf)

    # ---- configuration ----------------------------------------------------

    def reset(self) -> None:
        self._write(REG_MODE_CONFIG, 0x40)
        time.sleep(0.05)

    def configure(self, red_ma: float = 6.4, ir_ma: float = 6.4) -> None:
        """SpO2 mode: red and IR, 100 Hz, 411 us pulses, 18-bit.

        Current is deliberately modest. A brighter LED does not give a better
        pulse -- it saturates the photodiode against a fingertip and the AC
        component, which IS the measurement, disappears into a flat ceiling.
        """
        self._write(REG_INTR_ENABLE_1, 0xC0)       # FIFO almost full + new data
        self._write(REG_FIFO_WR_PTR, 0x00)
        self._write(REG_OVF_COUNTER, 0x00)
        self._write(REG_FIFO_RD_PTR, 0x00)
        # sample average 4, rollover on, almost-full at 17
        self._write(REG_FIFO_CONFIG, 0b0100_1111)
        self._write(REG_MODE_CONFIG, 0x03)         # red + IR
        # ADC range 4096 nA, 100 Hz, 411 us -> 18-bit resolution
        self._write(REG_SPO2_CONFIG, 0b0010_0111)
        step = 0.2                                  # mA per LSB
        self._write(REG_LED1_PA, min(255, int(red_ma / step)))
        self._write(REG_LED2_PA, min(255, int(ir_ma / step)))

    # ---- sampling ---------------------------------------------------------

    def read_fifo(self) -> tuple[int, int]:
        """One (red, ir) pair. Both are 18-bit, big-endian, top 6 bits unused."""
        d = self._read(REG_FIFO_DATA, 6)
        red = ((d[0] << 16) | (d[1] << 8) | d[2]) & 0x03FFFF
        ir = ((d[3] << 16) | (d[4] << 8) | d[5]) & 0x03FFFF
        return red, ir

    def collect(self, seconds: float = 10.0) -> tuple[list, list]:
        """Block for `seconds`, returning (red, ir) sample lists."""
        red, ir = [], []
        n = int(seconds * SAMPLE_RATE)
        period = 1.0 / SAMPLE_RATE
        t = time.monotonic()
        for _ in range(n):
            r, i = self.read_fifo()
            red.append(r); ir.append(i)
            t += period
            dt = t - time.monotonic()
            if dt > 0:
                time.sleep(dt)
        return red, ir


# --------------------------------------------------------------- analysis ----
# Pure maths from here down: no hardware, so it is testable without a sensor
# and IS tested that way. Every failure mode below was found on synthetic
# signals before the part arrived.

def analyse(samples, rate: int = SAMPLE_RATE) -> Pulse:
    """Is there a heartbeat in this, and how sure are we?

    Three numbers, and a pulse needs all three:

      bpm         where the energy is, inside 40-200
      confidence  how much of the band's energy sits at that one frequency.
                  Noise spreads energy everywhere; a pulse concentrates it.
      perfusion   AC/DC. A finger modulates the reflected light by a fraction
                  of a percent to a few percent. A static object modulates it
                  by nothing, however periodic the noise happens to look.

    Confidence alone is not enough, and that is the point. Mains hum at 50 Hz
    is beautifully periodic and is not a heartbeat; a bright flat surface gives
    a huge DC with no AC at all. Requiring all three is what stops those.
    """
    import numpy as np

    x = np.asarray(samples, dtype=float)
    n = x.size
    if n < rate * 3:
        return Pulse(0.0, 0.0, 0.0, n,
                     f"only {n / rate:.1f}s of data; need at least 3s")

    dc = float(x.mean())
    if dc <= 0:
        return Pulse(0.0, 0.0, 0.0, n, "no signal -- is the LED on?")

    # Detrend before anything else. A finger settling onto the ring produces a
    # large slow ramp that dwarfs the pulse and smears across the whole
    # spectrum; a straight-line fit removes most of it.
    t = np.arange(n)
    x = x - np.polyval(np.polyfit(t, x, 1), t)

    ac = float(np.percentile(x, 95) - np.percentile(x, 5))
    perfusion = ac / dc * 100.0

    w = np.hanning(n)
    spec = np.abs(np.fft.rfft(x * w)) ** 2
    freq = np.fft.rfftfreq(n, 1.0 / rate)

    # 0.7-3.5 Hz is 42-210 bpm. Below that is breathing and hand tremor; above
    # it there is nothing a heart does.
    band = (freq >= 0.7) & (freq <= 3.5)
    if not band.any() or spec[band].sum() <= 0:
        return Pulse(0.0, 0.0, perfusion, n, "no energy in the pulse band")

    k = int(np.argmax(np.where(band, spec, 0)))
    bpm = float(freq[k] * 60.0)

    # Concentration: the peak and its immediate neighbours, over the whole
    # band. A single sharp line scores high; broadband noise scores low.
    lo, hi = max(0, k - 2), min(spec.size, k + 3)
    confidence = float(spec[lo:hi].sum() / spec[band].sum())

    reason = ""
    if perfusion < PERFUSION_MIN:
        reason = f"perfusion {perfusion:.3f}% -- nothing is modulating the light"
    elif perfusion > PERFUSION_MAX:
        reason = (f"perfusion {perfusion:.2f}% -- far too large for blood "
                  f"volume; this is the finger moving, not the heart")
    elif confidence < 0.5:
        reason = f"confidence {confidence:.2f} -- energy is spread, not a beat"
    elif not 40.0 <= bpm <= 200.0:
        reason = f"{bpm:.0f} bpm is outside 40-200"
    return Pulse(bpm, confidence, perfusion, n, reason)


def read_pulse(seconds: float = 10.0, i2c=None) -> Pulse:
    """Configure, sample, analyse. The whole touch-tier measurement."""
    dev = Max3010x(i2c=i2c)
    dev.configure()
    time.sleep(0.3)                      # let the FIFO fill with real samples
    _red, ir = dev.collect(seconds)
    return analyse(ir)
