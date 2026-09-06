"""CELL-4B bench console -- the whole signing path, on the Pi's own screen.

Built to be FILMED. Everything the device knows is on one screen at once: the
QR camera that reads the transaction, the Pi camera on the speckle path, the
live spectrometer, and the signature at the end. Nothing is hidden in a
terminal, so a recording shows the real thing rather than a narration of it.

The gate is REAL. It drives the emitters and reads the AS7341, and if the
optical path is not built it says so and refuses rather than pretending. There
is a demo override on the D key, and it labels itself on screen for as long as
it is on -- a gate you can quietly bypass while filming is worse than no gate.
"""
from __future__ import annotations

import os, queue, re, sys, threading, time, tkinter as tk
from dataclasses import dataclass, field

sys.path.insert(0, "upstream")

import base64

import cv2
import numpy as np

BG, PANEL, INK, DIM, ACC = "#0b0d10", "#12171d", "#e6ebf2", "#7c8896", "#ff9d3c"
OK, BAD, LASER = "#5fd39a", "#f08a7a", "#c8442e"
MONO = ("DejaVu Sans Mono", 12)
MONO_S = ("DejaVu Sans Mono", 10)
MONO_L = ("DejaVu Sans Mono", 15, "bold")
HEAD = ("DejaVu Sans", 26, "bold")


@dataclass
class State:
    stage: str = "SCANNING"
    frame_qr: object = None
    frame_pi: object = None
    scanned: str = ""
    tx: dict = field(default_factory=dict)
    display: list = field(default_factory=list)
    gate: dict = field(default_factory=dict)
    result: str = ""
    raw: str = ""
    blind: bool = False
    frames_seen: tuple = (0, 0)
    result_ok: bool = False
    demo: bool = False
    log: list = field(default_factory=list)

    def say(self, msg):
        self.log.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        del self.log[:-9]


S = State()
# --demo pre-arms the override so a filmed run completes without a sample. It
# still lights DEMO GATE ON in the header for the whole session: a bypass that
# does not announce itself is worse than no gate.
S.demo = "--demo" in sys.argv
Q = queue.Queue()



class Frames:
    """pNofM reassembly, with the paranoia qr.py documents.

    Pins the total from the first frame, refuses an index out of range, and
    refuses to overwrite a chunk it already holds with different bytes -- the
    camera sees whatever is in front of it, including the tail of a previous
    transfer.
    """

    def __init__(self):
        self.total = None
        self.chunks = {}

    def reset(self):
        self.total, self.chunks = None, {}

    def feed(self, frame):
        m = re.match(r"^p(\d+)of(\d+)\s*(.*)$", frame.strip(), re.S | re.I)
        if not m:
            return None
        i, n, body = int(m.group(1)), int(m.group(2)), m.group(3)
        if self.total is None:
            self.total = n
        elif n != self.total:
            self.reset(); self.total = n
        if not 1 <= i <= self.total:
            return None
        if i in self.chunks and self.chunks[i] != body:
            self.reset(); self.total = n
        self.chunks[i] = body
        S.frames_seen = (len(self.chunks), self.total)
        if len(self.chunks) != self.total:
            return None
        joined = "".join(self.chunks[k] for k in range(1, self.total + 1))
        self.reset()
        return "p1of1 " + joined


FRAMES = Frames()


