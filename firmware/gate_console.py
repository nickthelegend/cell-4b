"""BLOOD GATE — the live gate readout, on the Pi's own screen.

Every number here comes from upstream's blood_gate.py, unmodified, against
its shipped thresholds. Nothing is reimplemented for display: the same
gate1_return the device would sign behind is the one printing to this screen,
so a green row means the real gate passed and not that a copy of it did.

The chemistry gates need three reads -- dark, the cartridge's printed white
patch, and the sample -- because every one of them is a RATIO. That is also
why they survive dim emitters: 120 ohm resistors change the illumination
constant, and a ratio divides it out.
"""
from __future__ import annotations

import base64, glob, os, sys, threading, time, tkinter as tk
sys.path.insert(0, "upstream")

import cv2
import numpy as np
import blood_gate as bg

BG, PANEL, INK, DIM = "#08090b", "#101418", "#e6ebf2", "#7c8896"
OK, BAD, ACC, WARN = "#5fd39a", "#f0564a", "#ff9d3c", "#e0c04a"
M = ("DejaVu Sans Mono", 15)
MB = ("DejaVu Sans Mono", 15, "bold")
BIG = ("DejaVu Sans Mono", 22, "bold")

TH = bg.Thresholds()

# ONE picamera2 instance. The preview and the speckle series read the same
# stream: opening it twice fails, and a preview that fought the analysis for
# the sensor would change the exposure the correlation depends on.
CAM = {"frame": None, "burst": [], "err": None}
QR = {"frame": None, "t": 0.0, "err": None, "dev": None}

# Preview lamp. With every emitter off there is genuinely nothing to
# see -- correct for the instrument, useless for a console someone is
# watching. The whites stay lit while idle purely so the pane shows the
# chamber; each measurement drives them itself and this re-asserts
# afterwards. W toggles it, for a true dark frame.
LIGHTS = {"on": True}
LAMP = {"said": False}

# The live colour read and a chemistry/speckle run both want the AS7341 and
# the emitters. One lock, so a measurement always wins and the readout simply
# pauses rather than interleaving reads into someone else's integration.
SPEC_LOCK = threading.Lock()
BENCH_LOCK = threading.Lock()

# One lock for the whole I2C bus. The MAX3010x at 0x57 and the AS7341 at 0x39
# share /dev/i2c-1, and each library opens its OWN busio.I2C -- so their
# internal locks guard nothing against each other. An AS7341 read is a SMUX
# write followed by a read, and pulse traffic interleaving into the middle of
# that returns zeros: a dark reading, which is exactly the value this device
# must never get wrong. Every bus user takes this.
I2C_LOCK = threading.RLock()
COLOUR = {"bands": None, "name": "--", "rgb": "#05070a", "err": None}

BAND_HUE = {415: "#7a3cff", 445: "#3b5bff", 480: "#00a8ff", 515: "#3ddc5a",
            555: "#b6e02a", 590: "#ffc400", 630: "#ff5a2a", 680: "#d61f1f"}


def band_list():
    return bg.BANDS if hasattr(bg, "BANDS") else [415, 445, 480, 515, 555,
                                                  590, 630, 680]


def colour_name(v):
    """Name a hue from the eight bands. Uncalibrated -- no white reference --
    so it names hue, not shade: enough to say green from red, not to grade a
    sample. The gates never use this; it is here to be looked at."""
    if v is None or v.sum() < 25:
        return "-- too dark --", "#05070a"
    B, G, R = v[[0, 1, 2]].mean(), v[[3, 4]].mean(), v[[6, 7]].mean()
    hi = max(R, G, B, 1e-6)
    rgb = "#%02x%02x%02x" % tuple(int(255 * min(x / hi, 1.0)) for x in (R, G, B))
    if hi / max(min(R, G, B), 1e-6) < 1.35:
        return "NEUTRAL / WHITE", rgb
    if R > 1.5 * G and R > 1.5 * B:
        return ("RED" if G < 1.3 * B else "ORANGE-RED"), rgb
    if G > 1.3 * R and G > 1.3 * B:
        return "GREEN", rgb
    if B > 1.3 * R and B > 1.3 * G:
        return "BLUE", rgb
    if R > 1.3 * B and G > 1.3 * B:
        return "YELLOW / WARM", rgb
    if R > G and B > G:
        return "MAGENTA / PINK", rgb
    if G > R and B > R:
        return "CYAN", rgb
    return "MIXED", rgb


def read_colour_once():
    """One spectrometer read, called from the thread that owns the bus.

    This used to be its own thread, and it never got a turn: read_pulse holds
    the bus for its whole window, so two threads racing for one bus meant the
    pulse read always won. Sequential on one thread cannot starve.
    """
    if S["stage"] not in IDLE or not LIGHTS["on"]:
        return
    if SPEC_LOCK.acquire(blocking=False):
        try:
            b = ensure_bench()
            b.white_1.on()
            if b.white_2 is not None:
                b.white_2.on()   # None when the violet holds its bore
            with I2C_LOCK:
                r = SPEC.read()
            v = np.array([r.channels[x] for x in band_list()], dtype=float)
            COLOUR["bands"] = v
            COLOUR["name"], COLOUR["rgb"] = colour_name(v)
            COLOUR["err"] = None
        except Exception as e:
            COLOUR["err"] = f"{type(e).__name__}: {e}"
        finally:
            SPEC_LOCK.release()


def pi_camera_thread():
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        cam.configure(cam.create_video_configuration(main={"size": (320, 240)}))
        cam.start()
        time.sleep(1.2)
        # The chamber is light-tight by design, so auto-exposure hunts across
        # near-total darkness and settles on noise -- the pane then looks dead
        # even with the emitters lit. Fix it long and bright enough to see.
        # Sized for the chamber WITH the preview lamp on, which is the
        # default: 25 ms at unity gain was the exposure that neither blew out
        # nor buried the whites when they were metered directly. Lamp off, the
        # pane goes black -- correct, that is what a light-tight chamber is.
        cam.set_controls({"AeEnable": False, "AwbEnable": False,
                          "ExposureTime": 20000, "AnalogueGain": 2.0})
        time.sleep(0.5)
        while True:
            a = cam.capture_array()
            CAM["frame"] = a[:, :, :3] if a.ndim == 3 and a.shape[2] >= 3 else a
            g = a[:, :, 0] if a.ndim == 3 else a
            CAM["burst"].append(g.astype(float))
            del CAM["burst"][:-16]
            time.sleep(0.05)
    except Exception as e:
        CAM["err"] = f"{type(e).__name__}: {e}"


