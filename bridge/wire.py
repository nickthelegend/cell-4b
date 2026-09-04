"""CELL-EVM-1 — the wire format between a browser and the device.

Upstream's qr.py frames PSBTs, which are Bitcoin. There is no EVM equivalent
in the repo, so this defines one, and deliberately reuses qr.py's framing
rather than inventing a second convention: the same `pNofM base64` a webcam
already knows how to collect.

WHAT CROSSES, and what does not. The payload carries transaction FIELDS, never
a digest. eth.py refuses to sign a hash on purpose -- "a digest is exactly the
thing the owner cannot read" -- so the device rebuilds the transaction from
these fields and hashes what it built. If the browser lied about any field,
the device renders the truth and the owner sees it.

NO CALLDATA. `data` is not in this schema at all, because EthTransaction
rejects it. A contract call cannot be rendered as a sentence, so it cannot be
authorised by a device whose whole claim is that it shows what it signs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re

VERSION = 1
OP_SEND = "eth.send"
CHUNK = 300                                  # base64 chars per frame, as qr.py
_FRAME = re.compile(r"^p(\d+)of(\d+)\s*(.*)$", re.IGNORECASE | re.DOTALL)

REQUIRED = ("chain", "nonce", "to", "value", "gas", "maxFee", "maxPrio")


class BadPayload(ValueError):
    """A payload that is not a CELL-EVM-1 request."""


def build(*, chain_id: int, nonce: int, to: str, value_wei: int,
          gas_limit: int, max_fee_wei: int, max_prio_wei: int) -> dict:
    """The canonical request object. Integers as hex strings, so a browser's
    Number cannot silently round a wei value past 2^53."""
    return {
        "v": VERSION,
        "op": OP_SEND,
        "chain": chain_id,
        "nonce": nonce,
        "to": to,
        "value": hex(value_wei),
        "gas": gas_limit,
        "maxFee": hex(max_fee_wei),
        "maxPrio": hex(max_prio_wei),
    }


def encode(req: dict, chunk: int = CHUNK) -> list[str]:
    """Request object -> pNofM frames."""
    blob = json.dumps(req, separators=(",", ":"), sort_keys=True).encode()
    body = base64.b64encode(blob).decode("ascii")
    parts = [body[i:i + chunk] for i in range(0, len(body), chunk)] or [""]
    return [f"p{i + 1}of{len(parts)} {p}" for i, p in enumerate(parts)]


def digest(req: dict) -> str:
    """The 8-hex check the two screens compare by eye."""
    blob = json.dumps(req, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:8]


def collect(frames: list[str]) -> dict:
    """Frames -> request object. Rejects anything that is not one."""
    total, chunks = None, {}
    for f in frames:
        m = _FRAME.match(f.strip())
        if not m:
            raise BadPayload(f"not a pNofM frame: {f[:24]!r}")
        i, n, body = int(m.group(1)), int(m.group(2)), m.group(3)
        if total is None:
            total = n
        elif n != total:
            raise BadPayload(f"frame claims {n} total, transfer has {total}")
        if not 1 <= i <= total:
            raise BadPayload(f"frame index {i} out of range 1..{total}")
        if i in chunks and chunks[i] != body:
            raise BadPayload(f"frame {i} arrived twice with different bytes")
        chunks[i] = body
    if total is None or len(chunks) != total:
        raise BadPayload(f"incomplete: have {len(chunks)} of {total}")
    return parse(base64.b64decode("".join(chunks[i] for i in range(1, total + 1))))


def parse(blob: bytes) -> dict:
    try:
        req = json.loads(blob)
    except Exception as e:
        raise BadPayload(f"payload is not JSON: {e}") from None
    if not isinstance(req, dict):
        raise BadPayload("payload is not an object")
    if req.get("v") != VERSION:
        raise BadPayload(f"version {req.get('v')!r}, expected {VERSION}")
    if req.get("op") != OP_SEND:
        raise BadPayload(f"operation {req.get('op')!r} is not {OP_SEND}")
    missing = [k for k in REQUIRED if k not in req]
    if missing:
        raise BadPayload(f"missing fields: {', '.join(missing)}")
    if "data" in req and req["data"] not in ("", "0x", None):
        raise BadPayload(
            "payload carries calldata. This device signs value transfers, "
            "which it can render in full; it cannot render an EVM call as "
            "something an owner could evaluate.")
    return req


def to_int(v) -> int:
    """Accept hex strings or ints, reject anything else."""
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.startswith("0x"):
        return int(v, 16)
    raise BadPayload(f"expected an integer or 0x-hex string, got {v!r}")
