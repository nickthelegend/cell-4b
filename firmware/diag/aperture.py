"""Own LED vs the room. Separates 'sensor is blind' from 'chamber is dark'.

If the aperture is blocked at ~0 mm (glue over the window, or the breakout
glued face-down), the on-board LED reflects off the obstruction and pegs the
ADC while everything further away reads nothing.
"""
import time
from cell4b.spectro import Spectrometer, BANDS
from cell4b.display import Display

s = Spectrometer()
d = Display()

def snap():
    time.sleep(0.3)
    r = s.read()
    return sum(r.channels.values()), r.clear, r.nir, dict(r.channels)

print(f"  atime={s.atime} astep={s.astep} gain={s.gain}x  "
      f"integration={s.read().integration_ms:.0f} ms\n")

d.lines("APERTURE", "TEST", "", "room light", "")
tot, c, n, ch = snap()
print(f"  ROOM LIGHT, own LED off : sum={tot:8.0f}  clear={c:7.0f} nir={n:6.0f}")
room = tot

d.lines("APERTURE", "TEST", "", "own LED ON", "")
try:
    s.dev.led_current = 10
    s.dev.led = True
except Exception as e:
    print(f"  (driver led failed: {e}; poking registers)")
    s._poke(0x70, s._peek(0x70) | 0x08)     # CONFIG: LED_SEL
    s._poke(0x74, 0x80 | 0x04)              # LED: LED_ACT + drive
time.sleep(1.0)
tot2, c2, n2, ch2 = snap()
print(f"  ROOM LIGHT, own LED ON  : sum={tot2:8.0f}  clear={c2:7.0f} nir={n2:6.0f}")
try:
    s.dev.led = False
except Exception:
    s._poke(0x74, 0x00)

print(f"\n  own-LED contribution: {tot2 - room:+.0f}")
print(f"  per band with the LED on: " +
      " ".join(f"{b}={ch2[b]}" for b in BANDS))
print()
if tot2 - room > 1000 and room < 500:
    print("  BLIND, NOT DARK.")
    print("  Its own LED pegs it while a room-lit chamber reads nothing.")
    print("  Light is only reaching the die from ~0 mm away, which means the")
    print("  aperture is covered or the breakout is face-down against a")
    print("  surface. That is mechanical -- no wiring or register will fix it.")
    d.lines("SENSOR", "BLIND", "", "aperture", "blocked")
elif room > 500:
    print("  It sees the room. The sensor is NOT blind; the earlier zeros were")
    print("  a genuinely dark sealed chamber plus emitters aimed off the spot.")
    d.lines("SENSOR", "SEES ROOM", "", "aim the", "emitters")
else:
    print("  Nothing from the room AND nothing from its own LED.")
    print("  The ADC converts (AVALID toggles) but no photons arrive at all.")
    d.lines("SENSOR", "NO LIGHT", "", "own LED too", "")
