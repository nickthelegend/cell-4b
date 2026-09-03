"""Emitters, the cartridge switch, and the laser interlock.

The interlock is the reason this file exists. ASSEMBLY.md wires the laser gate
through the microswitch, so hardware already refuses to fire it with the slot
empty -- but hardware interlocks fail closed only if they are wired right, and
nothing in software should assume that. So every laser call re-reads the switch
and refuses on its own account. Two independent refusals, one of which you can
test without a multimeter.

Pinout is ASSEMBLY.md section 5, and the rails are NOT interchangeable there:
the white LEDs sit behind 68 ohm to +5V (~28 mA), the 940 nm part behind 47 ohm
to +3V3 (~41 mA). Swap the rails and you either barely light the whites or cook
the IR. That is a soldering fact, not a software one, but it is why the two
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

# The laser needs 20-40 mA, far past a pin's 16 mA, so it cannot be sunk and
# always needs a real switch. False makes laser() say so instead of pretending.
LASER_FITTED = False

# --- ASSEMBLY.md section 5 -------------------------------------------------
PIN_WHITE_1 = 12
PIN_WHITE_2 = 16          # CELL-4B's addition; upstream drove this from the
                          # AS7341's LDR pin, which no breakout exposes.
PIN_IR_940 = 23
PIN_LASER = 6
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
        self.white_2 = DigitalOutputDevice(PIN_WHITE_2, active_high=hi,
                                           initial_value=False)
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
        for d in (self.white_1, self.white_2, self.ir_940, self._laser):
            try:
                d.off()
            except Exception:
                pass          # teardown must not raise; the pin is going away

    @contextmanager
    def white(self):
        """Both white LEDs, for the duration of the block."""
        self.white_1.on()
        self.white_2.on()
        time.sleep(self.settle)
        try:
            yield
        finally:
            self.white_1.off()
            self.white_2.off()

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
        if require_seated and not self.seated:
            raise InterlockError(
                "no cartridge seated (GPIO22 high) -- laser refused. "
                "Seat a cartridge, or pass require_seated=False if you are "
                "deliberately aligning with the shell open.")
        self._laser.on()
        time.sleep(self.settle)
        try:
            yield
        finally:
            self._laser.off()

    @contextmanager
    def dark(self):
        """Everything off, settled. The reference every reading subtracts."""
        self.all_off()
        time.sleep(self.settle)
        yield

    def close(self) -> None:
        self.all_off()
        for d in (self.white_1, self.white_2, self.ir_940,
                  self._laser, self.cartridge):
            try:
                d.close()
            except Exception:
                pass

    def __enter__(self) -> "Bench":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
