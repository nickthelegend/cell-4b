// Injects the page-context shim and relays its device calls to the worker.
//
// The shim has to run in the PAGE's world to replace window.ethereum -- an
// isolated content script gets its own copy of window and the dApp would never
// see the wrapper. But the page's world cannot talk to the extension, so this
// file sits between the two and passes messages across.

const el = document.createElement("script");
el.type = "module";
el.src = chrome.runtime.getURL("inpage.js");
el.dataset.qrUrl = chrome.runtime.getURL("lib/qr.js");
el.dataset.cssUrl = chrome.runtime.getURL("overlay.css");
(document.head || document.documentElement).prepend(el);

window.addEventListener("message", (ev) => {
  if (ev.source !== window || ev.data?.channel !== "cell-bridge" || !ev.data?.id) return;
  chrome.runtime.sendMessage(ev.data.payload, (reply) => {
    window.postMessage({
      channel: "cell-bridge-reply",
      id: ev.data.id,
      reply: chrome.runtime.lastError
        ? { ok: false, error: chrome.runtime.lastError.message }
        : reply,
    }, "*");
  });
});
