const u = document.getElementById("u"), s = document.getElementById("s");
chrome.storage.local.get("deviceUrl", ({ deviceUrl }) => {
  u.value = deviceUrl || "http://127.0.0.1:8799";
});
document.getElementById("save").onclick = () =>
  chrome.storage.local.set({ deviceUrl: u.value.trim() }, () => {
    s.className = "ok"; s.textContent = "saved";
  });
document.getElementById("probe").onclick = () => {
  s.className = ""; s.textContent = "probing…";
  chrome.runtime.sendMessage({ type: "cell:probe" }, (r) => {
    if (!r?.ok) { s.className = "bad"; s.textContent = r?.error || "unreachable"; return; }
    s.className = "ok";
    s.textContent = `${r.info.device}\n${r.info.address}\ngate: ${r.info.gate}\n${r.info.warning}`;
  });
};
