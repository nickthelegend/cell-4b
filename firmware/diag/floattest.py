"""Does the IR LED light when GPIO23 is merely RELEASED?

Sink drive from a 5V rail has a trap. While a program runs, the pin is
actively driven HIGH to keep the LED off. When the program exits, gpiozero
releases the pin to an input -- and 5V through the resistor and the LED then
forward-biases the pin's ESD clamp diode into the 3.3V rail. Current flows,
the LED lights, and it stays lit with nothing running. It also back-feeds
3.3V, which is the same abuse that likely took GPIO12.

If that is what is happening, holding the pin HIGH collapses the baseline
and releasing it restores it.
"""
import time
from gpiozero import DigitalOutputDevice
from cell4b.spectro import Spectrometer, atime_for, EMITTER_OHMS

s = Spectrometer(); s.set_timing(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)

def nir():
    time.sleep(0.4)
    return float(s.read().nir)

print(f"  pin released (as found)     nir {nir():7.0f}")

led = DigitalOutputDevice(23, active_high=False, initial_value=False)
time.sleep(0.6)
held_off = nir()
print(f"  pin driven HIGH (LED off)   nir {held_off:7.0f}")

led.on(); time.sleep(0.6)
driven_on = nir()
print(f"  pin driven LOW  (LED on)    nir {driven_on:7.0f}")

led.off(); time.sleep(0.4)
led.close()                      # releases the pin back to an input
time.sleep(0.8)
released = nir()
print(f"  pin released again          nir {released:7.0f}")
print()
if released - held_off > 300:
    print("  CONFIRMED. The LED lights whenever the pin is not actively held")
    print("  high -- 5V is pushing current through the pin's clamp diode.")
    print("  Move that anode from +5V to +3.3V and it stops, because 3.3V")
    print("  cannot forward-bias a clamp into the 3.3V rail.")
else:
    print("  Not the floating pin. The source is something else.")
