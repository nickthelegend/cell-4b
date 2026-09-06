"""Generate the device's own key. Once, on the device, from the OS CSPRNG.

The words are printed on the PI'S OWN SCREEN and nowhere else. They are not
returned over SSH and they do not enter a chat transcript, because a seed that
has travelled through someone else's logs is not a seed any more. Only the
ADDRESS comes back.

WHAT THIS IS NOT. There is no ATECC608B here, so the seed sits in a file on an
SD card. Anyone who takes the card takes the money. The real design wraps it
with a key that never leaves a secure element and gates it behind a PIN whose
counter cannot be rolled back; none of that exists yet. Treat this as a hot
wallet on a computer that has been on the internet.
"""
import os, secrets, stat, sys, subprocess

sys.path.insert(0, "upstream")
import bip39, bip32
from addresses import eth_address
import secp256k1 as ec

HOME = os.path.expanduser("~/.cell")
SEEDFILE = os.path.join(HOME, "seed")
PATH = "m/44'/60'/0'/0/0"          # the standard Ethereum account

if os.path.exists(SEEDFILE):
    print("  A seed already exists at ~/.cell/seed -- refusing to overwrite it.")
    print("  Deleting it destroys any funds held by that address.")
    mn = open(SEEDFILE).read().strip()
else:
    # 256 bits from the kernel CSPRNG -> 24 words.
    entropy = secrets.token_bytes(32)
    mn = bip39.entropy_to_mnemonic(entropy)
    assert bip39.validate(mn), "generated an invalid mnemonic"
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    fd = os.open(SEEDFILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(mn + "\n")
    print("  new seed written to ~/.cell/seed  (mode 0600)")

root = bip32.from_mnemonic(mn)
# ExtendedKey exposes .derive(path) and holds the private half in .seckey --
# .privkey/.key are other libraries' names for it.
node = root.derive(PATH)
sk = node.seckey
if sk is None:
    raise SystemExit("derived a watch-only node -- no private key")
addr = eth_address(node.pubkey)

# The words go to the Pi's own display, not to stdout.
words = mn.split()
rows = [f"{i+1:>2}. {w:<10}" for i, w in enumerate(words)]
grid = "\n".join("".join(rows[i::(len(rows)//4 or 1)][:1] for _ in [0]) for i in range(0))
body = "\n".join("   ".join(rows[r*4:(r+1)*4]) for r in range((len(rows) + 3) // 4))
msg = (f"CELL-4B  SEED  --  WRITE THESE DOWN\n\n{body}\n\n"
       f"path    {PATH}\naddress {addr}\n\n"
       f"These 24 words ARE the money. Anyone who reads them can spend it.\n"
       f"There is no secure element on this build: the seed is a file on the\n"
       f"SD card, so treat this as a hot wallet.")
try:
    with open("/tmp/cell-seed.txt", "w") as f:
        f.write(msg + "\n")
    os.chmod("/tmp/cell-seed.txt", 0o600)
    subprocess.Popen(["lxterminal", "--title=CELL SEED",
                      "-e", "bash", "-c", f"cat /tmp/cell-seed.txt; read -p ''"],
                     env={**os.environ, "DISPLAY": ":0"})
    print("  words opened in a terminal ON THE PI'S SCREEN, and in /tmp/cell-seed.txt")
except Exception as e:
    print(f"  could not open a window ({type(e).__name__}); words are in /tmp/cell-seed.txt")

print()
print(f"  path    {PATH}")
print(f"  ADDRESS {addr}")
