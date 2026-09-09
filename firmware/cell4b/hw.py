"""Emitters, the cartridge switch, and the laser interlock.

The interlock is the reason this file exists. ASSEMBLY.md wires the laser gate
through the microswitch, so hardware already refuses to fire it with the slot
empty -- but hardware interlocks fail closed only if they are wired right, and
nothing in software should assume that. So every laser call re-reads the switch
and refuses on its own account. Two independent refusals, one of which you can
test without a multimeter.

Pinout is ASSEMBLY.md section 5. This build fits 220 ohm on all three emitters,
NOT the 68/47 the optical design asks for: those assume a transistor in the
ground return, and with EMITTER_SINK the pin itself carries the current against
a 16 mA rating -- 68 ohm is 27.9 mA and 47 ohm is 41.5 mA.

That value is not free-floating: spectro.EMITTER_OHMS must agree with it,
because atime_for() scales integration time from it to hold collected light
constant. This line said 120 while EMITTER_OHMS said 220, and a day of bench
scripts copied the 120 timing -- every reading collected 1.8x less light than
the hardware could deliver, which reads as a dim instrument rather than as a
wrong constant.

The rails are still NOT interchangeable. Whites on +5V (Vf ~3.1 V, so +3V3
barely lights them); the 940 nm on +3V3, because a sink LED floats its pin to
(rail - Vf) while the pin is an input, and 5 - 1.35 = 3.65 V is over the pad
limit. That is a soldering fact, not a software one, but it is why the two
groups are named apart here instead of being one list.
"""
from __future__ import annotations

import atexit
import time
from contextlib import contextmanager

from gpiozero import DigitalOutputDevice, Button

# --- how the emitters are wired -------------------------------------------
# Two topologies, and this flag MUST match the solder joints -- get it wrong
# and every emitter is lit exactly when it should be dark.
#
#   SINK (no transistors):  +V -> R -> LED -> GPIO.  The pin sinks the current;
#       pin LOW = lit. A GPIO sources only 3.3 V, which cannot light a 3.1 V
#       white LED, but it can SINK one running off the 5 V rail.
#
#   SOURCE (2N7000 / BJT):  GPIO -> gate/base, transistor in the ground return;
#       pin HIGH = lit.
#
# The sink build is safe on a floating pin -- during boot GPIOs are inputs, and
# the LED stops conducting once the pin reaches (rail - Vf), so a white on +5 V
# can pull a pad no higher than 1.90 V. That is WHY the 940 nm stays on +3V3:
# from 5 V its 1.35 V Vf would let the pin float to 3.65 V, over the 3.3 V pad
# limit. Never move the IR to the 5 V rail in a sink build.
EMITTER_SINK = True

# The laser needs 20-40 mA, far past a pin's 16 mA, so it can never be sunk by
# a pin the way the LEDs are. It needs either a transistor or -- as on this
# build -- a module with a TTL ENABLE input, which is a logic input drawing
# almost nothing while the module takes its current straight off +5 V.
#
# Set True once that driver exists. False makes laser() say so rather than
# pretending, which is the honest failure: a laser that silently does nothing
# reads exactly like a laser that is working and pointed somewhere harmless.
LASER_FITTED = True

# BENCH ONLY. True lets laser() fire with no cartridge seated.
#
# This exists because the cartridge switch is not built yet -- there are no
# printed cartridges and no microswitch in the slot, so GPIO22 has nothing
# real to report. It is NOT a convenience switch for when the interlock is
# annoying, and every call it permits announces itself.
#
# Set it back to False the moment a real switch is in a real slot. An
# interlock that stays overridden is not an interlock, and this flag exists
# to be removed.
# The switch now exists and GPIO22 follows it, so the bypass is gone. It was
# only ever a stand-in for a slot that had no switch in it, and a full
# component run on 2026-09-07 showed what leaving it costs: the laser fired
# with nothing seated, and the run recorded its own interlock as broken.
BENCH_NO_INTERLOCK = False