PULSE = {"p": None, "err": None}


SIGN = {"stage": "", "lines": [], "txid": "", "ok": None, "dry": True}

# ONE reader of the MAX3010x at a time. The live panel polls it continuously
# and the signing read wants its own clean window; run both and each drains
# samples the other was counting on, so perfusion comes out nonsense and a
# perfectly good finger is refused. The panel yields while a signature is
# being authorised.
PULSE_LOCK = threading.Lock()


def sign_with_pulse(spec, bench):
    """The touch tier, start to finish, on screen.

    The pulse is read FRESH here rather than reused from the live panel: the
    panel exists for aiming a finger, and authorising a signature on a reading
    taken before the owner decided to sign is how a gate becomes decoration.
    """
    import json, secrets, urllib.request
    sys.path.insert(0, "upstream")
    import blindtx, eth
    from hashes import keccak256
    from devkey import device_key, device_address
    from cell4b import pulse as P

    RPC = "https://ethereum-sepolia-rpc.publicnode.com"
    TARGET = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"

    def rpc(m, prm):
        r = urllib.request.Request(RPC, method="POST",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m,
                             "params": prm}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "curl/8.0"})
        j = json.loads(urllib.request.urlopen(r, timeout=30).read())
        if "error" in j: raise RuntimeError(j["error"])
        return j["result"]

    SIGN.update(stage="PULSE", lines=["hold your finger still -- 8 s"],
                txid="", ok=None)
    try:
        time.sleep(0.6)                  # let the panel's read finish
        with PULSE_LOCK:
            q = P.read_pulse(seconds=10.0)
        if not q.present:
            SIGN.update(stage="REFUSED", ok=False,
                        lines=[f"bpm {q.bpm:.0f}  conf {q.confidence:.2f}  "
                               f"perfusion {q.perfusion:.2f}",
                               q.reason or "no living finger",
                               "", "NOTHING WAS SIGNED"])
            return
        SIGN.update(stage="SIGNING",
                    lines=[f"pulse accepted: {q.bpm:.0f} bpm, "
                           f"perfusion {q.perfusion:.2f}"])

        ME = device_address()
        secret = secrets.token_bytes(32)
        data = keccak256(b"commit(bytes32)")[:4] + keccak256(b"pulsetest" + secret)
        nonce = int(rpc("eth_getTransactionCount", [ME, "pending"]), 16)
        base = int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
        prio = int(rpc("eth_maxPriorityFeePerGas", []), 16)
        gas = int(rpc("eth_estimateGas", [{"from": ME, "to": TARGET,
                                           "data": "0x" + data.hex()}]), 16)
        tx = blindtx.BlindContractCall(chain_id=11155111, nonce=nonce,
                max_priority_fee_per_gas=prio, max_fee_per_gas=base * 2 + prio,
                gas_limit=int(gas * 1.3), to=TARGET, value=0, data=data)
        r_, s_, y_ = blindtx.sign(tx, device_key())
        who = eth.sender(tx, r_, s_, y_)
        raw = "0x" + tx.encode_signed(r_, s_, y_).hex()
        lines = [f"pulse {q.bpm:.0f} bpm  perfusion {q.perfusion:.2f}  ACCEPTED", ""]
        lines += tx.render()
        lines += ["", f"signed {len(raw)//2 - 1} bytes",
                  f"recovers {who[:20]}...",
                  "MATCHES" if who.lower() == ME.lower() else "WRONG KEY"]
        if SIGN["dry"]:
            lines += ["", "DRY RUN -- not broadcast"]
            SIGN.update(stage="SIGNED (DRY)", ok=True, lines=lines)
            return
        h = rpc("eth_sendRawTransaction", [raw])
        SIGN.update(stage="BROADCAST", ok=True, txid=h,
                    lines=lines + ["", h])
        for _ in range(20):
            rec = rpc("eth_getTransactionReceipt", [h])
            if rec:
                good = int(rec["status"], 16) == 1
                SIGN.update(stage="MINED" if good else "REVERTED", ok=good,
                            lines=lines + ["", h,
                                           f"block {int(rec['blockNumber'],16)}  "
                                           f"gas {int(rec['gasUsed'],16)}"])
                return
            time.sleep(6)
    except Exception as e:
        SIGN.update(stage="ERROR", ok=False,
                    lines=[f"{type(e).__name__}: {e}"[:120]])


def pulse_thread():
    """Rolling 4 s reads, so a finger can be adjusted against live numbers.

    The gate itself uses a longer window; this is for aiming, not deciding.
    """
    try:
        from cell4b import pulse as P
        while True:
            if SIGN["stage"] in ("PULSE", "SIGNING"):
                time.sleep(0.3)          # the signature has the sensor
                continue
            # Colour FIRST. read_pulse builds a fresh Max3010x and samples
            # for its whole window -- with no finger on the sensor that is
            # where this thread sits, and anything queued behind it never
            # runs at all. Reading colour first cannot be starved.
            read_colour_once()      # same thread: the bus is never contended
            with PULSE_LOCK, I2C_LOCK:
                try:
                    PULSE["p"] = P.read_pulse(seconds=3.0)
                except Exception as e:
                    PULSE["err"] = f"{type(e).__name__}"
            time.sleep(0.4)
    except Exception as e:
        PULSE["err"] = f"{type(e).__name__}: {e}"


def uvc_indices():
    """Video nodes backed by uvcvideo, lowest first.

    A USB camera does not keep its index. This one was video1, dropped off the
    bus, and came back as video2 -- so a hardcoded index, or a guess from a
    short list, breaks on every replug. The kernel already knows which nodes
    are UVC; ask it rather than probing and hoping.
    """
    found = []
    for d in sorted(glob.glob("/sys/class/video4linux/video*")):
        try:
            drv = os.path.basename(os.path.realpath(os.path.join(d, "device/driver")))
        except OSError:
            continue
        if drv == "uvcvideo":
            found.append(int(os.path.basename(d)[5:]))
    return found or [1, 2, 0]


