# Handover

Everything an agent needs to pick this up cold. Written after two days of
bring-up, and organised so the expensive lessons arrive before you can repeat
them.

**Read "Traps" before touching hardware.** Most of them cost hours or parts.

---

## Access

```bash
ssh raspberrypi@192.168.1.22          # key auth, no password prompt
cd ~/Desktop/cell-4b                  # the deployed copy
.venv/bin/python -u <script>          # always the venv, always -u
```

The repo lives on the Mac at `/Volumes/Extreme SSD/Projects/cell/cell4b` and
is pushed to `github.com/nickthelegend/cell-4b`. The Pi copy is deployed with
`scp`, not `git pull` — keep them in sync by hand and `sync` after writing,
because this board loses power often enough to lose an unflushed file.

**The Pi reboots on its own.** `vcgencmd get_throttled` has reported
under-voltage. Expect SSH to drop mid-command; retry rather than diagnose.

**Long-running GUI processes die with the SSH session.** `nohup`/`setsid` did
not survive; hold the connection open instead:

```bash
ssh -o ServerAliveInterval=30 raspberrypi@192.168.1.22 \
  'cd ~/Desktop/cell-4b && DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 \
   WAYLAND_DISPLAY=wayland-0 exec .venv/bin/python -u gate_console.py'
```

Screenshots: `XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 grim
/tmp/x.png`. The display is **1520x651** — the console is laid out for it.

---

## Hardware state

| | GPIO | header | state |
|---|---|---|---|
| white #1 | 13 | 33 | working |
| **violet 400 nm** | 16 | 36 | working — **replaced white #2**, see below |
| 940 nm IR | 23 | 16 | working, **on +3V3** |
| laser 650 nm | 6 | 31 | working |
| cartridge switch | 22 | 15 | **never reads seated** — untrusted |
| ~~GPIO12~~ | 12 | 32 | **DEAD.** Killed by the 5V clamp, see trap 1 |

**AS7341 (0x39): damaged.** Dark floor wanders between 826 and 5300 counts at
gain 256 / 916 ms, against a signal of ~200. It fails both tests that would
excuse it: a cold start shows the floor already high, and ice directly on the
die moved it 5% for a 4 C fall where dark current halves every ~8 C.
**Chemistry gates cannot be trusted until this part is replaced.** FINDINGS 15.

**MAX3010x (0x57) and the OLED (0x3c) are fine.** The pulse gate works and has
authorised a real mainnet signature.

---

## Traps

### 1. A low-Vf emitter cannot be sink-driven from +5V

Sink drive puts the GPIO on the cathode, so "off" means driving the pin to the
anode's rail. A 3.3V pin cannot reach 5V, leaving `5.0 - 3.3 = 1.7 V` across
the LED. White LEDs (Vf ~3.0) do not care. **A 940 nm LED (Vf ~1.3) has no off
state**, and a released pin drives 5V through the ESD clamp into the 3.3V rail.

This killed GPIO12, and then it cooked the AS7341 sitting beside it.
**940 nm belongs on +3V3.** `hw.py`'s header said so all along.

### 2. EMITTER_OHMS is the calibration, not a comment

`atime_for()` scales integration time from it to hold collected light constant.
It says **220**; `hw.py` used to say 120. Every script that hardcoded
`atime=99` under-integrated by 1.8x and it presented as a dim instrument.
Derive it: `atime_for(EMITTER_OHMS)`.

### 3. `bench.white_2` is `None` when the violet is fitted

`WHITE2_IS_VIOLET = True` gives the violet white #2's bore and its pin — the
head has three LED bores and all were taken. Code that calls `white_2.on()`
directly raises. Use `with bench.white():`.

### 4. The gates PASS on a collapsed reference

`chemistry_gates()` divides by the white patch without checking it returned
any light. Once `white - dark <= 0`: G2 returns 1e15 and G3 returns 1.0,
**and both pass**. A red dye cleared them this way. FINDINGS 16.
`sign_with_blood` now refuses before the gates run; keep that guard.

### 5. A released sink pin lights its own LED

