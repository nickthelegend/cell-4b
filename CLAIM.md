# Claim — poidh bounty 24

**CELL-4B**, a Raspberry Pi 4B build of [z0r0z/cell](https://github.com/z0r0z/cell).
Everything below is verifiable by anyone with an RPC endpoint.

## Device

| | |
|---|---|
| address | `0xD9B4b074e48cfF75538E6468748C0FA2C16De5F5` |
| seed | generated on the device, never left it |
| network | Ethereum **mainnet** |

The key had **never signed anything** before this build: the transactions
below are nonces 0 through 3 on a fresh account.

## On chain

Four mainnet transactions, all `SUCCESS`, all from the device key.

| what | nonce | block | tx |
|---|---|---|---|
| `pulse.wei` commit | 0 | 25934252 | [`0x86b3273c…`](https://etherscan.io/tx/0x86b3273c65ad551aef0cfd211b4880e1e9ec2ec62cd23c575286083242f3efb7) |
| `pulse.wei` register | 1 | 25934352 | [`0xf6835b12…`](https://etherscan.io/tx/0xf6835b1204cba15e2aae91b4c2c26390bf0a6940d12ac4542804a01d0ba350ea) |
| `blood.wei` commit | 2 | — | — |
| `blood.wei` register | 3 | 25942667 | [`0xec1fa23b…`](https://etherscan.io/tx/0xec1fa23b839fa46d38bdd20180d2e79a32802ef148b20962eb9c5af5487e6504) |

**Two `.wei` domains registered and owned by the device key.** WNS uses
commit-reveal, so each name took two transactions and a wait between them.

## Against the four requirements

**1. The assembled device, running.** Video. Full-screen console on the Pi's
own display: both cameras, the live pulse gate, the eight-band spectrometer,
G1–G6, and the speckle plot with both thresholds drawn.

**2. A signature authorised by a pulse.** The gate reads bpm, confidence and
perfusion from a MAX3010x and refuses on any of the three. A passing read:

```
OK bpm 80.0    OK conf 0.820    OK perfusion 3.609    (want 0.05-8.0)
PULSE PRESENT -- a living finger
```

It refuses far more often than it passes — a moving finger reads perfusion
around 10 %, well outside the window, and is rejected:

```
perfusion 9.43% -- far too large for blood volume; this is the finger moving
```

**3. A transaction on chain.** Four of them, above.

**4. A signature authorised by fresh blood.** **Not claimed.** The chemistry
gates could not be run to a standard worth claiming. See below.

## The airgap

The browser extension holds **no key** — only an address, announced over
EIP-6963 as `life.proof.cell`. It builds an EIP-1559 transaction, frames it,
and shows a QR. The device rebuilds it **from the fields**, renders it on its
own screen, gates, signs, and shows the signature back as a QR.

Contract calls are blind-signed and say so. The device does not invent a
summary it cannot justify:

```
!! UNREAD CONTRACT CALL !!
  the device cannot explain this
  to       0x0000000000696760E15f265e828DB644A0c242EB
  value    0 ETH
  selector 0xf14fcbc8
  data     36 bytes
  hash     <sha256 of the calldata>
```

Flip one bit of calldata and the displayed hash changes.

## What did not work, and the numbers

`BOUNTY.md`: *"A failure is a claim too. If dye passes a gate, or real blood
fails on your optics, post it."* Both happened. `FINDINGS.md` 10–16.

**A red dye passes G2 and G3 when the white reference collapses** (16).
Measured, red dye, this device:

```
dark 5312   white patch 5140   sample 5280      <- reference darker than dark
G2 -> 1e15    PASS
G3 -> 1.0000  PASS
```

`chemistry_gates()` forms its ratios without checking the reference returned
any light. Once `white - dark <= 0`, G2 divides by ~zero and G3's index goes
to 1.0 as R415 goes to zero — a dead 415 channel is arithmetically identical
to perfect Soret absorption. G3's docstring anticipates it and does not act:
*"Gate 1 has already established that the sample returns real signal."* It
never checks whether G1 ran. **Fixed here** by refusing before the gates run.

**The white LEDs cannot excite the Soret band** (12). 415 nm reads exactly 0
at gain 128, 256 **and** 512 while 445 doubles each time. Blue-pump phosphor
emitters start around 445. G3 cannot pass for any sample on the BOM parts.
Fixed by fitting a **400 nm violet emitter**, which gives a clean 415 channel
at 6.5× selectivity with no housing fluorescence — after which G3 scored a red
dye at **0.2233** against its 0.75 bar, on a real two-position read.

**Real blood failed G5 on these optics** (14). A clotting series ran
`D 0.94 → 0.22` — endpoints that satisfy G6's `d_late ≤ 0.25` and
`drop ≥ 0.35`. G5 refuses first on speckle contrast: `K = 0.073` against a
0.10 floor, **flat across a 66× exposure sweep**. Grain size, not exposure.

**A 940 nm emitter cannot be sink-driven from +5V by a 3.3V GPIO** (10, 15).
`5.0 - 3.3 = 1.7 V` exceeds its 1.3 V forward voltage, so it has **no off
state**, and a released pin drives 5V through the pin's ESD clamp into the
3.3V rail. It cost GPIO12, and the emitter then ran lit for hours beside the
AS7341. The sensor's dark floor has been between 826 and 5300 counts since,
against a signal of ~200 — which is why the chemistry gates cannot be trusted.

## Honest status

**Working:** device assembled and running; pulse gate; airgapped bridge; blind
signing with a calldata hash; four mainnet transactions; both white emitters;
940 nm on the correct rail; 400 nm violet with a clean 415 nm channel;
two-position reads.

**Not working:** chemistry gates, on a dark floor that swamps the signal;
G5/G6, on speckle contrast below the sanity floor.

**Not claimed:** a signature authorised by fresh blood.
