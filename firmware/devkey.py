"""The device's signing key, in a module that does not open a window.

It lived in console.py, which builds a Tk root at import time -- so anything
wanting the key from a terminal got "no display name and no $DISPLAY". A key
is not a GUI concern; the pre-flight, the CLI and the console all need it and
only one of them has a screen.
"""
from __future__ import annotations

import os
import sys

SEEDFILE = os.path.expanduser("~/.cell/seed")
PATH = "m/44'/60'/0'/0/0"


def device_key() -> bytes:
    """Derive the device's key from its own seed. Never a constant.

    A hardcoded test key is fine for proving a code path and catastrophic the
    moment the address it derives to holds money, so this refuses outright
    rather than falling back to one.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__) or ".", "upstream"))
    import bip32
    if not os.path.exists(SEEDFILE):
        raise RuntimeError(
            f"no seed at {SEEDFILE}. Run provision_cell.py first -- it "
            f"generates one from the kernel CSPRNG and shows you the words.")
    with open(SEEDFILE) as f:
        mn = f.read().strip()
    node = bip32.from_mnemonic(mn).derive(PATH)
    if node.seckey is None:
        raise RuntimeError("derived a watch-only node")
    return node.seckey


def device_address() -> str:
    from addresses import eth_address
    import bip32
    with open(SEEDFILE) as f:
        mn = f.read().strip()
    return eth_address(bip32.from_mnemonic(mn).derive(PATH).pubkey)