def qr_camera_thread():
    """Keep a live frame, or none at all -- never a stale one.

    This used to hold the last good frame forever. When the camera dropped off
    the USB bus mid-session the pane went on showing a picture of the room, so
    it looked live while the scanner re-read one dead image indefinitely. A
    stale frame is worse than a black one: it reads as working. Now a stalled
    capture is dropped, the device is reopened, and the pane goes empty so the
    fault is visible.
    """
    cap, fails = None, 0
    while True:
        if cap is None:
            for idx in uvc_indices():
                c = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                if c.isOpened():
                    ok, _ = c.read()
                    if ok:
                        cap, QR["dev"] = c, idx
                        break
                c.release()
            if cap is None:
                QR["frame"], QR["err"] = None, "no USB camera"
                time.sleep(1.0)
                continue
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # newest frame, not a queue
            fails, QR["err"] = 0, None

        ok, f = cap.read()
        if ok and f is not None:
            QR["frame"], QR["t"], fails = cv2.cvtColor(f, cv2.COLOR_BGR2RGB), time.time(), 0
        else:
            fails += 1
            if fails > 15:
                try:
                    cap.release()
                except Exception:
                    pass
                cap, QR["frame"], QR["err"] = None, None, "camera stalled - reopening"
        time.sleep(0.03)
ADVANCE = threading.Event()

S = {"stage": "idle", "dark": None, "white": None, "chem": None,
     "gates": [], "speckle": [], "msg": "press D to start", "t0": None}


def read3(spec, bench, which):
    """(F8 array, clear, nir) under one illumination."""
    if which == "dark":
        bench.all_off()
    elif which == "white":
        bench.white_1.on()
        if bench.white_2 is not None:
            bench.white_2.on()
    time.sleep(0.35)
    with I2C_LOCK:
        r = spec.read()
    f8 = np.array([r.channels[b] for b in bg.BANDS] if hasattr(bg, "BANDS")
                  else list(r.channels.values()), dtype=float)
    nir = float(r.nir)
    bench.all_off()
    return f8, float(r.clear), nir


def chemistry(spec, bench):
    S["stage"] = "dark"; S["msg"] = "reading dark"
    S["dark"] = read3(spec, bench, "dark")
    S["stage"] = "white"; S["msg"] = "reading the white patch"
    S["white"] = read3(spec, bench, "white")
    # The white patch and the well are at DIFFERENT insertion depths -- 34.6
    # and 42.1 mm. Reading both without advancing the cartridge compares a
    # measurement to itself: G1 then comes out at exactly 1.0000 whatever is
    # in the well, which is a confident answer to a question never asked.
    ADVANCE.clear()
    S["stage"] = "advance"
    S["msg"] = "push the cartridge to the SECOND stop, then press SPACE"
    if not ADVANCE.wait(180):
        S["msg"] = "timed out waiting for the cartridge to be advanced"
        S["stage"] = "idle"
        return
    S["stage"] = "sample"; S["msg"] = "reading the sample"
    S["chem"] = read3(spec, bench, "white")     # sample sits under white light
    cap = {"dark": S["dark"], "white": S["white"], "chem": S["chem"]}
    try:
        S["gates"] = bg.chemistry_gates(cap, TH)
        S["msg"] = "chemistry done — press S for the speckle series"
    except Exception as e:
        S["msg"] = f"{type(e).__name__}: {e}"
    S["stage"] = "chem done"


FRAME_FILE = "/tmp/cell-frame.txt"

OLED = {"dev": None, "last": None}


def oled(*rows):
    """Write to the device's OWN screen.

    The monitor is a convenience. This 128x64 panel is the display that ships
    inside the instrument, and the airgap claim rests on the owner reading
    what they are signing HERE -- on hardware with no network -- rather than
    on a desktop that has one. A console that renders only to the desktop is
    demonstrating the wrong thing.

    Shares /dev/i2c-1 with the AS7341 and the MAX3010x, so it takes the same
    lock, and only writes when the text actually changes: an OLED redrawn
    every tick holds the bus against reads that matter more.
    """
    rows = tuple(str(r)[:21] for r in rows[:5])
    if rows == OLED["last"]:
        return
    try:
        with I2C_LOCK:
            if OLED["dev"] is None:
                from cell4b.display import Display
                OLED["dev"] = Display()
            OLED["dev"].lines(*rows)
        OLED["last"] = rows
    except Exception:
        pass
SCAN = {"qr": None, "parts": {}, "want": 0, "shown": False}


def decode_qr(det, frame):
    """Try harder than one detectAndDecode on one raw frame.

    A screen filmed by a webcam is low contrast, a little out of focus, and
    often moire-patterned; cv2's detector quietly gives up on all three. The
    plain grayscale, an upscaled copy and an adaptively thresholded one cost
    a few milliseconds between them and turn "it will not scan" into "it
    scans". Also reports whether a code was SEEN but not read, which is the
    difference between aim at it and hold it still.

    Returns (text, saw_a_code).
    """
    g = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    seen = False
    tries = (g,
             cv2.resize(g, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC),
             cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY, 31, 5))
    for img in tries:
        try:
            ok, texts, pts, _ = det.detectAndDecodeMulti(img)
        except Exception:
            continue
        if pts is not None and len(pts):
            seen = True
        if ok:
            for t in texts:
                if t:
                    return t, True
    return "", seen