# --- ASSEMBLY.md section 5 -------------------------------------------------
PIN_WHITE_1 = 13          # was GPIO12 (header pin 32). A short on this
                          # emitter's leg pulled 5V onto the pin and reset
                          # the board three times; GPIO12 stopped driving
                          # and never recovered. Moved to header pin 33.
PIN_WHITE_2 = 16          # CELL-4B's addition; upstream drove this from the
                          # AS7341's LDR pin, which no breakout exposes.
PIN_IR_940 = 23
PIN_LASER = 6
# A 400 nm violet emitter, for G3. The head has exactly three 45 deg / 12 mm
# LED bores and all three are spoken for, so a fourth emitter cannot be added
# without reprinting the optical head. Until then it displaces white #2 and
# takes its bore and its pin -- chosen over the 940 nm because losing G2 costs
# a gate that works, while losing half the white light only costs signal.
#
# The gates survive that: G1 and G3 are ratios of a sample against the printed
# white patch AT THE SAME WAVELENGTH, from the same emitter, so illumination
# geometry cancels in each ratio independently. That is what the patch is for.
#
# Set WHITE2_IS_VIOLET True once the swap is soldered. It is not a preference:
# get it wrong and the code drives an LED that is not in that bore.
WHITE2_IS_VIOLET = False
PIN_VIOLET = PIN_WHITE_2      # same bore, same pin -- it replaces it

PIN_CARTRIDGE = 22        # internal pull-up, LOW when a cartridge is seated


class InterlockError(RuntimeError):
    """Raised when the laser is asked to fire with no cartridge seated."""


