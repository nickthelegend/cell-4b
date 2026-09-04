#!/usr/bin/env python3
"""A stand-in for the CELL device, so the browser half can be built and tested
while the real one is in pieces on a bench.

It is deliberately NOT a simulation of the optics. It is the part of the device
the browser can see: it accepts a CELL-EVM-1 request, renders it exactly as
ops.EthereumSpend would render it on the OLED, pretends a gate ran, and signs
with upstream's own eth.py. So the bytes it returns are real -- a node will
accept them -- and only the liveness is fake.

    --gate blood|touch|refuse    what the pretend gate decides
    --delay N                    how long the pretend gate takes

THE KEY HERE IS PUBLIC. It is the all-ones test key every Ethereum test vector
uses. Anything it signs is signed by a key printed in this file, so point it at
a testnet and never at funds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "firmware"))

import wire                                            # noqa: E402
import eth                                             # noqa: E402
import ops                                             # noqa: E402
from addresses import eth_address                      # noqa: E402
import secp256k1 as ec                                 # noqa: E402

DEMO_KEY = bytes.fromhex("00" * 31 + "01")             # scalar 1. Public. Toy.
DEMO_ADDR = eth_address(ec.pubkey_compressed(DEMO_KEY))

for cid, name, tick in ((8453, "Base", "ETH"), (84532, "Base Sepolia", "ETH"),
                        (11155111, "Sepolia", "ETH")):
    try:
        eth.register_chain(cid, name, tick)
    except Exception:
        pass                                            # already built in

GATE = "blood"
DELAY = 2.0


def render(tx: eth.EthTransaction) -> list[str]:
    """The lines the device would put on its screen, from the same code."""
    return ops.EthereumSpend(
        amount_wei=tx.value,
        destination=tx.to,
        chain_id=tx.chain_id,
        chain_name=tx.chain_name(),
        nonce=tx.nonce,
        max_fee_wei=tx.max_fee_wei(),
        ticker=eth.CHAINS[tx.chain_id][1],
    ).render()


def handle(req: dict) -> dict:
    tx = eth.EthTransaction(
        chain_id=wire.to_int(req["chain"]),
        nonce=wire.to_int(req["nonce"]),
        max_priority_fee_per_gas=wire.to_int(req["maxPrio"]),
        max_fee_per_gas=wire.to_int(req["maxFee"]),
        gas_limit=wire.to_int(req["gas"]),
        to=req["to"],
        value=wire.to_int(req["value"]),
    )
    lines = render(tx)
    print("\n  ---- the device would show ----")
    for ln in lines:
        print(f"  | {ln}")
    print(f"  ---- gate: {GATE} ----", flush=True)
    time.sleep(DELAY)
    if GATE == "refuse":
        return {"ok": False, "error": "gate refused: no sample detected",
                "display": lines}
    r, s, yp = eth.sign(tx, DEMO_KEY)
    raw = tx.encode_signed(r, s, yp)
    return {
        "ok": True,
        "display": lines,
        "tier": GATE,
        "from": DEMO_ADDR,
        "txid": tx.txid(r, s, yp),
        "raw": "0x" + raw.hex(),
        "digest": wire.digest(req),
    }


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        self._send(200, {"device": "mock-cell", "address": DEMO_ADDR,
                         "gate": GATE, "warning": "demo key, testnet only"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n))
            req = wire.collect(body["frames"]) if "frames" in body \
                else wire.parse(json.dumps(body["request"]).encode())
            self._send(200, handle(req))
        except wire.BadPayload as e:
            self._send(400, {"ok": False, "error": str(e)})
        except eth.BadEthTransaction as e:
            self._send(400, {"ok": False, "error": f"device refused: {e}"})
        except Exception as e:                          # noqa: BLE001
            self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass


def main() -> int:
    global GATE, DELAY
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8799)
    p.add_argument("--gate", choices=("blood", "touch", "refuse"), default="blood")
    p.add_argument("--delay", type=float, default=2.0)
    a = p.parse_args()
    GATE, DELAY = a.gate, a.delay
    print(f"  mock CELL on :{a.port}")
    print(f"  address {DEMO_ADDR}   gate={GATE}   delay={DELAY}s")
    print("  THE KEY IS PUBLIC -- testnet only\n")
    HTTPServer(("127.0.0.1", a.port), H).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