def scan_and_sign(spec, bench):
    """The whole airgap: camera -> QR -> gate -> signature -> QR back.

    Neither half of this existed. The T key built its own Sepolia transaction,
    so it could gate a signature but not sign what a browser handed it;
    qrsign.py decoded a frame but from a FILE and behind no gate at all. A
    device that can gate, and a device that can sign what you give it, are
    only a wallet when they are the same path.

    The pulse is read FRESH, after the transaction is on screen and never
    before: authorising a signature on a reading taken before the owner saw
    what they were signing is how a gate becomes decoration.
    """
    import base64, json, re
    sys.path.insert(0, "upstream")
    import blindtx, eth, ops, segno
    from devkey import device_key
    from cell4b import pulse as P

    SIGN.update(stage="SCAN", txid="", ok=None,
                lines=["hold the QR up to the USB camera",
                       "(or drop a frame at /tmp/cell-frame.txt)"])
    SCAN.update(qr=None, parts={}, want=0, shown=False)

    det = cv2.QRCodeDetector()
    t0 = time.time()
    while time.time() - t0 < 120:
        txt = ""
        # A frame handed over on disk, for when the camera cannot see the
        # screen. The transport changes; nothing else does. It is the same
        # payload, rebuilt from the same fields, shown the same way, behind
        # the same gate -- the device still verifies what it is about to sign.
        if os.path.exists(FRAME_FILE):
            try:
                txt = open(FRAME_FILE).read().strip()
                os.remove(FRAME_FILE)
                SIGN.update(lines=["frame handed over directly"])
            except OSError:
                txt = ""
        else:
            f = QR["frame"]
            if f is None or time.time() - QR["t"] > 2.0:
                # No camera, or a frame old enough that it cannot be what is
                # being held up now. Scanning a stale frame is how a dead
                # camera looks like a bad QR.
                SIGN.update(lines=[QR["err"] or "waiting for the QR camera"])
                time.sleep(0.2); continue
            txt, seen = decode_qr(det, f)
            if not txt:
                SIGN.update(lines=[
                    "QR IN FRAME -- hold it still" if seen
                    else "no QR in frame -- fill more of the camera with it",
                    f"{120 - int(time.time() - t0)} s left"])
        if txt:
            m = re.match(r"^p(\d+)of(\d+)\s*(.*)$", txt.strip(), re.S)
            if m:
                SCAN["parts"][int(m.group(1))] = m.group(3)
                SCAN["want"] = int(m.group(2))
            else:
                SCAN["parts"][1] = txt.strip()
                SCAN["want"] = 1
            got, want = len(SCAN["parts"]), SCAN["want"]
            SIGN.update(lines=[f"frame {got} of {want}",
                               "hold steady" if got < want else "assembled"])
            if want and got >= want:
                break
        time.sleep(0.05)

    if not SCAN["want"] or len(SCAN["parts"]) < SCAN["want"]:
        SIGN.update(stage="REFUSED", ok=False,
                    lines=["no complete QR seen in 120 s", "",
                           "NOTHING WAS SIGNED"])
        return

    try:
        body = "".join(SCAN["parts"][i] for i in sorted(SCAN["parts"]))
        tx = json.loads(base64.b64decode(body))
    except Exception as e:
        SIGN.update(stage="REFUSED", ok=False,
                    lines=[f"frame did not parse: {type(e).__name__}", "",
                           "NOTHING WAS SIGNED"])
        return

    # Rebuilt from FIELDS, never from a digest handed to us. Which type it is
    # decides what the owner is shown, so it is decided by the calldata being
    # there -- not by a flag the page can set.
    data = bytes.fromhex((tx.get("data") or "").removeprefix("0x"))
    if data:
        t = blindtx.BlindContractCall(
            chain_id=tx["chain"], nonce=tx["nonce"],
            max_priority_fee_per_gas=int(tx["maxPrio"], 16),
            max_fee_per_gas=int(tx["maxFee"], 16),
            gas_limit=tx["gas"], to=tx["to"],
            value=int(tx["value"], 16), data=data)
        shown, signer = t.render(), blindtx.sign
    else:
        t = eth.EthTransaction(
            chain_id=tx["chain"], nonce=tx["nonce"],
            max_priority_fee_per_gas=int(tx["maxPrio"], 16),
            max_fee_per_gas=int(tx["maxFee"], 16),
            gas_limit=tx["gas"], to=tx["to"], value=int(tx["value"], 16))
        shown = ops.EthereumSpend(
            amount_wei=t.value, destination=t.to, chain_id=t.chain_id,
            chain_name=t.chain_name(), nonce=t.nonce,
            max_fee_wei=t.max_fee_wei()).render()
        signer = eth.sign

    SIGN.update(stage="PULSE",
                lines=shown + ["", "hold your finger still -- 10 s"])
    time.sleep(0.6)
    with PULSE_LOCK, I2C_LOCK:
        q = P.read_pulse(seconds=10.0)
    if not q.present:
        SIGN.update(stage="REFUSED", ok=False, lines=shown + [
            "", f"bpm {q.bpm:.0f}  conf {q.confidence:.2f}  "
                f"perfusion {q.perfusion:.2f}",
            q.reason or "no living finger", "", "NOTHING WAS SIGNED"])
        return

    r, s_, y = signer(t, device_key())
    raw = "0x" + t.encode_signed(r, s_, y).hex()
    SCAN["qr"] = segno.make(raw, error="l")
    # Also written out, because a signature that exists only as pixels on a
    # screen nobody can scan is a signature that does not exist. The QR is
    # still the airgap; this is the fallback that stops a working device
    # looking like a broken one.
    try:
        with open("/tmp/cell-signed.txt", "w") as fh:
            fh.write(raw + "\n")
    except OSError:
        pass
    txid = t.txid(r, s_, y)
    SIGN.update(stage="SIGNED", ok=True, txid=txid, lines=shown + [
        "", f"bpm {q.bpm:.0f}  conf {q.confidence:.2f}  "
            f"perfusion {q.perfusion:.2f}",
        "PULSE PRESENT -- signed", "", f"txid {txid}",
        "scan the QR back into the browser"])


