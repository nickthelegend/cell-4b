// The only part of the extension that can reach the mock device.
//
// A page on https://wei.domains cannot fetch http://127.0.0.1 -- mixed content
// is blocked before the request leaves the tab. A service worker is not
// subject to that, so every device call is relayed through here. When the real
// CELL is in use this path goes away entirely: the transaction crosses as QR
// pixels and nothing is fetched at all.

const DEFAULT_DEVICE = "http://127.0.0.1:8799";

async function deviceURL() {
  const { deviceUrl } = await chrome.storage.local.get("deviceUrl");
  return deviceUrl || DEFAULT_DEVICE;
}

async function call(path, body) {
  const url = (await deviceURL()) + path;
  const res = await fetch(url, {
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

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    try {
      if (msg.type === "cell:probe") reply({ ok: true, info: await call("/") });
      else if (msg.type === "cell:sign") reply({ ok: true, result: await call("/", { request: msg.request }) });
      else reply({ ok: false, error: `unknown message ${msg.type}` });
    } catch (e) {
      reply({ ok: false, error: String(e.message || e) });
    }
  })();
  return true;                      // keep the channel open for the async reply
});
