"""Blind signing — a contract call the device CANNOT read, and says so.

eth.py refuses calldata, and that refusal is right: a contract call is not a
sentence, and a device whose claim is "it renders what it signs" must not
render a fiction. This file does not overturn that. It takes the other honest
option, the one every hardware wallet ends up at:

    refuse to PRETEND, rather than refuse to SIGN.

So nothing here claims to explain the call. It shows the four things that are
true regardless of what the calldata does -- who is being paid, how much, on
which chain, and at what worst-case cost -- plus the selector and a hash of
the payload, under a banner that says the rest is unread. Ledger calls this
blind signing and warns on every one; so does this.

WHAT IS STILL GUARANTEED, and it is not nothing:

  * The recipient is displayed. Calldata cannot change where value goes.
  * The value is displayed, and gas_limit x max_fee bounds the total loss.
  * The chain id is committed to, so the signature cannot replay elsewhere.
  * The calldata is HASHED into the display. A page that shows one call and
    sends another produces a different hash, and the two can be compared.

WHAT IS NOT: what the call does. approve(spender, 2^256-1) and
transfer(friend, 1) are both "a contract call" here. If you cannot say why you
trust the page, do not sign it.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

sys.path.insert(0, "upstream")

from eth import CHAINS, TX_TYPE_1559, BadEthTransaction, rlp_encode
from hashes import keccak256
from addresses import valid_checksum_address
import ops
import secp256k1 as ec


@dataclass(frozen=True)
class BlindContractCall:
    """An EIP-1559 transaction that carries calldata. Deliberately a separate
    type from EthTransaction: the two are not interchangeable, and code that
    means to sign a readable transfer should not silently accept one of these.
    """

    chain_id: int
    nonce: int
    max_priority_fee_per_gas: int
    max_fee_per_gas: int
    gas_limit: int
    to: str
    value: int
    data: bytes

    def __post_init__(self):
        if not self.data:
            raise BadEthTransaction(
                "no calldata -- use eth.EthTransaction, which can render it")
        if self.chain_id not in CHAINS:
            raise BadEthTransaction(
                f"chain id {self.chain_id} is not one this device recognises")
        for n in ("nonce", "max_priority_fee_per_gas", "max_fee_per_gas",
                  "gas_limit", "value"):
            v = getattr(self, n)
            if not isinstance(v, int) or v < 0:
                raise BadEthTransaction(f"{n} must be a non-negative integer")
        if self.max_priority_fee_per_gas > self.max_fee_per_gas:
            raise BadEthTransaction("priority fee exceeds the max fee per gas")
        if not valid_checksum_address(self.to):
            raise BadEthTransaction(
                f"recipient {self.to!r} is not a valid address, or its EIP-55 "
                f"checksum does not match its capitalisation")

    # ---- encoding: byte for byte what eth.py does, with data populated ----

    def to_bytes(self) -> bytes:
        return int(self.to.removeprefix("0x"), 16).to_bytes(20, "big")

    def _fields(self) -> list:
        return [self.chain_id, self.nonce, self.max_priority_fee_per_gas,
                self.max_fee_per_gas, self.gas_limit, self.to_bytes(),
                self.value, self.data, []]

    def signing_payload(self) -> bytes:
        return bytes([TX_TYPE_1559]) + rlp_encode(self._fields())

    def sighash(self) -> bytes:
        return keccak256(self.signing_payload())

    def encode_signed(self, r: int, s: int, y_parity: int) -> bytes:
        if y_parity not in (0, 1):
            raise BadEthTransaction("y_parity must be 0 or 1")
        return bytes([TX_TYPE_1559]) + rlp_encode(self._fields() + [y_parity, r, s])

    def txid(self, r: int, s: int, y_parity: int) -> str:
        return "0x" + keccak256(self.encode_signed(r, s, y_parity)).hex()

    def max_fee_wei(self) -> int:
        return self.max_fee_per_gas * self.gas_limit

    def chain_name(self) -> str:
        return CHAINS[self.chain_id][0]

    def ticker(self) -> str:
        return CHAINS[self.chain_id][1]

    # ---- display ----

    def selector(self) -> str:
        return "0x" + self.data[:4].hex() if len(self.data) >= 4 else "(none)"

    def data_hash(self) -> str:
        return "0x" + keccak256(self.data).hex()[:16]

    def render(self) -> list[str]:
        """Everything true about this transaction, and a banner over the rest."""
        t = self.ticker()
        return [
            "!! UNREAD CONTRACT CALL !!",
            "  this device cannot",
            "  explain what this does",
            "",
            f"  to       {self.to[:26]}",
            f"           {self.to[26:]}",
            f"  value    {ops.format_eth(self.value, t)}",
            f"  max fee  {ops.format_eth(self.max_fee_wei(), t)}",
            f"  MOST     {ops.format_eth(self.value + self.max_fee_wei(), t)}",
            f"  chain    {self.chain_name()} ({self.chain_id})",
            f"  nonce    {self.nonce}",
            "",
            f"  selector {self.selector()}",
            f"  data     {len(self.data)} bytes",
            f"  hash     {self.data_hash()}",
        ]


def sign(tx: BlindContractCall, seckey: bytes) -> tuple[int, int, int]:
    """Same verify-before-return contract as eth.sign: a wrong parity byte
    yields a valid-looking transaction credited to an address nobody holds."""
    digest = tx.sighash()
    r, s, rec = ec.ecdsa_sign(digest, seckey, grind_low_r=False)
    y = rec & 1
    if ec.ecdsa_recover(digest, r, s, y) != ec.pubkey_compressed(seckey):
        raise BadEthTransaction("signature does not recover to the signing key")
    return r, s, y
