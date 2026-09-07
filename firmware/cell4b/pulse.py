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

# --- two chips, two register maps ------------------------------------------
#
# The MAX30100 and MAX30102 share an address and a family name and almost
# nothing else. Writing 0x03 to "MODE_CONFIG" configures SpO2 mode on one and
# writes to the FIFO read pointer on the other, and neither complains. So the
# part id is read FIRST and the map is chosen from it.
#
#                      MAX30100      MAX30102
#   part id            0x11          0x15
#   FIFO data          0x05          0x07
#   mode config        0x06          0x09
#   samples            4 bytes       6 bytes
#   resolution         16-bit        18-bit
#   channel order      IR, RED       RED, IR
#
# The channel order is the one that fails silently: read a MAX30100 with the
# 30102's order and you get a valid-looking pulse from the wrong LED.

# 100 Hz is the useful floor. A pulse tops out near 3.5 Hz, so this is ~28x
# oversampled -- margin for the filter and for dropped samples, without
# producing more data than a 10 s window needs.
SAMPLE_RATE = 100

# Perfusion index bounds, as AC/DC percent.
#
# The floor rejects things that are not modulating at all. The CEILING rejects
# MOTION, and it took a test failure to find: rhythmic waving at 0.4 Hz put its
# second harmonic at 0.8 Hz, inside the pulse band, and the gate called it a
# 48 bpm heartbeat. Frequency alone cannot tell a heartbeat from a hand,
# because a hand can move at heart rate.
#
# Amplitude can. Blood volume moves reflected light by a fraction of a percent
# to a few percent; a finger physically moving on and off the ring moves it by
# tens of percent. A different SIZE of effect, not a different frequency.
#
# 8.0 is a first cut from the literature for reflectance PPG and wants
# measuring against this sensor on real fingers -- it is the one number here
# that has never met a finger.
PERFUSION_MIN = 0.05
PERFUSION_MAX = 8.0


PART_MAX30100 = 0x11
PART_MAX30102 = 0x15               # MAX30105 shares this id; it adds green

REG_PART_ID = 0xFF
REG_REV_ID  = 0xFE

MAP_30100 = dict(
    int_status=0x00, int_enable=0x01, fifo_wr=0x02, ovf=0x03, fifo_rd=0x04,
    fifo_data=0x05, mode=0x06, spo2=0x07, led=0x09,
    sample_bytes=4, ir_first=True,
)
MAP_30102 = dict(
    int_status=0x00, int_enable=0x02, fifo_wr=0x04, ovf=0x05, fifo_rd=0x06,
    fifo_data=0x07, fifo_config=0x08, mode=0x09, spo2=0x0A,
    led1=0x0C, led2=0x0D,
    sample_bytes=6, ir_first=False,
)

# MAX30100 LED current steps, datasheet table 5. Not linear, so it is a table.
LED_CURRENT_30100 = [0.0, 4.4, 7.6, 11.0, 14.2, 17.4, 20.8, 24.0,
                     27.1, 30.6, 33.8, 37.0, 40.2, 43.6, 46.8, 50.0]

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
    """Either part. The map is chosen from the id, never assumed."""

    def __init__(self, i2c=None, address: int = I2C_ADDR):
        if i2c is None:
            import board, busio
            i2c = busio.I2C(board.SCL, board.SDA)
        self.i2c = i2c
        self.addr = address
        try:
            self.part_id = self._read(REG_PART_ID, 1)[0]
            self.rev_id = self._read(REG_REV_ID, 1)[0]
        except Exception as e:
            raise NoSensor(
                f"nothing answered at 0x{address:02x} -- check VIN, GND, and "
                f"that SDA/SCL reach pins 3 and 5 ({type(e).__name__})") from None
        if self.part_id == PART_MAX30100:
            self.m, self.name = MAP_30100, "MAX30100"
        elif self.part_id == PART_MAX30102:
            self.m, self.name = MAP_30102, "MAX30102/30105"
        else:
            raise NoSensor(
                f"0x{address:02x} answered with part id 0x{self.part_id:02x}, "
                f"which is neither a MAX30100 (0x11) nor a MAX30102 (0x15)")
        self.reset()

    # ---- raw bus ----------------------------------------------------------

    def _write(self, reg: int, val: int) -> None:
        while not self.i2c.try_lock():
            pass
        try:
            self.i2c.writeto(self.addr, bytes([reg, val]))
        finally:
            self.i2c.unlock()

    def _read(self, reg: int, n: int) -> bytes:
        buf = bytearray(n)
        while not self.i2c.try_lock():
            pass
        try:
            self.i2c.writeto_then_readfrom(self.addr, bytes([reg]), buf)
        finally:
            self.i2c.unlock()
        return bytes(buf)

    # ---- configuration ----------------------------------------------------

    def reset(self) -> None:
        self._write(self.m["mode"], 0x40)
        time.sleep(0.05)

    def configure(self, red_ma: float = 7.6, ir_ma: float = 7.6) -> None:
        """SpO2 mode, ~100 Hz, both LEDs.

        Current is deliberately modest. A brighter LED does not give a better
        pulse -- against a fingertip it saturates the photodiode and the AC
        component, which IS the measurement, flattens into the ceiling.
        """
        m = self.m
        self._write(m["fifo_wr"], 0x00)
        self._write(m["ovf"], 0x00)
        self._write(m["fifo_rd"], 0x00)

        if self.part_id == PART_MAX30100:
            # SPO2_CONFIG: HI_RES_EN | SR=100Hz (001) | PW=1600us, 16-bit (11)
            self._write(m["spo2"], 0b0100_0111)
            def step(ma):
                return min(range(16), key=lambda i: abs(LED_CURRENT_30100[i] - ma))
            self._write(m["led"], (step(red_ma) << 4) | step(ir_ma))
            self._write(m["mode"], 0x03)            # SpO2: red + IR
        else:
            self._write(m["fifo_config"], 0b0100_1111)
            self._write(m["spo2"], 0b0010_0111)
            self._write(m["led1"], min(255, int(red_ma / 0.2)))
            self._write(m["led2"], min(255, int(ir_ma / 0.2)))
            self._write(m["mode"], 0x03)

    # ---- sampling ---------------------------------------------------------

    def read_fifo(self) -> tuple[int, int]:
        """One (red, ir) pair, whichever way round the part reports them."""
        m = self.m
        d = self._read(m["fifo_data"], m["sample_bytes"])
        if m["sample_bytes"] == 4:                  # MAX30100, 16-bit, IR first
            a = (d[0] << 8) | d[1]
            b = (d[2] << 8) | d[3]
        else:                                       # MAX30102, 18-bit, RED first
            a = ((d[0] << 16) | (d[1] << 8) | d[2]) & 0x03FFFF
            b = ((d[3] << 16) | (d[4] << 8) | d[5]) & 0x03FFFF
        return (b, a) if m["ir_first"] else (a, b)

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
    #
    # Both ends are clamped INTO the band, and that matters more than it looks.
    # A peak sitting on the band edge -- 42 bpm is exactly 0.7 Hz -- had its
    # neighbourhood reach outside, so the numerator included energy the
    # denominator did not and confidence came back as 1.05. A ratio above 1 is
    # not a very good score, it is a broken one, and it was flattering the
    # readings closest to the boundary.
    idx = np.flatnonzero(band)
    lo, hi = max(idx[0], k - 2), min(idx[-1] + 1, k + 3)
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