def sign_with_blood(spec, bench, seconds=300):
    """A signature no finger can authorise. G1-G6, then the key.

    The pulse path proves a person is present. This proves a person BLED --
    which is a different and much stronger claim, and it is the one the whole
    instrument exists to make. Nothing here may be skipped: every gate must
    return passed, and a single failure signs nothing at all.

    The order is forced by the physics, not by convenience. Chemistry first,
    because it is fast and cheap and rules out dye. Speckle second, because
    G5 and G6 are a PAIR -- liquid now, arrested later -- and the sample has
    to be given time to clot between them. That is also why this cannot be
    faked by holding something still: G5 has already required it to flow.
    """
    import base64, json, re
    sys.path.insert(0, "upstream")
    import blindtx, eth, ops, segno
    from devkey import device_key

    if not os.path.exists(FRAME_FILE):
        SIGN.update(stage="NO FRAME", ok=False,
                    lines=["nothing armed to sign",
                           "load a transaction first"])
        return

    def refuse(why, gates=()):
        SIGN.update(stage="REFUSED", ok=False, lines=(
            [why, ""] + [f"  {'PASS' if g.passed else 'FAIL'}  {g.name}"
                         for g in gates] + ["", "NOTHING WAS SIGNED"]))

    # --- chemistry -------------------------------------------------------
    oled("BLOOD GATE", "", "reading dark", "hold still", "")
    S["stage"] = "dark"; S["msg"] = "reading dark"
    S["dark"] = read3(spec, bench, "dark")
    oled("BLOOD GATE", "", "white patch", "", "")
    S["stage"] = "white"; S["msg"] = "reading the white patch"
    S["white"] = read3(spec, bench, "white")
    ADVANCE.clear()
    S["stage"] = "advance"
    S["msg"] = "push the cartridge to the SECOND stop, then press SPACE"
    SIGN.update(stage="BLOOD", ok=None,
                lines=["advance the cartridge to the well", "then press SPACE"])
    oled("BLOOD GATE", "", "advance to", "STOP 2", "then press SPACE")
    if not ADVANCE.wait(180):
        S["stage"] = "idle"
        return refuse("timed out waiting for the cartridge")
    S["stage"] = "sample"; S["msg"] = "reading the sample"
    S["chem"] = read3(spec, bench, "white")
    cap = {"dark": S["dark"], "white": S["white"], "chem": S["chem"]}
    try:
        chem = bg.chemistry_gates(cap, TH)
    except Exception as e:
        S["stage"] = "idle"
        return refuse(f"chemistry read failed: {type(e).__name__}: {e}")
    S["gates"] = chem
    if not all(g.passed for g in chem):
        S["stage"] = "chem done"
        S["msg"] = "chemistry refused -- nothing signed"
        bad = next(g for g in chem if not g.passed)
        oled("REFUSED", "", bad.name[:21], "", "nothing signed")
        return refuse("CHEMISTRY REFUSED THIS SAMPLE", chem)

    # --- speckle: flowing now, arrested later -----------------------------
    oled("G1-G4 PASS", "", "watching it", f"clot {seconds}s", "do not touch")
    SIGN.update(stage="BLOOD", lines=["chemistry passed",
                                      f"watching it clot -- {seconds}s"])
    speckle(spec, bench, seconds)
    motion = [g for g in S["gates"] if g.name.startswith(("G5", "G6"))]
    if len(motion) < 2 or not all(g.passed for g in motion):
        bad = next((g for g in motion if not g.passed), None)
        oled("REFUSED", "", bad.name[:21] if bad else "no series",
             "", "nothing signed")
        return refuse("MOTION GATES REFUSED THIS SAMPLE", S["gates"])

    # --- every gate passed. only now is there a key ----------------------
    txt = open(FRAME_FILE).read().strip()
    os.remove(FRAME_FILE)
    tx = json.loads(base64.b64decode(re.sub(r"^p\d+of\d+\s*", "", txt)))
    data = bytes.fromhex((tx.get("data") or "").removeprefix("0x"))
    if data:
        t = blindtx.BlindContractCall(
            chain_id=tx["chain"], nonce=tx["nonce"],
            max_priority_fee_per_gas=int(tx["maxPrio"], 16),
            max_fee_per_gas=int(tx["maxFee"], 16), gas_limit=tx["gas"],
            to=tx["to"], value=int(tx["value"], 16), data=data)
        shown, signer = t.render(), blindtx.sign
    else:
        t = eth.EthTransaction(
            chain_id=tx["chain"], nonce=tx["nonce"],
            max_priority_fee_per_gas=int(tx["maxPrio"], 16),
            max_fee_per_gas=int(tx["maxFee"], 16), gas_limit=tx["gas"],
            to=tx["to"], value=int(tx["value"], 16))
        shown = ops.EthereumSpend(
            amount_wei=t.value, destination=t.to, chain_id=t.chain_id,
            chain_name=t.chain_name(), nonce=t.nonce,
            max_fee_wei=t.max_fee_wei()).render()
        signer = eth.sign

    for i in range(0, len(shown), 5):
        oled(*shown[i:i + 5])
        time.sleep(2.2)
    r, s_, y = signer(t, device_key())
    raw = "0x" + t.encode_signed(r, s_, y).hex()
    SCAN["qr"] = segno.make(raw, error="l")
    SCAN["shown"] = False
    oled("SIGNED BY BLOOD", "", "all six gates", "passed",
         t.txid(r, s_, y)[:18])
    try:
        with open("/tmp/cell-signed.txt", "w") as fh:
            fh.write(raw + "\n")
    except OSError:
        pass
    SIGN.update(stage="SIGNED BY BLOOD", ok=True, txid=t.txid(r, s_, y),
                lines=shown + ["", "ALL SIX GATES PASSED",
                               f"txid {t.txid(r, s_, y)}"])


def speckle(spec, bench, seconds=600):
    """G5/G6. Reads the shared camera stream while the laser is on."""
    S["stage"] = "speckle"; S["speckle"] = []; S["t0"] = time.time()
    try:
        with bench.laser(require_seated=False):
            while time.time() - S["t0"] < seconds:
                while len(CAM["burst"]) < 12:
                    time.sleep(0.1)
                burst = np.stack(CAM["burst"][-12:])
                try:
                    d, k = bg.speckle_metrics(burst)
                except Exception:
                    d, k = 0.0, 0.0
                S["speckle"].append((time.time() - S["t0"], float(d), float(k)))
                S["msg"] = (f"speckle {len(S['speckle'])} bursts, "
                            f"{seconds - (time.time()-S['t0']):.0f} s left")
                time.sleep(1.0)
    finally:
        bench.all_off()
    sp = S["speckle"]
    if len(sp) > 3:
        t = np.array([r[0] for r in sp]); D = np.array([r[1] for r in sp])
        K = np.array([r[2] for r in sp])
        S["gates"] = [g for g in S["gates"] if not g.name.startswith(("G5", "G6"))]
        S["gates"] += [bg.gate5_free_motion(t, D, K, TH),
                       bg.gate6_motion_arrested(t, D, TH)]
    S["stage"] = "done"; S["msg"] = "series complete"


# ------------------------------------------------------------------- UI ----
# Laid out for the screen this actually runs on: 1520 x 651. Wide and SHORT.
# The first version stacked panels vertically and needed ~1000 px, so the
# signing status, the plot and the key legend all rendered below the bottom
# edge -- X worked from the day it was written and simply had nowhere to say
# so. Three horizontal bands now, none of them taller than they need to be.
root = tk.Tk(); root.title("BLOOD GATE"); root.configure(bg=BG)
root.attributes("-fullscreen", True)

