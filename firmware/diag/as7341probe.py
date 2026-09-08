"""Ask the AS7341 directly what state it is in."""
import time, subprocess, shutil
import board, busio

ADDR = 0x39
i2c = busio.I2C(board.SCL, board.SDA)

def poke(reg, val):
    while not i2c.try_lock(): pass
    try: i2c.writeto(ADDR, bytes((reg, val)))
    finally: i2c.unlock()

def peek(reg, n=1):
    buf = bytearray(n)
    while not i2c.try_lock(): pass
    try: i2c.writeto_then_readfrom(ADDR, bytes((reg,)), buf)
    finally: i2c.unlock()
    return buf[0] if n == 1 else buf

det = shutil.which("i2cdetect") or "/usr/sbin/i2cdetect"
print("=== bus ===")
print(subprocess.run([det, "-y", "1"], capture_output=True, text=True).stdout)

print("=== identity ===")
idv, rev = peek(0x92), peek(0x91)
print(f"  ID  0x92 = 0x{idv:02x}   (AS7341 reports 0x24 once the low 2 bits are masked: 0x{idv & 0xFC:02x})")
print(f"  REV 0x91 = 0x{rev:02x}")
if (idv & 0xFC) != 0x24:
    print("  !! that is NOT an AS7341 answering at 0x39")

print("\n=== state as found ===")
for name, reg in [("ENABLE", 0x80), ("ATIME", 0x81), ("CFG0", 0xA9),
                  ("CFG1/gain", 0xAA), ("CFG6/smux", 0xAF),
                  ("ASTEP_L", 0xCA), ("ASTEP_H", 0xCB),
                  ("STATUS", 0x93), ("ASTATUS", 0x94), ("STATUS2", 0xA3)]:
    print(f"  {name:10} 0x{reg:02x} = 0x{peek(reg):02x}")

print("\n=== force PON|SP_EN, then watch STATUS2 for AVALID ===")
poke(0x80, 0x00); time.sleep(0.02)
poke(0x80, 0x01); time.sleep(0.02)
poke(0x80, 0x03)
for i in range(10):
    time.sleep(0.4)
    s2 = peek(0xA3)
    raw = peek(0x95, 12)
    ch = [raw[j] | (raw[j + 1] << 8) for j in range(0, 12, 2)]
    print(f"  t={i*0.4:4.1f}s STATUS2=0x{s2:02x} "
          f"AVALID={'yes' if s2 & 0x40 else 'NO '} "
          f"ASAT_A={'y' if s2 & 0x08 else 'n'} "
          f"ASAT_D={'y' if s2 & 0x10 else 'n'}  CH0-5={ch}")

print("\n  ATIME/ASTEP now:", peek(0x81), peek(0xCA) | (peek(0xCB) << 8))
print("  ENABLE now: 0x%02x" % peek(0x80))