class Bench:
    """Owns every pin. Construct one, use it as a context manager.

    Emitters are initialised OFF and returned to OFF on the way out, including
    on an unhandled exception and on interpreter exit. A 650 nm module left on
    by a crashed script is exactly the failure this class is shaped to prevent.
    """

    def __init__(self, settle: float = 0.05):
        self.settle = settle
        # active_high mirrors the wiring: in a sink build "lit" is a LOW pin.
        # gpiozero handles the inversion, so .on() still means lit either way.
        hi = not EMITTER_SINK
        self.white_1 = DigitalOutputDevice(PIN_WHITE_1, active_high=hi,
                                           initial_value=False)
        # Exactly one of these owns the pin. gpiozero refuses two devices on
        # one GPIO, and that refusal is the point: the bore holds one LED.
        if WHITE2_IS_VIOLET:
            self.white_2 = None
            self.violet = DigitalOutputDevice(PIN_VIOLET, active_high=hi,
                                              initial_value=False)
        else:
            self.white_2 = DigitalOutputDevice(PIN_WHITE_2, active_high=hi,
                                               initial_value=False)
            self.violet = None
        self.ir_940 = DigitalOutputDevice(PIN_IR_940, active_high=hi,
                                          initial_value=False)
        # The laser gate is always a real transistor, so always active-high.
        self._laser = DigitalOutputDevice(PIN_LASER, initial_value=False)
        # pull_up=True matches the switch wiring: LOW == seated, so
        # is_pressed reads True exactly when a cartridge is in.
        self.cartridge = Button(PIN_CARTRIDGE, pull_up=True, bounce_time=0.02)
        atexit.register(self.all_off)

    # -- state ------------------------------------------------------------
    @property
    def seated(self) -> bool:
        """True when a cartridge is in the slot."""
        return bool(self.cartridge.is_pressed)

    @property
    def laser_on(self) -> bool:
        return bool(self._laser.value)

    # -- emitters ---------------------------------------------------------
    def all_off(self) -> None:
        for d in (self.white_1, self.white_2, self.violet, self.ir_940,
                  self._laser):
            if d is None:
                continue
            try:
                d.off()
            except Exception:
                pass          # teardown must not raise; the pin is going away

    @contextmanager
    def white(self):
        """The white emitters, for the duration of the block.

        One of them when the violet has taken white #2's bore. Half the light,
        which costs signal and costs nothing else: every gate that uses this
        is a ratio against the white patch under the same illumination.
        """
        self.white_1.on()
        if self.white_2 is not None:
            self.white_2.on()
        time.sleep(self.settle)
        try:
            yield
        finally:
            self.white_1.off()
            if self.white_2 is not None:
                self.white_2.off()

    @contextmanager
    def ultraviolet(self):
        """The 400 nm emitter, which is the only way G3 can be measured.

        G3 is (R630 - R415)/(R630 + R415), and the white LEDs are blue-pump
        phosphor: they emit nothing at 415, so F1 reads a hard zero and the
        gate cannot run for any sample. See FINDINGS.md 12.
        """
        if self.violet is None:
            raise RuntimeError(
                "no violet emitter: set hw.WHITE2_IS_VIOLET True once the "
                "400 nm LED is soldered into white #2's bore")
        self.violet.on()
        time.sleep(self.settle)
        try:
            yield
        finally:
            self.violet.off()

    @contextmanager
    def infrared(self):
        self.ir_940.on()
        time.sleep(self.settle)
        try:
            yield
        finally:
            self.ir_940.off()

    @contextmanager
    def laser(self, require_seated: bool = True):
        """The 650 nm module. Refuses to fire with the slot empty.

        require_seated=False exists for a bench alignment check with the shell
        open, and is deliberately awkward to reach: you have to pass it, and
        the caller that does should say why.
        """
        if not LASER_FITTED:
            raise InterlockError(
                "no laser driver fitted (hw.LASER_FITTED is False). The 650 nm "
                "module needs 20-40 mA, well past a GPIO's 16 mA, so it cannot "
                "be sunk like the LEDs -- it needs a transistor. Everything up "
                "to M5 runs without it; only M6 speckle needs the laser.")
        if require_seated and BENCH_NO_INTERLOCK and not self.seated:
            # Loud on purpose: a bypassed safety should never be silent.
            print("  !! BENCH_NO_INTERLOCK: firing with no cartridge seated. "
                  "This is not a safe configuration -- it is a stand-in until "
                  "the switch exists.")
        elif require_seated and not self.seated:
            raise InterlockError(
                "no cartridge seated (GPIO22 high) -- laser refused. "
                "Seat a cartridge, or pass require_seated=False if you are "
                "deliberately aligning with the shell open.")
        # The check above happens ONCE, but the block can be long -- M6's
        # speckle series holds this open for 600 s. Checking only at entry
        # means a switch that is pressed for a moment buys a ten-minute
        # exposure, which is the difference between an enable and a bypass.
        # So the beam also follows the switch for as long as it is on: let go
        # and it drops, whether the switch is a lever in the slot or a tactile
        # held by hand.
        cut = {"n": 0}

        def _on_release():
            self._laser.off()               # beam first, bookkeeping after
            cut["n"] += 1
            print("  !! switch released with the laser on -- beam cut.")

        prev = self.cartridge.when_released
        if require_seated:
            self.cartridge.when_released = _on_release
        self._laser.on()
        time.sleep(self.settle)
        try:
            yield
        finally:
            self._laser.off()
            if require_seated:
                self.cartridge.when_released = prev
        # Only reached on a clean exit. A run that lost the beam part way is
        # not a short run, it is a run whose later frames are dark -- say so
        # rather than letting it look like data.
        if cut["n"]:
            raise InterlockError(
                f"the cartridge switch opened {cut['n']}x while the laser was "
                "on. The beam was cut each time, so frames after the first "
                "break are dark -- discard this run and repeat it.")

    @contextmanager
    def dark(self):
        """Everything off, settled. The reference every reading subtracts."""
        self.all_off()
        time.sleep(self.settle)
        yield

    def close(self) -> None:
        self.all_off()
        for d in (self.white_1, self.white_2, self.violet, self.ir_940,
                  self._laser, self.cartridge):
            if d is None:
                continue
            try:
                d.close()
            except Exception:
                pass

    def __enter__(self) -> "Bench":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
