# CELL bridge

A browser extension that routes a dApp's **value transfers** to a CELL device,
so a transaction any website builds can be authorised with blood.

    dApp ──eth_sendTransaction──► shim ──fields as QR──► CELL ──raw tx──► chain

## What it does and does not do

It intercepts `eth_sendTransaction` and nothing else. Account lists, chain
switches and reads pass straight through to whatever wallet is installed,
because CELL is a **signer, not a wallet** — it has no accounts to enumerate.

**It refuses calldata**, and that is not a limitation to work around. From
`firmware/eth.py`:

> NO CALLDATA. `data` must be empty. Arbitrary EVM calldata cannot be rendered
> as a sentence the owner can evaluate.

So a swap, an approve or a mint is passed back to your normal wallet with an
explanation. A plain transfer goes to the device. On **wei.domains**, "send
eth" is a plain transfer, which is why it works there.

**It sends fields, never a digest.** The device rebuilds the transaction from
those fields and hashes what *it* built. A page that lies about the recipient
gets rendered truthfully on the device's own screen. That property is the whole
point of the device, and it only survives if this extension never takes the
shortcut of hashing anything itself.

## Try it without hardware

    .venv/bin/python cell4b/bridge/mock_cell.py

The mock is not a simulation of the optics. It is the part of the device the
browser can see: it renders the transaction with `ops.EthereumSpend` — the same
code the OLED uses — pretends a gate ran, and signs with upstream's real
`eth.py`. **The bytes it returns are valid; only the liveness is fake.** Its key
is the all-ones test scalar, printed in the file. Testnet only.

    --gate blood|touch|refuse     what the pretend gate decides
    --delay N                     how long it pretends to take

Load `cell4b/bridge/extension/` at `chrome://extensions` → Developer mode →
Load unpacked. Then open a dApp and send.

## Wire format

`CELL-EVM-1`. Upstream's `qr.py` frames PSBTs, which are Bitcoin; there is no
EVM equivalent in the repo, so `wire.py` defines one and reuses the same
`pNofM base64` framing a webcam already knows how to collect.

`wire.py` and `extension/lib/wire.js` must agree byte for byte — the digest the
two screens compare is a SHA-256 over canonical JSON, so a stray space in
either makes every transfer look tampered with. `e2e.test.html` asserts they
match.

## Tests

| file | asserts |
|---|---|
| `qr.test.html` | every frame size round-trips through the browser's own `BarcodeDetector` |
| `harness.test.html` | the harness itself, against a segno-generated matrix |
| `e2e.test.html` | fields → QR → device → signed tx, digests agree, calldata refused |

Serve the directory and open them; they need a real browser for
`BarcodeDetector`.

## Vendored

`lib/qr.js` and `lib/keccak.js` are written out rather than imported: an MV3
extension cannot pull script from a CDN. Both are tested against known vectors
— keccak against the three standard digests and the EIP-55 examples, QR against
`BarcodeDetector`.
