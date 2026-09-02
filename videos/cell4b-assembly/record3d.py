"""Record the real 3-D assembly animation, then mux the narration onto it.

    ../../../.venv/bin/python record3d.py

Playwright plays the page's own timeline in real time and captures the browser
viewport with recordVideo -- so this is a genuine render of the animation, not
a frame dump, and the desktop is never touched.

Audio is assembled from the same Kokoro WAVs the timeline was paced against:
each line is delayed to its segment's start, so narration and motion line up by
construction rather than by hand.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "renders")
URL = "http://localhost:8731/viewer/assembly.html"
W, H = 1920, 1080


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        sys.stderr.write(p.stderr[-2000:] + "\n")
        raise SystemExit("ffmpeg failed")


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, "_raw3d")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, channel="chromium",
                               args=["--enable-unsafe-swiftshader",
                                     "--force-device-scale-factor=1"])
        ctx = b.new_context(viewport={"width": W, "height": H},
                            device_scale_factor=1,
                            record_video_dir=tmp,
                            record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(URL, wait_until="load")
        page.wait_for_function("() => window.__anim && window.__anim.ready",
                               timeout=60000)
        total = page.evaluate("() => window.__anim.total")
        segs = page.evaluate("() => window.__anim.segments.map("
                             "g => ({id:g.id, start:g.start}))")
        print(f"  playing {total:.1f}s ...")
        page.evaluate("() => window.__anim.play()")
        page.wait_for_timeout(int((total + 1.5) * 1000))
        vid = page.video
        ctx.close()
        raw = vid.path()
        b.close()
    if errs:
        raise SystemExit(f"page errors: {errs[:2]}")

    # --- audio: each narration line delayed to its own segment start --------
    script = json.load(open(os.path.join(ROOT, "script.json")))
    by_id = {s["id"]: s for s in script}
    ins, filt, mixed = [], [], []
    for i, g in enumerate(segs):
        rec = by_id.get(g["id"])
        if not rec:
            continue
        ins += ["-i", os.path.join(ROOT, rec["wav"])]
        ms = int(g["start"] * 1000)
        filt.append(f"[{len(mixed)}:a]adelay={ms}|{ms},aresample=48000[a{len(mixed)}]")
        mixed.append(f"[a{len(mixed)}]")
    fc = ";".join(filt) + ";" + "".join(mixed) + \
         f"amix=inputs={len(mixed)}:normalize=0[mix]"
    vo = os.path.join(tmp, "vo.m4a")
    run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", fc,
         "-map", "[mix]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-ac", "2", vo])

    out = os.path.join(OUT, "cell4b-assembly-3d.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-i", vo,
         "-map", "0:v", "-map", "1:a", "-t", f"{total:.3f}",
         "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", out])
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
