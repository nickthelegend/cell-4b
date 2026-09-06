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

import queue, sys, threading, time, tkinter as tk
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
                Q.put(("qr", txt))
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
def sign_tx(tx):
    import eth
    for cid, (nm, tk_) in {1: ("Ethereum", "ETH"), 8453: ("Base", "ETH"),
                           84532: ("Base Sepolia", "ETH"),
                           11155111: ("Sepolia", "ETH")}.items():
        try: eth.register_chain(cid, nm, tk_)
        except Exception: pass
    t = eth.EthTransaction(
        chain_id=tx["chain"], nonce=tx["nonce"],
        max_priority_fee_per_gas=int(tx["maxPrio"], 16),
        max_fee_per_gas=int(tx["maxFee"], 16),
        gas_limit=tx["gas"], to=tx["to"], value=int(tx["value"], 16))
    # The device renders with ops.EthereumSpend and signs with
    # eth.EthTransaction. They are separate on purpose -- one is what the owner
    # reads, the other is what the signature commits to -- and EthTransaction
    # has no render() at all, so hasattr() here quietly showed nothing.
    import ops
    S.display = ops.EthereumSpend(
        amount_wei=t.value, destination=t.to, chain_id=t.chain_id,
        chain_name=t.chain_name(), nonce=t.nonce,
        max_fee_wei=t.max_fee_wei()).render()
    sk = bytes.fromhex("59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")
    r, s_, y = eth.sign(t, sk)
    return t.txid(r, s_, y), t.encode_signed(r, s_, y).hex(), eth.sender(t, r, s_, y)


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
        S.result = (f"SIGNED{'  (DEMO GATE)' if not passed else ''}\n\n"
                    f"from  {frm}\ntxid  {txid}\n\nraw   {raw[:64]}...")
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

# --- QR camera
p1 = panel(left); p1.pack(fill="both", expand=True)
tk.Label(p1, text="QR CAMERA   USB /dev/video1", font=MONO_S, fg=DIM,
         bg=PANEL, anchor="w").pack(fill="x", padx=10, pady=(8, 4))
cv_qr = tk.Label(p1, bg="#05070a"); cv_qr.pack(fill="both", expand=True,
                                               padx=10, pady=(0, 10))
# --- Pi camera
p2 = panel(left); p2.pack(fill="both", expand=True, pady=(12, 0))
tk.Label(p2, text="PI CAMERA   speckle path, lensless", font=MONO_S, fg=DIM,
         bg=PANEL, anchor="w").pack(fill="x", padx=10, pady=(8, 4))
cv_pi = tk.Label(p2, bg="#05070a"); cv_pi.pack(fill="both", expand=True,
                                               padx=10, pady=(0, 10))

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
txt_res = tk.Label(p5, text="", font=MONO_L, fg=INK, bg=PANEL,
                   justify="left", anchor="nw", wraplength=520)
txt_res.pack(fill="both", expand=True, padx=12, pady=10)

foot = tk.Frame(root, bg=BG); foot.pack(fill="x", padx=16, pady=(4, 10))
txt_log = tk.Label(foot, text="", font=MONO_S, fg=DIM, bg=BG, justify="left",
                   anchor="w")
txt_log.pack(side="left")
tk.Label(foot, text="Q quit   R rescan   D demo gate", font=MONO_S, fg=DIM,
         bg=BG).pack(side="right")

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

    for widget, frame in ((cv_qr, S.frame_qr), (cv_pi, S.frame_pi)):
        ph = to_photo(frame, widget.winfo_width(), widget.winfo_height())
        if ph is not None:
            widget.configure(image=ph); widget.image = ph

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
    elif k == "r":
        S.stage = "SCANNING"; S.tx = {}; S.gate = {}; S.result = ""
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
