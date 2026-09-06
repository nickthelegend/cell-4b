"""QR image -> decoded frame -> rebuilt transaction -> signature. No camera."""
import os, sys, time, base64, json, re
sys.path.insert(0, "upstream")
import cv2

print("CELL-4B  QR -> signature, headless\n")

img = cv2.imread("/tmp/scan-me.png")
print(f"  1. QR image             {img.shape[1]}x{img.shape[0]}")

t0 = time.time()
txt, pts, _ = cv2.QRCodeDetector().detectAndDecode(img)
print(f"  2. decoded in {(time.time()-t0)*1000:.0f} ms   {len(txt)} chars")
print(f"     {txt[:54]}...")

body = re.sub(r"^p\d+of\d+\s*", "", txt.strip())
tx = json.loads(base64.b64decode(body))
print(f"  3. CELL-EVM-{tx['v']} frame, op = {tx['op']}")
for k in ("chain", "nonce", "to", "value", "gas", "maxFee", "maxPrio"):
    print(f"       {k:<8} {tx[k]}")


SEEDFILE = os.path.expanduser("~/.cell/seed")
PATH = "m/44\'/60\'/0\'/0/0"


def device_key():
    """The key the device was provisioned with, derived on demand.

    Never a constant. A hardcoded test key is fine for proving a code path and
    catastrophic the moment someone funds the address it derives to, so this
    reads the seed the device generated for itself and refuses if there is not
    one -- an explicit failure beats silently signing as somebody else.
    """
    import bip32
    if not os.path.exists(SEEDFILE):
        raise RuntimeError(
            "no seed on this device. Run provision_cell.py first -- it "
            "generates one from the kernel CSPRNG and shows you the words.")
    with open(SEEDFILE) as f:
        mn = f.read().strip()
    node = bip32.from_mnemonic(mn).derive(PATH)
    if node.seckey is None:
        raise RuntimeError("derived a watch-only node")
    return node.seckey


import eth
eth.register_chain(84532, "Base Sepolia", "ETH")
t = eth.EthTransaction(
    chain_id=tx["chain"], nonce=tx["nonce"],
    max_priority_fee_per_gas=int(tx["maxPrio"], 16),
    max_fee_per_gas=int(tx["maxFee"], 16),
    gas_limit=tx["gas"], to=tx["to"], value=int(tx["value"], 16))
# The device renders with ops.EthereumSpend and signs with eth.EthTransaction.
# They are deliberately separate: one is what the owner reads, the other is
# what the signature commits to, and eth.EthTransaction has no render() at all.
import ops
spend = ops.EthereumSpend(
    amount_wei=t.value, destination=t.to, chain_id=t.chain_id,
    chain_name=t.chain_name(), nonce=t.nonce, max_fee_wei=t.max_fee_wei())
print("\n  4. the device rebuilt it from those fields and would show:")
for l in spend.render():
    print("       | " + l)

sk = device_key()
r, s_, y = eth.sign(t, sk)
raw = t.encode_signed(r, s_, y).hex()
print("\n  5. SIGNED on the Pi")
print(f"       from  {eth.sender(t, r, s_, y)}")
print(f"       txid  {t.txid(r, s_, y)}")
print(f"       raw   0x{raw[:56]}...")
print(f"       {len(raw)//2} bytes, ready for eth_sendRawTransaction")
