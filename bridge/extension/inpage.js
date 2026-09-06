// The shim. Runs in the PAGE's world so the dApp sees it as window.ethereum.
//
// It intercepts eth_sendTransaction, and only that. Everything else -- account
// lists, chain switches, reads -- goes straight through to the wallet already
// installed, because CELL is a signer, not a wallet: it has no accounts to
// enumerate and no opinion about the chain.
//
// WHAT IT SENDS THE DEVICE: transaction fields. Never a digest. eth.py rebuilds
// the transaction from these and hashes what IT built, so a page that lies
// about the recipient gets rendered truthfully on the device's own screen and
// the owner sees the difference. That property is the whole point, and it only
// survives if this file never takes a shortcut and hashes anything itself.

import { encodeQR } from "./lib/qr.js";
import * as wire from "./lib/wire.js";
import { toChecksumAddress } from "./lib/keccak.js";

// document.currentScript is null inside a module -- the dataset the content
// script attached is unreachable from here. import.meta.url is the module-safe
// way to find our own directory, and it works whatever URL the extension was
// loaded from.
{
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = new URL("./overlay.css", import.meta.url).href;
  (document.head || document.documentElement).append(l);
}

// ---------------------------------------------------------------- bridge ----
let seq = 0;
function toBackground(payload) {
  return new Promise((resolve) => {
    const id = `cb${++seq}`;
    const onReply = (ev) => {
      if (ev.source !== window || ev.data?.channel !== "cell-bridge-reply" || ev.data.id !== id) return;
      window.removeEventListener("message", onReply);
      resolve(ev.data.reply);
    };
    window.addEventListener("message", onReply);
    window.postMessage({ channel: "cell-bridge", id, payload }, "*");
  });
}

// ---------------------------------------------------------------- overlay ---
function overlay(req, frames, digest, lines) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "cellbr-root";
    const wei = BigInt(req.value), eth = Number(wei) / 1e18;
    root.innerHTML = `
      <div class="cellbr-card">
        <div class="cellbr-hd"><b>Sign with CELL</b><span class="cellbr-tag">proof of life</span></div>
        <div class="cellbr-sub">check ${digest} &middot; chain ${req.chain} &middot; nonce ${req.nonce}</div>
        <svg class="cellbr-qr" viewBox="0 0 1 1"></svg>
        <div class="cellbr-frame"></div>
        <div class="cellbr-lines">${lines.join("\n")}</div>
        <div class="cellbr-row">
          <button class="cellbr-btn primary" data-act="mock">Sign on mock CELL</button>
          <button class="cellbr-btn" data-act="cancel">Cancel</button>
        </div>
        <div class="cellbr-row">
          <input class="cellbr-in" data-act="raw" placeholder="or paste the signed transaction hex from the device">
        </div>
        <div class="cellbr-err" hidden></div>
        <div class="cellbr-note">The device rebuilds this transaction from the fields
          above and hashes what it built. If this page asked for something else, the
          device's own screen shows the difference.</div>
      </div>`;
    const svg = root.querySelector(".cellbr-qr");
    const frameEl = root.querySelector(".cellbr-frame");
    const errEl = root.querySelector(".cellbr-err");
    const say = (m, ok) => { errEl.hidden = false; errEl.textContent = m; errEl.classList.toggle("cellbr-ok", !!ok); };

    let i = 0;
    const paint = () => {
      const m = encodeQR(frames[i % frames.length]);
      const n = m.length, q = 4, size = n + q * 2;
      let d = "";
      for (let r = 0; r < n; r++) for (let c = 0; c < n; c++)
        if (m[r][c]) d += `M${c + q} ${r + q}h1v1h-1z`;
      svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
      svg.innerHTML = `<rect width="${size}" height="${size}" fill="#fff"/><path d="${d}" fill="#000"/>`;
      frameEl.textContent = frames.length > 1
        ? `frame ${(i % frames.length) + 1} of ${frames.length} — hold the device steady`
        : `one frame — ${eth} ETH`;
      i++;
    };
    paint();
    const timer = frames.length > 1 ? setInterval(paint, 500) : null;

    const done = (v) => { if (timer) clearInterval(timer); root.remove(); resolve(v); };
    root.addEventListener("click", async (ev) => {
      const act = ev.target?.dataset?.act;
      if (act === "cancel") done({ cancelled: true });
      if (act === "mock") {
        ev.target.disabled = true;
        say("waiting for the gate…");
        const r = await toBackground({ type: "cell:sign", request: req });
        ev.target.disabled = false;
        if (!r?.ok) return say(r?.error || "device unreachable — is mock_cell.py running?");
        if (!r.result?.ok) return say(r.result?.error || "the gate refused");
        // Replace the preview with what the device actually put on its screen.
        // The browser has no chain registry and renders "CHAIN 84532" where the
        // device says "BASE SEPOLIA"; if the two ever disagree about anything
        // that matters, the device's version is the one worth showing.
        if (Array.isArray(r.result.display)) {
          root.querySelector(".cellbr-lines").textContent = r.result.display.join("\n");
        }
        say(`signed at ${r.result.tier} tier`, true);
        setTimeout(() => done({ raw: r.result.raw }), 900);
      }
    });
    root.querySelector('[data-act="raw"]').addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      const v = ev.target.value.trim();
      if (/^0x[0-9a-fA-F]+$/.test(v)) done({ raw: v });
      else say("that is not a hex transaction");
    });
    document.documentElement.append(root);
  });
}