SMALL = ("DejaVu Sans Mono", 10)
HEAD = ("DejaVu Sans Mono", 10)

hdr = tk.Frame(root, bg=BG); hdr.pack(fill="x", padx=12, pady=(6, 2))
tk.Label(hdr, text="BLOOD GATE", font=("DejaVu Sans Mono", 17, "bold"),
         fg=ACC, bg=BG).pack(side="left")
l_stage = tk.Label(hdr, text="idle", font=MB, fg=WARN, bg=BG)
l_stage.pack(side="left", padx=12)
l_msg = tk.Label(hdr, text="", font=SMALL, fg=DIM, bg=BG)
l_msg.pack(side="right")

l_spk = tk.Label(root, text="", font=SMALL, fg=WARN, bg=BG, anchor="w")
l_spk.pack(fill="x", padx=12)
l_raw = tk.Label(root, text="", font=SMALL, fg=INK, bg=BG, anchor="w",
                 justify="left")
l_raw.pack(fill="x", padx=12, pady=(0, 4))

foot = tk.Label(root, text="D  chemistry   S  speckle   T  demo   X  scan+sign   "
                           "B  SIGN WITH BLOOD   L  dry/live   W  lights   Q  quit",
                font=SMALL, fg=DIM, bg=BG)
foot.pack(side="bottom", pady=(2, 5))


def panel(parent, title, **pk):
    f = tk.Frame(parent, bg=PANEL, highlightbackground="#243040",
                 highlightthickness=1)
    f.pack(**pk)
    tk.Label(f, text=title, font=HEAD, fg=DIM, bg=PANEL,
             anchor="w").pack(fill="x", padx=8, pady=(3, 1))
    return f


# --- band 1: the two cameras and the pulse gate ---------------------------
top = tk.Frame(root, bg=BG); top.pack(fill="x", padx=12)
cams = tk.Frame(top, bg=BG); cams.pack(side="left")


def cam_pane(title, note):
    p = panel(cams, title, side="left", padx=(0, 8))
    tk.Label(p, text=note, font=("DejaVu Sans Mono", 9), fg="#4a5563",
             bg=PANEL, anchor="w").pack(fill="x", padx=8)
    hold = tk.Frame(p, bg="#05070a", width=224, height=128)
    hold.pack(padx=8, pady=(4, 8)); hold.pack_propagate(False)
    lab = tk.Label(hold, bg="#05070a"); lab.pack(fill="both", expand=True)
    return hold, lab


hold_pi, cv_pi = cam_pane("PI CAMERA", "lensless, laser lit")
hold_qr, cv_qr = cam_pane("QR CAMERA", "USB - transaction in")

pp = panel(top, "PULSE GATE   MAX3010x 0x57   touch tier",
           side="left", fill="both", expand=True)
l_pulse = tk.Label(pp, text="rest a finger on the sensor", font=MB, fg=DIM,
                   bg=PANEL, anchor="w", justify="left")
l_pulse.pack(fill="both", expand=True, padx=10, pady=(2, 6))

# --- band 2: colour, and the six gates ------------------------------------
mid = tk.Frame(root, bg=BG); mid.pack(fill="x", padx=12, pady=(8, 0))

cp = panel(mid, "SPECTROMETER   AS7341 0x39   live colour",
           side="left", fill="x")
crow = tk.Frame(cp, bg=PANEL); crow.pack(fill="x", padx=10)
sw = tk.Canvas(crow, width=40, height=30, bg="#05070a", highlightthickness=1,
               highlightbackground="#243040")
sw.pack(side="left")
l_col = tk.Label(crow, text="--", font=("DejaVu Sans Mono", 15, "bold"),
                 fg=INK, bg=PANEL, anchor="w")
l_col.pack(side="left", padx=10)
l_ctot = tk.Label(crow, text="", font=SMALL, fg=DIM, bg=PANEL, anchor="w")
l_ctot.pack(side="left")
spec_cv = tk.Canvas(cp, width=540, height=62, bg="#0b0e12",
                    highlightthickness=1, highlightbackground="#243040")
spec_cv.pack(padx=10, pady=(4, 8))

rows = tk.Frame(mid, bg=BG); rows.pack(side="left", fill="both",
                                       expand=True, padx=(10, 0))
GROWS = []
for i in range(6):
    f = tk.Frame(rows, bg=BG); f.pack(fill="x")
    name = tk.Label(f, text="", font=SMALL, fg=DIM, bg=BG, width=17, anchor="w")
    val = tk.Label(f, text="", font=("DejaVu Sans Mono", 10, "bold"), fg=INK,
                   bg=BG, width=9, anchor="e")
    lim = tk.Label(f, text="", font=SMALL, fg=DIM, bg=BG, width=11, anchor="w")
    det = tk.Label(f, text="", font=SMALL, fg=DIM, bg=BG, anchor="w",
                   justify="left", wraplength=560)
    for w in (name, val, lim, det):
        w.pack(side="left", padx=(0, 6))
    GROWS.append((name, val, lim, det))

# --- band 3: what is being signed, and the speckle trace ------------------
bot = tk.Frame(root, bg=BG); bot.pack(fill="both", expand=True, padx=12,
                                      pady=(8, 0))
sp_ = panel(bot, "SIGN   T demo   X scan a QR and sign it",
            side="left", fill="both")
l_sh = tk.Label(sp_, text="", font=("DejaVu Sans Mono", 9), fg=DIM, bg=PANEL,
                anchor="w")
l_sh.pack(fill="x", padx=10)
l_sign = tk.Label(sp_, text="idle", font=SMALL, fg=DIM, bg=PANEL, anchor="nw",
                  justify="left", width=46)
l_sign.pack(fill="both", expand=True, padx=10, pady=(0, 6))

plotf = tk.Frame(bot, bg=BG); plotf.pack(side="left", fill="both",
                                         expand=True, padx=(10, 0))
cv = tk.Canvas(plotf, bg="#0b0e12", highlightthickness=1,
               highlightbackground="#243040", height=120)
cv.pack(fill="both", expand=True)


