const F = ["address", "chainId", "rpcUrl", "deviceUrl", "gate"];
const BOOLS = ["blind"];
const msg = (t, ok = true) => {
  const m = document.getElementById("msg");
  m.textContent = t; m.style.color = ok ? "#5fd39a" : "#f08a7a";
};

chrome.runtime.sendMessage({ type: "cell:config" }, (r) => {
  if (!r?.ok) return msg("could not read config", false);
  for (const k of F) if (r.config[k] != null) document.getElementById(k).value = r.config[k];
  for (const k of BOOLS) document.getElementById(k).checked = !!r.config[k];
});

document.getElementById("save").onclick = () => {
  const v = Object.fromEntries(F.map((k) => [k, document.getElementById(k).value.trim()]));
  for (const k of BOOLS) v[k] = document.getElementById(k).checked;
  if (v.address && !/^0x[0-9a-fA-F]{40}$/.test(v.address))
    return msg("that is not a 20-byte address", false);
  chrome.storage.local.set(v, () => msg("saved — reload the dApp tab"));
};

document.getElementById("probe").onclick = () => {
  msg("probing…");
  chrome.runtime.sendMessage({ type: "cell:probe" }, (r) => {
    if (!r?.ok) return msg("device unreachable\n" + (r?.error || ""), false);
    msg("device: " + JSON.stringify(r.info).slice(0, 120));
  });
};