// --------------------------------------------------------------- provider ---
// CELL is announced as its own wallet rather than wrapping someone else's.
// That is the whole point of an airgapped signer: there is no hot wallet in
// this browser to wrap, and nothing here can spend. What this file holds is an
// ADDRESS -- the one the device derived -- exactly as a watch-only wallet does.
//
//   reads and broadcast   -> a public node, via the service worker
//   eth_accounts          -> the configured address
//   eth_sendTransaction   -> QR out, signature back, then broadcast

const hexToBig = (v) => (v == null ? 0n : BigInt(v));

let CONFIG = { address: "", chainId: "0x1" };
toBackground({ type: "cell:config" }).then((r) => {
  if (r?.ok) CONFIG = { ...CONFIG, ...r.config };
});

async function rpc(method, params) {
  const r = await toBackground({ type: "cell:rpc", method, params });
  if (!r?.ok) throw Object.assign(new Error(r?.error || "rpc failed"), { code: r?.code ?? -32603 });
  return r.result;
}

function needAddress() {
  if (!CONFIG.address) {
    throw Object.assign(new Error(
      "No CELL address configured. Open the extension and paste the address " +
      "your device holds -- the browser never sees a key, only which account " +
      "to build transactions for."), { code: 4100 });
  }
  return CONFIG.address;
}

async function sendTransaction(tx = {}) {
  if (tx.data && tx.data !== "0x") {
    throw Object.assign(new Error(
      "CELL refuses transactions carrying calldata. It signs value transfers, " +
      "which it can render in full; it cannot render a contract call as " +
      "something you could evaluate. Registering a name is a contract call."),
      { code: 4100 });
  }
  const from = tx.from || needAddress();
  const [nonceHex, prioHex, block] = await Promise.all([
    rpc("eth_getTransactionCount", [from, "pending"]),
    rpc("eth_maxPriorityFeePerGas", []).catch(() => "0x5f5e100"),
    rpc("eth_getBlockByNumber", ["latest", false]),
  ]);
  const base = hexToBig(block?.baseFeePerGas ?? "0x0");
  const prio = hexToBig(tx.maxPriorityFeePerGas ?? prioHex);
  const maxFee = hexToBig(tx.maxFeePerGas ?? (base * 2n + prio));
  const gas = hexToBig(tx.gas ?? "0x5208");

  const req = wire.build({
    chainId: parseInt(CONFIG.chainId, 16),
    nonce: parseInt(nonceHex, 16),
    to: toChecksumAddress(tx.to),
    value: hexToBig(tx.value ?? "0x0"),
    gas, maxFee, maxPrio: prio,
  });
  const digest = await wire.digest(req);
  const frames = wire.encode(req);
  const eth = Number(BigInt(req.value)) / 1e18;
  const lines = [
    `SEND ON CHAIN ${req.chain}`,
    `  amount   ${eth} ETH`,
    `  to`,
    `           ${req.to.slice(0, 26)}`,
    `           ${req.to.slice(26)}`,
    `  max fee  ${Number(BigInt(req.maxFee) * BigInt(req.gas)) / 1e18} ETH`,
    `  nonce    ${req.nonce}`,
  ];
  const out = await overlay(req, frames, digest, lines);
  if (out.cancelled) throw Object.assign(new Error("CELL: cancelled"), { code: 4001 });
  return rpc("eth_sendRawTransaction", [out.raw]);
}

