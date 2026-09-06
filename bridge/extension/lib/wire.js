// CELL-EVM-1, the browser half. Mirrors bridge/wire.py exactly -- if these two
// disagree the device rejects the payload, so they are kept deliberately dull.

export const VERSION = 1;
export const OP_SEND = "eth.send";
export const CHUNK = 300;

const hex = (v) => "0x" + BigInt(v).toString(16);

/** Transaction FIELDS, never a digest. The device rebuilds and rehashes. */
export function build({ chainId, nonce, to, value, gas, maxFee, maxPrio, data }) {
  const req = {
    v: VERSION, op: OP_SEND,
    chain: Number(chainId),
    nonce: Number(nonce),
    to,
    value: hex(value),
    gas: Number(gas),
    maxFee: hex(maxFee),
    maxPrio: hex(maxPrio),
  };
  // `blind` is not decoration: the device refuses calldata that is not marked,
  // so a contract call cannot arrive by a page omitting a flag.
  if (data && data !== "0x") { req.data = data; req.blind = true; }
  return req;
}

// Sorted keys and no whitespace, so the digest matches Python's json.dumps
// with sort_keys=True and the tightest separators.
function canonical(req) {
  return JSON.stringify(req, Object.keys(req).sort());
}

export function encode(req, chunk = CHUNK) {
  const body = btoa(String.fromCharCode(...new TextEncoder().encode(canonical(req))));
  const parts = [];
  for (let i = 0; i < body.length; i += chunk) parts.push(body.slice(i, i + chunk));
  if (!parts.length) parts.push("");
  return parts.map((p, i) => `p${i + 1}of${parts.length} ${p}`);
}

export async function digest(req) {
  const bytes = new TextEncoder().encode(canonical(req));
  const h = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 8);
}
