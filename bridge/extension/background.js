// The service worker. Two jobs, and neither involves a key.
//
// RPC. The provider in the page answers eth_accounts and eth_chainId from
// config, and sends everything else here to be forwarded to a public node.
// That is what makes the extension walletless: it can read the chain and
// broadcast to it without holding anything that can spend.
//
// DEVICE. A page on https://wei.domains cannot fetch http://127.0.0.1 -- mixed
// content is blocked before the request leaves the tab. A service worker is
// not subject to that. With the real CELL this path is only used by the mock;
// a physical device is reached with pixels and there is nothing to fetch.

const DEFAULTS = {
  deviceUrl: "http://127.0.0.1:8799",
  // wei.domains is Ethereum mainnet. Its own scripts use these two nodes.
  rpcUrl: "https://ethereum-rpc.publicnode.com",
  chainId: "0x1",
  // No key here, and none anywhere in the browser. This is the address the
  // DEVICE holds, typed in once, the way a watch-only wallet is set up.
  address: "",
  // Off unless the owner turns it on, per session of their own choosing. A
  // device that blind-signs by default is a device that does not render.
  blind: false,
  // Which gate the OPERATOR intends to clear: "pulse" or "blood". This is
  // declared, not commanded. The browser cannot tell the device to accept a
  // weaker proof -- the device enforces whichever gate is actually invoked on
  // it. Carrying it here only lets the overlay say what is about to be asked
  // of you, so a page cannot quietly expect blood while you offer a finger.
  gate: "pulse",
};

async function cfg() {
  const got = await chrome.storage.local.get(Object.keys(DEFAULTS));
  // `false` is a meaningful stored value for blind; filtering falsy would make
  // it impossible to ever turn back off.
  return { ...DEFAULTS, ...Object.fromEntries(
    Object.entries(got).filter(([k, v]) =>
      v !== undefined && (k === "blind" || v !== ""))) };
}

async function device(path, body) {
  const { deviceUrl } = await cfg();
  const res = await fetch(deviceUrl + path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); }
  catch { throw new Error(`device returned non-JSON (${res.status}): ${text.slice(0, 120)}`); }
  if (!res.ok && json.error) throw new Error(json.error);
  return json;
}

let rpcId = 0;
async function rpc(method, params) {
  const { rpcUrl } = await cfg();
  const res = await fetch(rpcUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: ++rpcId, method, params: params || [] }),
  });
  const json = await res.json();
  if (json.error) {
    // Surface the node's own code: a dApp distinguishes "insufficient funds"
    // from "nonce too low" by it, and flattening both to a string breaks that.
    const e = new Error(json.error.message || "rpc error");
    e.code = json.error.code;
    throw e;
  }
  return json.result;
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    try {
      switch (msg.type) {
        case "cell:probe":  return reply({ ok: true, info: await device("/") });
        case "cell:sign":   return reply({ ok: true, result: await device("/", { request: msg.request }) });
        case "cell:rpc":    return reply({ ok: true, result: await rpc(msg.method, msg.params) });
        case "cell:config": return reply({ ok: true, config: await cfg() });
        default:            return reply({ ok: false, error: `unknown message ${msg.type}` });
      }
    } catch (e) {
      reply({ ok: false, error: String(e.message || e), code: e.code });
    }
  })();
  return true;                      // keep the channel open for the async reply
});