`gpiozero` releases pins to inputs on close, and an input floats. The emitter
then lights with nothing running. **Hold a `Bench` open for any dark
measurement** — `all_off()` drives the pins and holds them.

### 6. The Pi camera cannot see 940 nm

OV5647 has an IR-cut filter. A phone camera can (front camera is better than
rear). Do not conclude an IR emitter is dead from the Pi camera.

### 7. The Pi camera is LENSLESS

`spec.py` removes the lens deliberately for speckle. It cannot form an image —
frames are intensity maps. Do not expect a photograph of the chamber.

### 8. The white LEDs emit nothing at 415 nm

Blue-pump phosphor. 415 read a hard 0 at gain 128, 256 AND 512 while 445
doubled each time. **G3 is impossible without the violet emitter.** FINDINGS 12.

### 9. Other small ones

- `i2cdetect` is in `/usr/sbin`, off a normal user's PATH.
- `luma` blanks the OLED in `atexit` — pass `persist=True`.
- The USB QR camera **changes its node** on replug. Find it by driver:
  `/sys/class/video4linux/*/device/driver` == `uvcvideo`.
- The Adafruit AS7341 driver times out above `atime=182`.
- A **stale camera frame is worse than none** — it reads as working. The QR
  thread now reopens on stall and serves `None`.

---

## Signing

**Address `0xD9B4b074e48cfF75538E6468748C0FA2C16De5F5`.** Seed at `~/.cell/seed`
on the SD card — a hot wallet, accepted deliberately for bench work.

**On chain already:** `pulse.wei` registered on Ethereum mainnet, nonces 0 and
1, commit in block 25934252. Both authorised by the pulse gate.

### The airgap

The browser extension (`bridge/extension`, EIP-6963 as `life.proof.cell`) holds
**no key** — only the address. It builds an EIP-1559 transaction, frames it as
`pNofM <base64>`, and shows a QR. The device rebuilds it **from the fields**,
displays it, gates, signs, and shows the signature back as a QR.

Configure it in the extension popup: address, chain, gate, and **blind signing
on** for contract calls.

```
X   scan a QR from the USB camera, gate on PULSE, sign
B   run G1-G6 and sign only if all six pass
```

`/tmp/cell-frame.txt` is a frame handed over directly, for when the camera
cannot read the screen. Same payload, same rebuild, same gate — only the
transport differs. The signature is written to `/tmp/cell-signed.txt`.

### Two things that will bite

**Signature fields start at index 9** of the RLP, not 8 — index 8 is
`accessList`. Off by one recovers a valid signature for the *wrong address*.

**Signing is RFC 6979 deterministic**, so re-signing the identical transaction
reproduces the identical bytes. That is how a signature was recovered after the
console failed to display its QR — it is the same signature, not a new one.

---

## Where it stands

**Working:** device assembled and running; pulse gate; airgapped bridge; blind
signing with a calldata hash; both whites; the 940 nm on the right rail; the
400 nm violet with a clean 415 channel (6.5x selectivity, no housing
fluorescence); two-position reads when the sensor holds still.

**Blocked:**

- **Chemistry gates** — the AS7341's floor. Replace the part.
- **G5/G6** — speckle contrast `K = 0.073` against a 0.10 floor, flat across a
  66x exposure sweep. Grain size, not exposure. FINDINGS 14.
- **G3** — needs the violet, which is now fitted. Measured a red dye at
  **0.2233** against its 0.75 bar with a real two-position read.

**The bounty** (`../BOUNTY.md`, poidh 24) wants four things and three are done:
device running, a pulse-authorised signature, and a transaction on chain.
Blood is not. It also says **"a failure is a claim too"** — and FINDINGS 13,
14, 15 and 16 are exactly that, measured on this hardware.

## Rules that held

- **Never fake a gate result.** A green screen that did not happen is worth
  less than a documented refusal, and the whole claim of the instrument is
  that its numbers are honest.
- **A gate that passes on garbage is worse than one that fails.** Prefer
  refusing to measure over reporting a number nobody can defend.
- **Say which reading is untrustworthy and why.** Most of the wasted time here
  came from treating a broken measurement as data.