def to_photo(arr, w, h):
    if arr is None or w < 40 or h < 40:
        return None
    ah, aw = arr.shape[:2]
    k = min(w / aw, h / ah)
    small = cv2.resize(arr, (max(2, int(aw * k)), max(2, int(ah * k))),
                       interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        small = cv2.cvtColor(small, cv2.COLOR_GRAY2RGB)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(small.astype("uint8"),
                                                cv2.COLOR_RGB2BGR))
    return tk.PhotoImage(data=base64.b64encode(buf.tobytes()).decode()) if ok else None


def draw_cams():
    for hold, lab, frame in ((hold_pi, cv_pi, CAM["frame"]),
                             (hold_qr, cv_qr, QR["frame"])):
        ph = to_photo(frame, hold.winfo_width() - 4, hold.winfo_height() - 4)
        if ph is not None:
            lab.configure(image=ph); lab.image = ph


def draw_colour():
    v = COLOUR["bands"]
    sw.delete("all")
    sw.create_rectangle(0, 0, 60, 46, fill=COLOUR["rgb"], outline="")
    l_col.config(text=COLOUR["err"] or COLOUR["name"],
                 fg=BAD if COLOUR["err"] else INK)
    spec_cv.delete("all")
    w = spec_cv.winfo_width() or 700
    h = spec_cv.winfo_height() or 96
    bands = band_list()
    if v is None:
        spec_cv.create_text(w / 2, h / 2, text="waiting for a read",
                            fill=DIM, font=M)
        l_ctot.config(text="")
        return
    l_ctot.config(text=f"total {int(v.sum())}   peak {bands[int(v.argmax())]} nm")
    pad, base = 8, h - 20
    bw = (w - 2 * pad) / len(bands)
    hi = max(float(v.max()), 1.0)
    for i, (band, val) in enumerate(zip(bands, v)):
        x0 = pad + i * bw + 3
        x1 = pad + (i + 1) * bw - 3
        y = base - (base - 10) * (val / hi)
        spec_cv.create_rectangle(x0, y, x1, base, fill=BAND_HUE.get(band, INK),
                                 outline="")
        spec_cv.create_text((x0 + x1) / 2, base + 10, text=str(band),
                            fill=DIM, font=("DejaVu Sans Mono", 9))
        spec_cv.create_text((x0 + x1) / 2, y - 8, text=f"{val:.0f}",
                            fill=DIM, font=("DejaVu Sans Mono", 9))


def show_signed_qr():
    """Put the signature on the glass, full screen.

    The signing path built this QR from the first version and then never drew
    it, so a signature that existed could only be got at over SSH. On a device
    whose entire claim is that nothing but pixels crosses the gap, the one
    artefact that has to be on screen is this one. Full screen and high
    contrast, because it is about to be read by a webcam.
    """
    import io
    q = SCAN.get("qr")
    if q is None:
        return
    top = tk.Toplevel(root)
    top.configure(bg="white")
    top.attributes("-fullscreen", True)
    buf = io.BytesIO()
    q.png(buf, scale=7, border=4, dark="#000000", light="#ffffff")
    ph = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode())
    lab = tk.Label(top, image=ph, bg="white")
    lab.image = ph
    lab.pack(expand=True)
    tk.Label(top, bg="white", fg="#111", font=("DejaVu Sans Mono", 13),
             text="SIGNED -- scan this back into the browser."
                  "   any key to close").pack(pady=6)
    top.bind("<Key>", lambda e: top.destroy())
    top.focus_force()


def draw_plot():
    """D over time against the two speckle thresholds.

    The gates are a band, not a line: G5 wants D ABOVE 0.6 (still flowing)
    and G6 wants it BELOW 0.25 (arrested). Shading those regions makes a
    passing trace legible at a glance instead of needing the numbers read.
    """
    cv.delete("all")
    w, h = cv.winfo_width() or 1200, cv.winfo_height() or 300
    L, R, T, B = 66, 30, 30, 38
    pw, ph = w - L - R, h - T - B
    if pw < 120 or ph < 70:
        return
    y_of = lambda v: T + ph - min(max(v, 0.0), 1.0) * ph

    cv.create_rectangle(L, T, L + pw, y_of(TH.d_liquid_min),
                        fill="#0d1f18", outline="")
    cv.create_rectangle(L, y_of(TH.d_clot_max), L + pw, T + ph,
                        fill="#221a0d", outline="")

    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = y_of(v)
        cv.create_line(L, y, L + pw, y, fill="#18202a")
        cv.create_text(L - 12, y, text=f"{v:.2f}", fill=DIM, anchor="e",
                       font=("DejaVu Sans Mono", 12))

    for val, lab, col in ((TH.d_liquid_min, f"G5  liquid   D >= {TH.d_liquid_min}", OK),
                          (TH.d_clot_max, f"G6  clot     D <= {TH.d_clot_max}", ACC)):
        y = y_of(val)
        cv.create_line(L, y, L + pw, y, fill=col, dash=(6, 4), width=2)
        cv.create_text(L + pw - 8, y - 13, text=lab, fill=col, anchor="e",
                       font=("DejaVu Sans Mono", 13, "bold"))

    cv.create_rectangle(L, T, L + pw, T + ph, outline="#2a3644")
    cv.create_text(L, T - 15, text="SPECKLE   D decorrelation over time",
                   fill=DIM, anchor="w", font=("DejaVu Sans Mono", 12))

    sp = S["speckle"]
    if len(sp) < 2:
        cv.create_text(L + pw / 2, T + ph / 2, text="no speckle series yet",
                       fill=DIM, font=M)
        return

    tmax = max(r[0] for r in sp) or 1
    x_of = lambda t: L + t / tmax * pw
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        t = tmax * frac; x = x_of(t)
        cv.create_line(x, T + ph, x, T + ph + 5, fill="#2a3644")
        cv.create_text(x, T + ph + 18, text=f"{t:.0f}s", fill=DIM,
                       font=("DejaVu Sans Mono", 11))

    cv.create_line(*[c for r in sp for c in (x_of(r[0]), y_of(r[2]))],
                   fill="#4a90d9", width=1, dash=(3, 3))
    cv.create_line(*[c for r in sp for c in (x_of(r[0]), y_of(r[1]))],
                   fill=INK, width=2)

    lx, ly = x_of(sp[-1][0]), y_of(sp[-1][1])
    cv.create_oval(lx - 5, ly - 5, lx + 5, ly + 5, fill=ACC, outline="")
    cv.create_text(lx - 12, ly - 17, text=f"D {sp[-1][1]:.2f}", fill=ACC,
                   anchor="e", font=("DejaVu Sans Mono", 13, "bold"))
    cv.create_text(L + 10, T + 15, text="D  decorrelation", fill=INK,
                   anchor="w", font=("DejaVu Sans Mono", 11))
    cv.create_text(L + 10, T + 32, text="K  speckle contrast", fill="#4a90d9",
                   anchor="w", font=("DejaVu Sans Mono", 11))