# ------------------------------------------------------------ QR camera ----
def qr_thread():
    cap = cv2.VideoCapture(1, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    det = cv2.QRCodeDetector()
    n = 0
    while True:
        ok, f = cap.read()
        if not ok:
            time.sleep(0.1); continue
        n += 1
        # decode every 3rd frame -- 140 ms each, and the preview must stay live
        if n % 3 == 0 and S.stage == "SCANNING":
            try:
                txt, pts, _ = det.detectAndDecode(f)
            except Exception:
                txt, pts = "", None
            if pts is not None:
                cv2.polylines(f, [pts.astype(int)], True, (60, 220, 150), 3)
            if txt:
                got = FRAMES.feed(txt)
                if got is not None:
                    Q.put(("qr", got))
        S.frame_qr = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        time.sleep(0.01)


# ------------------------------------------------------------- Pi camera ----
def pi_thread():
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        cam.configure(cam.create_video_configuration(main={"size": (640, 480)}))
        cam.start()
        while True:
            a = cam.capture_array()
            S.frame_pi = a[:, :, :3] if a.ndim == 3 and a.shape[2] >= 3 else a
            time.sleep(0.08)
    except Exception as e:
        S.say(f"pi cam unavailable: {type(e).__name__}")


# ----------------------------------------------------------------- gate ----
def run_gate():
    """Drive the emitters, read the sensor, decide. Honest either way."""
    from cell4b.hw import Bench
    from cell4b.spectro import Spectrometer
    S.stage = "GATE"; S.say("running the gate")
    try:
        with Bench() as b, Spectrometer(atime=99, astep=1799, gain=256) as sp:
            b.all_off(); time.sleep(0.5)
            dark = sp.read()
            S.gate = {"dark": dark.clear, "seated": b.seated}
            with b.white():
                time.sleep(0.7)
                lit = sp.read()
            S.gate.update({"lit": lit.clear, "rise": lit.clear - dark.clear,
                           "channels": lit.channels})
            b.all_off()
        rise = S.gate["rise"]
        if rise > 80:
            S.gate["verdict"] = "sample present, gate PASSED"
            return True
        S.gate["verdict"] = (f"only {rise:+d} counts under white light -- nothing "
                             f"is scattering back up the aperture. The optical "
                             f"head is not built, so the gate cannot pass.")
        return False
    except Exception as e:
        S.gate["verdict"] = f"{type(e).__name__}: {e}"
        return False


# ---------------------------------------------------------------- signing ----

SEEDFILE = os.path.expanduser("~/.cell/seed")
PATH = "m/44\'/60\'/0\'/0/0"


def device_key():
    """The key the device was provisioned with, derived on demand.

    Never a constant. A hardcoded test key is fine for proving a code path and
    catastrophic the moment someone funds the address it derives to, so this
    reads the seed the device generated for itself and refuses if there is not
    one -- an explicit failure beats silently signing as somebody else.
    """
    import bip32
    if not os.path.exists(SEEDFILE):
        raise RuntimeError(
            "no seed on this device. Run provision_cell.py first -- it "
            "generates one from the kernel CSPRNG and shows you the words.")
    with open(SEEDFILE) as f:
        mn = f.read().strip()
    node = bip32.from_mnemonic(mn).derive(PATH)
    if node.seckey is None:
        raise RuntimeError("derived a watch-only node")
    return node.seckey


def _addr(t, r, s_, y):
    from addresses import eth_address
    import secp256k1 as ec
    return eth_address(ec.ecdsa_recover(t.sighash(), r, s_, y))


def sign_tx(tx):
    import eth
    for cid, (nm, tk_) in {1: ("Ethereum", "ETH"), 8453: ("Base", "ETH"),
                           84532: ("Base Sepolia", "ETH"),
                           11155111: ("Sepolia", "ETH")}.items():
        try: eth.register_chain(cid, nm, tk_)
        except Exception: pass
    common = dict(
        chain_id=tx["chain"], nonce=tx["nonce"],
        max_priority_fee_per_gas=int(tx["maxPrio"], 16),
        max_fee_per_gas=int(tx["maxFee"], 16),
        gas_limit=tx["gas"], to=tx["to"], value=int(tx["value"], 16))
    if tx.get("blind") and tx.get("data") not in ("", "0x", None):
        # A separate type on purpose: code meaning to sign a readable transfer
        # must not silently accept a contract call instead.
        import blindtx
        t = blindtx.BlindContractCall(
            data=bytes.fromhex(tx["data"].removeprefix("0x")), **common)
        S.blind = True
    else:
        t = eth.EthTransaction(**common)
        S.blind = False
    # The device renders with ops.EthereumSpend and signs with
    # eth.EthTransaction. They are separate on purpose -- one is what the owner
    # reads, the other is what the signature commits to -- and EthTransaction
    # has no render() at all, so hasattr() here quietly showed nothing.
    import ops
    sk = device_key()
    if S.blind:
        # BlindContractCall renders itself -- there is no ops class for a call
        # nobody can read, and inventing one would be the fiction this avoids.
        import blindtx
        S.display = t.render()
        r, s_, y = blindtx.sign(t, sk)
    else:
        S.display = ops.EthereumSpend(
            amount_wei=t.value, destination=t.to, chain_id=t.chain_id,
            chain_name=t.chain_name(), nonce=t.nonce,
            max_fee_wei=t.max_fee_wei()).render()
        r, s_, y = eth.sign(t, sk)
    return t.txid(r, s_, y), t.encode_signed(r, s_, y).hex(), _addr(t, r, s_, y)


def worker(txt):
    import base64, json, re
    S.stage = "TRANSACTION"; S.scanned = txt
    S.say(f"scanned {len(txt)} chars")
    try:
        body = re.sub(r"^p\d+of\d+\s*", "", txt.strip())
        tx = json.loads(base64.b64decode(body))
        S.tx = tx
        S.say(f"decoded: {tx['op']} on chain {tx['chain']}")
    except Exception as e:
        S.stage = "SCANNING"; S.say(f"not a CELL frame: {type(e).__name__}"); return
    time.sleep(1.2)
    passed = run_gate()
    if not passed and not S.demo:
        S.stage = "REFUSED"; S.result_ok = False
        S.result = "GATE REFUSED\n\n" + S.gate.get("verdict", "")
        S.say("refused -- no sample"); return
    if not passed and S.demo:
        S.say("DEMO OVERRIDE: signing without a passing gate")
    S.stage = "SIGNING"; S.say("signing on the device"); time.sleep(0.8)
    try:
        txid, raw, frm = sign_tx(S.tx)
        S.result_ok = True; S.stage = "SIGNED"
        S.raw = raw
        S.result = (f"SIGNED{'  (DEMO GATE)' if not passed else ''}\n\n"
                    f"from  {frm}\ntxid  {txid[:34]}...\n\n"
                    f"scan the code to carry it back")
        S.say("signed")
    except Exception as e:
        S.stage = "REFUSED"; S.result_ok = False
        S.result = f"SIGNING REFUSED\n\n{type(e).__name__}\n{e}"
        S.say(f"refused: {type(e).__name__}")


# ------------------------------------------------------------------- UI ----
root = tk.Tk()
root.title("CELL-4B")
root.configure(bg=BG)
root.attributes("-fullscreen", True)

def panel(parent, **kw):
    return tk.Frame(parent, bg=PANEL, highlightbackground="#232a33",
                    highlightthickness=1, **kw)

top = tk.Frame(root, bg=BG); top.pack(fill="x", padx=16, pady=(12, 6))
tk.Label(top, text="CELL-4B", font=HEAD, fg=INK, bg=BG).pack(side="left")
tk.Label(top, text="  PROOF OF LIFE", font=("DejaVu Sans", 13), fg=LASER,
         bg=BG).pack(side="left", padx=(6, 0))
lbl_stage = tk.Label(top, text="SCANNING", font=("DejaVu Sans", 20, "bold"),
                     fg=ACC, bg=BG)
lbl_stage.pack(side="right")
lbl_demo = tk.Label(top, text="", font=("DejaVu Sans", 12, "bold"),
                    fg=BAD, bg=BG)
lbl_demo.pack(side="right", padx=14)

body = tk.Frame(root, bg=BG); body.pack(fill="both", expand=True, padx=16, pady=6)
left = tk.Frame(body, bg=BG); left.pack(side="left", fill="both", expand=True)
right = tk.Frame(body, bg=BG); right.pack(side="right", fill="both",
                                          expand=True, padx=(14, 0))

# Two cameras, two equal halves. pack(expand=True) let the QR feed win the
# whole column: a Label holding an image asks for the image's size, so the
# larger frame simply took the space and the Pi camera was squeezed to nothing.
# grid with a uniform group splits the column by weight instead of by content,
# and pack_propagate(False) on each holder stops the image driving the size at
# all -- the layout decides how big the picture may be, not the other way round.
left.columnconfigure(0, weight=1)
left.rowconfigure(0, weight=1, uniform="cams")
left.rowconfigure(1, weight=1, uniform="cams")

def camera_pane(row, title, pad=(0, 0)):
    pane = panel(left)
    pane.grid(row=row, column=0, sticky="nsew", pady=pad)
    tk.Label(pane, text=title, font=MONO_S, fg=DIM, bg=PANEL,
             anchor="w").pack(fill="x", padx=10, pady=(8, 4))
    hold = tk.Frame(pane, bg="#05070a")
    hold.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    hold.pack_propagate(False)
    lab = tk.Label(hold, bg="#05070a")
    lab.pack(fill="both", expand=True)
    return hold, lab

hold_qr, cv_qr = camera_pane(0, "QR CAMERA   USB /dev/video1")
hold_pi, cv_pi = camera_pane(1, "PI CAMERA   speckle path, lensless", pad=(12, 0))

# --- transaction
p3 = panel(right); p3.pack(fill="both", expand=True)
tk.Label(p3, text="TRANSACTION   as the device rebuilt it", font=MONO_S,
         fg=DIM, bg=PANEL, anchor="w").pack(fill="x", padx=10, pady=(8, 4))
txt_tx = tk.Label(p3, text="waiting for a QR frame", font=MONO, fg=INK,
                  bg=PANEL, justify="left", anchor="nw")
txt_tx.pack(fill="both", expand=True, padx=12, pady=(0, 10))

# --- gate
p4 = panel(right); p4.pack(fill="both", expand=True, pady=(12, 0))
tk.Label(p4, text="GATE   AS7341, 500 ms, gain 256x", font=MONO_S, fg=DIM,
         bg=PANEL, anchor="w").pack(fill="x", padx=10, pady=(8, 4))
txt_gate = tk.Label(p4, text="idle", font=MONO, fg=INK, bg=PANEL,
                    justify="left", anchor="nw", wraplength=520)
txt_gate.pack(fill="both", expand=True, padx=12, pady=(0, 10))

# --- result
p5 = panel(right); p5.pack(fill="both", expand=True, pady=(12, 0))
res_wrap = tk.Frame(p5, bg=PANEL); res_wrap.pack(fill="both", expand=True)
txt_res = tk.Label(res_wrap, text="", font=MONO_L, fg=INK, bg=PANEL,
                   justify="left", anchor="nw", wraplength=340)
txt_res.pack(side="left", fill="both", expand=True, padx=12, pady=10)
# The signature goes home the same way the request came: as pixels. Nothing is
# transmitted, so the airgap survives the return trip too.
cv_out = tk.Label(res_wrap, bg=PANEL)
cv_out.pack(side="right", padx=(0, 12), pady=10)

foot = tk.Frame(root, bg=BG); foot.pack(fill="x", padx=16, pady=(4, 10))
txt_log = tk.Label(foot, text="", font=MONO_S, fg=DIM, bg=BG, justify="left",
                   anchor="w")
txt_log.pack(side="left")
tk.Label(foot, text="S signature   R rescan   D demo gate   Q quit", font=MONO_S, fg=DIM,
         bg=BG).pack(side="right")



# --------------------------------------------------- carry-back overlay ----
carry = tk.Frame(root, bg="#05070a")
carry_qr = tk.Label(carry, bg="#05070a")
carry_hex = tk.Label(carry, font=("DejaVu Sans Mono", 15), fg="#e6ebf2",
                     bg="#05070a", justify="left")
carry_note = tk.Label(carry, font=("DejaVu Sans", 12), fg="#7c8896", bg="#05070a")


def chunked(h):
    """Numbered 8-character blocks. Nobody can type 236 unbroken hex digits
    and know where they are; with a block number they can stop and resume."""
    h = h if h.startswith("0x") else "0x" + h
    body = h[2:]
    rows, per = [], 6
    blocks = [body[i:i + 8] for i in range(0, len(body), 8)]
    for r in range(0, len(blocks), per):
        n = r + 1
        rows.append(f"{n:>3}  " + " ".join(blocks[r:r + per]))
    return "0x\n" + "\n".join(rows)


def show_carry():
    if not S.raw:
        return
    carry.place(relx=0, rely=0, relwidth=1, relheight=1)
    carry_note.config(text="SIGNED TRANSACTION  —  scan with a phone, or type the blocks.  "
                           "Esc to go back")
    carry_note.pack(pady=(18, 10))
    try:
        import segno
        q = segno.make("0x" + S.raw, error="L")
        m = np.array(q.matrix, dtype="uint8")
        m = np.kron(1 - m, np.ones((9, 9), "uint8")) * 255
        m = np.pad(m, 36, constant_values=255)
        ph = to_photo(np.dstack([m] * 3), 460, 460)
        carry_qr.configure(image=ph); carry_qr.image = ph
    except Exception:
        pass
    carry_qr.pack(side="left", padx=(40, 24))
    carry_hex.config(text=chunked(S.raw))
    carry_hex.pack(side="left", anchor="n", pady=8)
    carry.lift()


def hide_carry():
    carry.place_forget()

STAGE_COLOUR = {"SCANNING": ACC, "TRANSACTION": INK, "GATE": ACC,
                "SIGNING": ACC, "SIGNED": OK, "REFUSED": BAD}


def to_photo(arr, w, h):
    """numpy RGB -> tk.PhotoImage, without PIL.ImageTk.

    ImageTk lives in python3-pil.imagetk, a separate apt package, and this
    machine has no sudo. tkinter reads base64 PPM natively, so the dependency
    is avoidable: cv2 does the resize (fast, already a dependency) and P6 is
    a nine-byte header in front of the bytes we already have.
    """
    if arr is None or w < 40 or h < 40:
        return None
    ah, aw = arr.shape[:2]
    scale = min(w / aw, h / ah)
    nw, nh = max(2, int(aw * scale)), max(2, int(ah * scale))
    small = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        small = cv2.cvtColor(small, cv2.COLOR_GRAY2RGB)
    # PNG, not PPM: Tk's -data option took the base64 PPM and said
    # "couldn't recognize image data", and PNG is the one raster format every
    # Tk 8.6 build reads from -data. cv2 encodes it in about a millisecond at
    # these sizes, and it wants BGR.
    ok, buf = cv2.imencode(".png", cv2.cvtColor(small.astype("uint8"),
                                                cv2.COLOR_RGB2BGR))
    if not ok:
        return None
    return tk.PhotoImage(data=base64.b64encode(buf.tobytes()).decode("ascii"))


def tick():
    lbl_stage.config(text=S.stage, fg=STAGE_COLOUR.get(S.stage, INK))
    lbl_demo.config(text="DEMO GATE ON" if S.demo else "")

    for holder, widget, frame in ((hold_qr, cv_qr, S.frame_qr),
                                  (hold_pi, cv_pi, S.frame_pi)):
        ph = to_photo(frame, holder.winfo_width() - 4, holder.winfo_height() - 4)
        if ph is not None:
            widget.configure(image=ph); widget.image = ph

    if S.stage == "SCANNING" and S.frames_seen[1] > 1:
        txt_tx.config(text=f"collecting frames\n\n{S.frames_seen[0]} of {S.frames_seen[1]}")
    if S.tx:
        t = S.tx
        val = int(t["value"], 16) / 1e18
        lines = [f"op       {t['op']}", f"chain    {t['chain']}",
                 f"to       {t['to'][:26]}", f"         {t['to'][26:]}",
                 f"value    {val:.6f} ETH", f"nonce    {t['nonce']}",
                 f"gas      {t['gas']}"]
        if S.display:
            lines += ["", "-- device screen --"] + S.display
        txt_tx.config(text="\n".join(lines))

    if S.gate:
        g = S.gate
        gl = [f"cartridge   {'seated' if g.get('seated') else 'slot empty'}",
              f"dark        {g.get('dark','-')}",
              f"under white {g.get('lit','-')}",
              f"rise        {g.get('rise','-'):+}" if "rise" in g else ""]
        if "channels" in g:
            gl += ["", "  ".join(f"{k}:{v}" for k, v in list(g["channels"].items())[:4]),
                   "  ".join(f"{k}:{v}" for k, v in list(g["channels"].items())[4:])]
        if "verdict" in g:
            gl += ["", g["verdict"]]
        txt_gate.config(text="\n".join(x for x in gl if x != ""))

    txt_res.config(text=S.result, fg=OK if S.result_ok else BAD)
    if S.raw and getattr(cv_out, "shown", None) != S.raw:
        try:
            import segno
            q = segno.make("0x" + S.raw, error="L")
            m = np.array(q.matrix, dtype="uint8")
            m = np.kron(1 - m, np.ones((6, 6), "uint8")) * 255      # scale up
            m = np.pad(m, 24, constant_values=255)
            ph = to_photo(np.dstack([m] * 3), 300, 300)
            cv_out.configure(image=ph); cv_out.image = ph
            cv_out.shown = S.raw
        except Exception as e:
            S.say(f"QR out failed: {type(e).__name__}")
            cv_out.shown = S.raw
    elif not S.raw and getattr(cv_out, "shown", None):
        cv_out.configure(image=""); cv_out.shown = None
    txt_log.config(text="\n".join(S.log[-4:]))

    try:
        kind, val = Q.get_nowait()
        if kind == "qr" and S.stage == "SCANNING":
            threading.Thread(target=worker, args=(val,), daemon=True).start()
    except queue.Empty:
        pass
    root.after(60, tick)


def on_key(e):
    k = e.keysym.lower()
    if k == "q": root.destroy()
    elif k == "s": show_carry()
    elif k == "escape": hide_carry()
    elif k == "r":
        S.stage = "SCANNING"; S.tx = {}; S.gate = {}; S.result = ""; S.raw = ""
        S.display = []; S.say("rescanning")
    elif k == "d":
        S.demo = not S.demo
        S.say(f"demo gate {'ON -- signatures are not blood-backed' if S.demo else 'off'}")


root.bind("<Key>", on_key)
threading.Thread(target=qr_thread, daemon=True).start()
threading.Thread(target=pi_thread, daemon=True).start()
S.say("console up -- point the QR camera at a CELL frame")
tick()
root.mainloop()
