"""Record one video file per scene by driving the real viewer with Playwright.

    python3 video/record.py [--only 05_cutaway]

Chromium runs headless with `record_video_dir`, so ONLY the browser viewport is
captured to a file. Nothing touches the desktop and the machine stays usable.

One browser context per scene => one video file per scene, which is what makes
a single scene re-recordable later without disturbing the others.

Every scene:
  * loads the real viewer against the real manifest and GLBs
  * runs its `prep` actions (state the scene needs but should not show)
  * marks t0, runs its `actions`, and records how long that took
  * asserts the console stayed clean

Nothing is staged. The audit badge shows whatever the manifest says.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenes import SCENES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "video", "out")
RAW = os.path.join(OUT, "raw")
PORT = 8731
VIEW = f"http://localhost:{PORT}/viewer/index.html"
W, H = 1440, 900

TITLE_JS = r"""
(args) => {
  const [main, sub] = args;
  document.querySelectorAll('.vidcard').forEach(e => e.remove());
  const d = document.createElement('div');
  d.className = 'vidcard';
  d.innerHTML = `
    <style>
      .vidcard{position:fixed;inset:0;z-index:9999;display:flex;
        flex-direction:column;align-items:center;justify-content:center;
        background:#0e1013;font:400 13px ui-sans-serif,system-ui,sans-serif}
      .vc-wrap{position:relative;text-align:center}
      .vc-main{font-size:64px;font-weight:650;letter-spacing:-.03em;
        color:#e6eaef;white-space:nowrap;
        clip-path:inset(0 100% 0 0);animation:vcWipe 1.15s cubic-bezier(.2,.8,.2,1) forwards}
      .vc-main b{color:#ff9d3c}
      .vc-rule{height:2px;background:#ff9d3c;margin:18px auto 0;width:0;
        animation:vcRule .8s cubic-bezier(.2,.8,.2,1) .85s forwards}
      .vc-sub{margin-top:16px;font-size:19px;color:#8b95a3;opacity:0;
        transform:translateY(14px);
        animation:vcUp .7s cubic-bezier(.2,.8,.2,1) 1.15s forwards}
      @keyframes vcWipe{to{clip-path:inset(0 0 0 0)}}
      @keyframes vcRule{to{width:min(520px,70vw)}}
      @keyframes vcUp{to{opacity:1;transform:none}}
    </style>
    <div class="vc-wrap">
      <div class="vc-main"></div>
      <div class="vc-rule"></div>
      <div class="vc-sub"></div>
    </div>`;
  document.body.appendChild(d);
  const m = d.querySelector('.vc-main');
  // colour the -4B / the repo tail without innerHTML-ing user text
  const i = main.indexOf('-');
  if (i > 0 && main.startsWith('CELL')) {
    m.append(main.slice(0, i));
    const b = document.createElement('b'); b.textContent = main.slice(i);
    m.append(b);
  } else { m.textContent = main; }
  d.querySelector('.vc-sub').textContent = sub;
}
"""


CAPTION_JS = r"""
(text) => {
  document.querySelectorAll('.vidcap').forEach(e => e.remove());
  const d = document.createElement('div');
  d.className = 'vidcap';
  d.innerHTML = `<style>
    .vidcap{position:fixed;left:0;right:0;bottom:0;z-index:9998;
      display:flex;justify-content:center;pointer-events:none;
      padding:0 0 26px;
      background:linear-gradient(to top,#000c 0%,#000a 46%,#0000 100%)}
    .vidcap span{max-width:78%;text-align:center;color:#fff;
      font:400 21px/1.42 ui-sans-serif,system-ui,-apple-system,sans-serif;
      text-shadow:0 2px 8px #000c;padding-top:34px}
  </style><span></span>`;
  d.querySelector('span').textContent = text;
  document.body.appendChild(d);
}
"""


def wait_ready(page, timeout=30000):
    page.wait_for_function(
        "() => document.querySelectorAll('#parts .row').length > 0",
        timeout=timeout)
    page.wait_for_timeout(500)


def pick_model(page, label):
    page.select_option("#model", label=label)
    page.wait_for_function(
        "() => document.querySelectorAll('#parts .row').length > 0",
        timeout=30000)
    page.wait_for_timeout(700)


def orbit(page, deg, secs):
    box = page.locator("canvas").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    steps = max(12, int(secs * 30))
    page.mouse.move(cx, cy)
    page.mouse.down()
    # a shallow arc rather than a straight drag -- reads as a camera move
    for i in range(1, steps + 1):
        t = i / steps
        page.mouse.move(cx + (deg * 2.6) * t,
                        cy - 26 * math.sin(math.pi * t))
        page.wait_for_timeout(int(secs * 1000 / steps))
    page.mouse.up()


def toggle(page, names, on):
    for n in names:
        page.evaluate(
            """([n, on]) => { const cb = document.getElementById('cb_' + n);
                 if (cb) { cb.checked = on;
                           cb.dispatchEvent(new Event('change')); } }""",
            [n, on])
    page.wait_for_timeout(250)


def run_actions(page, actions):
    for verb, args in actions:
        if verb == "model":
            pick_model(page, args[0])
        elif verb == "orbit":
            orbit(page, args[0], args[1])
        elif verb == "zoom":
            box = page.locator("canvas").bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2,
                            box["y"] + box["height"] / 2)
            for _ in range(args[0]):
                page.mouse.wheel(0, -260)
                page.wait_for_timeout(180)
        elif verb == "hide":
            toggle(page, args, False)
        elif verb == "show":
            toggle(page, args, True)
        elif verb == "scroll":
            page.evaluate("y => document.getElementById('side').scrollTop = y",
                          args[0])
            page.wait_for_timeout(400)
        elif verb == "hold":
            page.wait_for_timeout(int(args[0] * 1000))
        elif verb == "title":
            page.evaluate(TITLE_JS, args)
            page.wait_for_timeout(300)
        else:
            raise SystemExit(f"unknown verb {verb}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=None)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    os.makedirs(RAW, exist_ok=True)
    todo = [s for s in SCENES if not args.only or s["id"] in args.only]
    meta = {}
    metaf = os.path.join(OUT, "record.json")
    if os.path.exists(metaf):
        meta = json.load(open(metaf))

    with sync_playwright() as pw:
        # channel="chromium" uses the full headless browser rather than
        # chrome-headless-shell. The shell cannot do WebGL, and this whole
        # video is a WebGL viewer.
        browser = pw.chromium.launch(headless=True, channel="chromium",
                                     args=["--enable-gpu",
                                           "--use-gl=angle",
                                           "--use-angle=metal",
                                           "--enable-unsafe-swiftshader"])
        for sc in todo:
            sid = sc["id"]
            tmp = os.path.join(RAW, "_tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp, exist_ok=True)

            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                device_scale_factor=1,
                record_video_dir=tmp,
                record_video_size={"width": W, "height": H})
            page = ctx.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text)
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(VIEW, wait_until="load")
            wait_ready(page)
            run_actions(page, sc.get("prep", []))
            # Caption is rendered by the PAGE, not by ffmpeg: this ffmpeg build
            # has no drawtext/subtitles filter, and the browser has real
            # typography anyway. One scene, one cue -- it is on screen for
            # exactly the footage its narration line covers, so no retiming can
            # ever desync it.
            page.evaluate(CAPTION_JS, sc["say"])
            page.wait_for_timeout(300)

            t0 = time.time()
            run_actions(page, sc["actions"])
            body = time.time() - t0
            if body < sc.get("min_s", 0):
                page.wait_for_timeout(int((sc["min_s"] - body) * 1000))
                body = sc["min_s"]
            page.wait_for_timeout(250)

            vid = page.video
            ctx.close()                      # flushes the file
            src = vid.path()
            dst = os.path.join(RAW, f"{sid}.webm")
            shutil.move(src, dst)
            shutil.rmtree(tmp, ignore_errors=True)

            dur = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", dst],
                capture_output=True, text=True).stdout.strip() or 0.0)
            trim = max(0.0, dur - body - 0.25)

            if errors:
                print(f"  !! {sid}: {len(errors)} console error(s)")
                for e in errors[:3]:
                    print(f"     {e[:120]}")
                raise SystemExit("console errors in footage -- refusing to ship")

            meta[sid] = {"file": f"raw/{sid}.webm", "duration": round(dur, 3),
                         "trim_start": round(trim, 3),
                         "body": round(body, 3), "say": sc["say"]}
            print(f"  {sid:14s} {dur:6.2f}s recorded, trim {trim:5.2f}s "
                  f"-> {body:5.2f}s of content")
            json.dump(meta, open(metaf, "w"), indent=1)
        browser.close()
    print(f"\n{len(todo)} scene(s) -> {RAW}")


if __name__ == "__main__":
    main()