IDLE = ("idle", "chem done", "done")


def tick():
    if SCAN.get("qr") is not None and not SCAN.get("shown"):
        SCAN["shown"] = True
        show_signed_qr()
    if LIGHTS["on"] and S["stage"] in IDLE:
        try:
            b = ensure_bench()
            b.white_1.on()
            if b.white_2 is not None:
                b.white_2.on()   # None when the violet holds its bore
        except Exception as e:
            # Said once, not every 300 ms. Swallowing this silently turned a
            # hardware fault into "the camera pane is black", which is the
            # same symptom as a dark chamber and sent us chasing optics.
            if not LAMP["said"]:
                LAMP["said"] = True
                S["msg"] = f"preview lamp: {type(e).__name__}: {e}"

    l_stage.config(text=S["stage"].upper())
    l_msg.config(text=S["msg"])
    sp = S["speckle"]
    if sp:
        l_spk.config(text=f"speckle:  D {sp[0][1]:.2f} -> {sp[-1][1]:.2f}    "
                          f"K {sp[-1][2]:.3f}    t {sp[-1][0]:.0f}s    n {len(sp)}")
    else:
        l_spk.config(text="speckle:  not run")
    if S["white"] and S["dark"] and S["chem"]:
        wf, wc, wn = S["white"]; df, dc, dn = S["dark"]; cf, cc, cn = S["chem"]
        b = bg.BANDS if hasattr(bg, "BANDS") else [415,445,480,515,555,590,630,680]
        l_raw.config(text=(f"white clr {wc:8.0f}   dark clr {dc:6.0f}\n"
                           f"sample clr {cc:7.0f}   415:{cf[0]:.0f}   630:{cf[6]:.0f}"))
    for i, (name, val, lim, det) in enumerate(GROWS):
        if i < len(S["gates"]):
            g = S["gates"][i]
            col = OK if g.passed else BAD
            name.config(text=g.name[:16], fg=col)
            val.config(text=f"{g.value:.4f}", fg=col)
            lim.config(text=f"lim {g.threshold:g}", fg=DIM)
            det.config(text=(g.detail or "")[:52], fg=DIM)
        else:
            for wgt in (name, val, lim, det): wgt.config(text="")
    q = PULSE["p"]
    if q is None:
        l_pulse.config(text=PULSE["err"] or "reading...", fg=DIM)
    else:
        import cell4b.pulse as _P
        okc = q.confidence >= 0.5
        okb = 40.0 <= q.bpm <= 200.0
        okp = _P.PERFUSION_MIN <= q.perfusion <= _P.PERFUSION_MAX
        mark = lambda ok: "OK " if ok else "no "
        txt = (f"{mark(okb)}bpm {q.bpm:6.1f}      "
               f"{mark(okc)}conf {q.confidence:.3f}      "
               f"{mark(okp)}perfusion {q.perfusion:6.3f}  "
               f"(want {_P.PERFUSION_MIN}-{_P.PERFUSION_MAX})")
        if q.present:
            txt += "\n\nPULSE PRESENT -- a living finger"
        elif q.reason:
            txt += "\n\n" + q.reason[:78]
        l_pulse.config(text=txt, fg=OK if q.present else BAD)
    l_sh.config(text=f"SIGN WITH PULSE   press T   "
                     f"[{'DRY RUN' if SIGN['dry'] else 'LIVE - WILL BROADCAST'}]",
                fg=DIM if SIGN["dry"] else BAD)
    if SIGN["stage"]:
        col = OK if SIGN["ok"] else (BAD if SIGN["ok"] is False else WARN)
        l_sign.config(text=SIGN["stage"] + "\n" + "\n".join(SIGN["lines"][:16]),
                      fg=col)
    draw_cams()
    draw_colour()
    draw_plot()
    root.after(300, tick)


BENCH = SPEC = None


def ensure_bench():
    """Build the bench once, whoever asks first.

    Unlocked, the Tk tick and the bus thread both saw BENCH is None and both
    constructed one; the loser died on GPIOPinInUse and its caller silently
    lost the emitters. Double-checked under a lock, so exactly one wins.
    """
    global BENCH, SPEC
    with BENCH_LOCK:
        if BENCH is None:
            from cell4b.hw import Bench
            from cell4b.spectro import atime_for, EMITTER_OHMS, Spectrometer
            BENCH = Bench()
            SPEC = Spectrometer(atime=atime_for(EMITTER_OHMS), astep=1799, gain=256)
    return BENCH


def start(fn, *a):
    ensure_bench()

    def held(*args):
        with SPEC_LOCK:            # the live readout stands down for this
            fn(*args)
    threading.Thread(target=held, args=(SPEC, BENCH) + a, daemon=True).start()


def on_key(e):
    k = e.keysym.lower()
    if k == "q":
        if BENCH: BENCH.all_off()
        root.destroy()
    elif k == "d" and S["stage"] in ("idle", "chem done", "done"):
        start(chemistry)
    elif k == "s" and S["stage"] in ("chem done", "done", "idle"):
        start(speckle)
    elif k == "t":
        start(sign_with_pulse)
    elif k == "x":
        start(scan_and_sign)
    elif k == "b" and S["stage"] in IDLE:
        start(sign_with_blood)
    elif k == "l":
        SIGN["dry"] = not SIGN["dry"]
    elif k in ("space", "return") and S["stage"] == "advance":
        ADVANCE.set()
    elif k == "w":
        LIGHTS["on"] = not LIGHTS["on"]
        if not LIGHTS["on"] and BENCH:
            BENCH.all_off()


root.bind("<Key>", on_key)
threading.Thread(target=pi_camera_thread, daemon=True).start()
threading.Thread(target=qr_camera_thread, daemon=True).start()
threading.Thread(target=pulse_thread, daemon=True).start()
tick()
root.mainloop()
