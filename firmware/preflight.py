"""Build the exact transaction the bench will build, sign it on the device,
and check everything a node will check -- without broadcasting."""
import sys, json, base64, re, urllib.request
sys.path.insert(0, "upstream")

RPC = "https://ethereum-sepolia-rpc.publicnode.com"
ADDR = "0xD9B4b074e48cfF75538E6468748C0FA2C16De5F5"
TO = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
VALUE = 10**15                                    # 0.001 ETH


def rpc(method, params):
    r = urllib.request.Request(RPC, method="POST",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                         "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.0"})
    return json.loads(urllib.request.urlopen(r, timeout=25).read())["result"]


print("CELL-4B  Sepolia pre-flight\n")
nonce = int(rpc("eth_getTransactionCount", [ADDR, "pending"]), 16)
bal = int(rpc("eth_getBalance", [ADDR, "latest"]), 16)
blk = rpc("eth_getBlockByNumber", ["latest", False])
base = int(blk["baseFeePerGas"], 16)
prio = int(rpc("eth_maxPriorityFeePerGas", []), 16)
maxfee = base * 2 + prio
gas = 21000
print(f"  chain      Sepolia 11155111")
print(f"  nonce      {nonce}")
print(f"  balance    {bal/1e18:.6f} ETH")
print(f"  base fee   {base/1e9:.4f} gwei      priority {prio/1e9:.4f} gwei")
print(f"  max fee    {maxfee/1e9:.4f} gwei    gas {gas}")
worst = VALUE + maxfee * gas
print(f"  worst case {worst/1e18:.9f} ETH  ({'covered' if bal >= worst else 'INSUFFICIENT'})")

import eth, ops
# Sepolia is a BUILTIN chain -- eth.py refuses to relabel one, on purpose:
# two names for one chain id is how an owner reads the wrong network.
tx = eth.EthTransaction(chain_id=11155111, nonce=nonce,
                        max_priority_fee_per_gas=prio, max_fee_per_gas=maxfee,
                        gas_limit=gas, to=TO, value=VALUE)
spend = ops.EthereumSpend(amount_wei=tx.value, destination=tx.to,
                          chain_id=tx.chain_id, chain_name=tx.chain_name(),
                          nonce=tx.nonce, max_fee_wei=tx.max_fee_wei())
print("\n  the device will show:")
for l in spend.render():
    print("     | " + l)

from devkey import device_key
r, s_, y = eth.sign(tx, device_key())
raw = tx.encode_signed(r, s_, y).hex()
recovered = eth.sender(tx, r, s_, y)
print(f"\n  signed on the device")
print(f"     txid      {tx.txid(r, s_, y)}")
print(f"     recovers  {recovered}")
print(f"     matches   {'YES' if recovered.lower() == ADDR.lower() else 'NO -- WRONG KEY'}")
print(f"     raw       {len(raw)//2} bytes")

# The node's own opinion, without broadcasting: estimateGas on the same call.
est = int(rpc("eth_estimateGas", [{"from": ADDR, "to": TO, "value": hex(VALUE)}]), 16)
print(f"\n  node agrees gas is {est} (we send {gas})")
print(f"\n  PRE-FLIGHT {'PASS -- press Send on the bench' if recovered.lower()==ADDR.lower() and bal>=worst and est<=gas else 'FAILED'}")
