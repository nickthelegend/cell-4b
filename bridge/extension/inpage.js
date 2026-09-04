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

// ---------------------------------------------------------------- wrapper ---
const hexToBig = (v) => (v == null ? 0n : BigInt(v));

async function interceptSend(provider, params) {
  const tx = params[0] || {};
  if (tx.data && tx.data !== "0x") {
    throw Object.assign(new Error(
      "CELL refuses transactions carrying calldata. It signs value transfers, " +
      "which it can render in full; it cannot render a contract call as " +
      "something you could evaluate. Use your normal wallet for this one."),
      { code: 4100 });
  }
  const call = (method, ps) => provider.request({ method, params: ps });
  const [chainIdHex, nonceHex, feeHistoryPrio] = await Promise.all([
    call("eth_chainId", []),
    call("eth_getTransactionCount", [tx.from, "pending"]),
    call("eth_maxPriorityFeePerGas", []).catch(() => "0x5f5e100"),
  ]);
  const block = await call("eth_getBlockByNumber", ["latest", false]);
  const base = hexToBig(block?.baseFeePerGas ?? "0x0");
  const prio = hexToBig(tx.maxPriorityFeePerGas ?? feeHistoryPrio);
  const maxFee = hexToBig(tx.maxFeePerGas ?? (base * 2n + prio));
  const gas = hexToBig(tx.gas ?? "0x5208");

  const req = wire.build({
    chainId: parseInt(chainIdHex, 16),
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
  return call("eth_sendRawTransaction", [out.raw]);
}

function wrap(provider) {
  if (!provider || provider.__cellWrapped) return provider;
  const original = provider.request.bind(provider);
  provider.request = async (args) => {
    if (args?.method === "eth_sendTransaction") return interceptSend({ request: original }, args.params || []);
    return original(args);
  };
  provider.__cellWrapped = true;
  console.info("[CELL bridge] wrapped window.ethereum — value transfers route to the device");
  return provider;
}

let held = window.ethereum;
if (held) wrap(held);
try {
  Object.defineProperty(window, "ethereum", {
    configurable: true,
    get: () => held,
    set: (v) => { held = wrap(v); },
  });
} catch { /* a wallet that locked the property; the eager wrap above still applies */ }