const listeners = new Map();
const provider = {
  isCELL: true,
  async request(args = {}) {
    const { method, params = [] } = args;
    switch (method) {
      case "eth_requestAccounts":
      case "eth_accounts":
        return [needAddress()];
      case "eth_chainId":
        return CONFIG.chainId;
      case "net_version":
        return String(parseInt(CONFIG.chainId, 16));
      case "eth_sendTransaction":
        return sendTransaction(params[0]);
      case "wallet_switchEthereumChain":
        // Honest refusal. The chain is configured against the address the
        // device holds; silently accepting and then signing for a different
        // one is the failure this whole design exists to prevent.
        throw Object.assign(new Error(
          "CELL signs for the chain it was configured with. Change it in the " +
          "extension, not from the page."), { code: 4902 });
      case "personal_sign":
      case "eth_sign":
      case "eth_signTypedData_v4":
        throw Object.assign(new Error(
          "CELL signs transactions it can render, not arbitrary messages."),
          { code: 4200 });
      default:
        return rpc(method, params);
    }
  },
  on(ev, fn) { listeners.set(fn, ev); return provider; },
  removeListener(fn) { listeners.delete(fn); return provider; },
  // Some dApps still call these directly.
  async enable() { return provider.request({ method: "eth_requestAccounts" }); },
  send(a, b) {
    if (typeof a === "string") return provider.request({ method: a, params: b });
    return provider.request(a);
  },
  sendAsync(payload, cb) {
    provider.request(payload).then(
      (result) => cb(null, { id: payload.id, jsonrpc: "2.0", result }),
      (error) => cb(error));
  },
};

// EIP-6963: the modern way to be discovered without fighting over
// window.ethereum. A dApp that supports it lists CELL alongside any other
// wallet the user has, instead of one clobbering the other.
const ICON = "data:image/svg+xml;base64," + btoa(
  `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96">` +
  `<rect width="96" height="96" rx="20" fill="#0f1318"/>` +
  `<circle cx="48" cy="48" r="20" fill="none" stroke="#c8442e" stroke-width="6"/>` +
  `<circle cx="48" cy="48" r="7" fill="#c8442e"/></svg>`);

const info = Object.freeze({
  uuid: (crypto.randomUUID && crypto.randomUUID()) || "cell-" + Date.now(),
  name: "CELL",
  icon: ICON,
  rdns: "life.proof.cell",
});
const announce = () => window.dispatchEvent(new CustomEvent(
  "eip6963:announceProvider", { detail: Object.freeze({ info, provider }) }));
window.addEventListener("eip6963:requestProvider", announce);
announce();

// And the legacy slot, but only if it is free. Sites like wei.domains read
// window.ethereum directly; stamping over a real wallet that a user might
// still want is not ours to do.
if (!window.ethereum) {
  try {
    Object.defineProperty(window, "ethereum", {
      configurable: true, get: () => provider, set: () => {},
    });
  } catch { window.ethereum = provider; }
  console.info("[CELL] provider installed as window.ethereum");
} else {
  console.info("[CELL] announced via EIP-6963; window.ethereum left to the existing wallet");
}
