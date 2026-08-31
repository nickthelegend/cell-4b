"""Cut every scene to its narration, burn its caption, and stitch the film.

    python3 video/assemble.py            # full cut, honours video/scenes.json
    python3 video/assemble.py --force    # re-encode every scene

Pacing rule, per scene:
  * the clip is trimmed of its prep, then matched to the MEASURED narration
    length -- speed-ramped when the footage runs long, last frame held when it
    runs short. No scene is ever cut short of its line.
  * then the scene's own multiplier from scenes.json is applied, video by
    setpts and audio by atempo so pitch stays natural.

Scene mp4s are cached and keyed on their multiplier, so changing one scene's
speed only re-encodes that scene.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID = os.path.join(ROOT, "video")
OUT = os.path.join(VID, "out")
CUTS = os.path.join(OUT, "cuts")
SCENES_JSON = os.path.join(VID, "scenes.json")

FONT = None
for cand in ("/System/Library/Fonts/Supplemental/Arial.ttf",
             "/System/Library/Fonts/Helvetica.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
    if os.path.exists(cand):
        FONT = cand
        break


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        sys.stderr.write(p.stderr[-2500:] + "\n")
        raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:8])}...")
    return p


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0.0)


def atempo_chain(m):
    """atempo only accepts 0.5..2.0, so compose it for bigger multipliers."""
    parts, rem = [], float(m)
    while rem > 2.0:
        parts.append("atempo=2.0")
        rem /= 2.0
    while rem < 0.5:
        parts.append("atempo=0.5")
        rem /= 0.5
    parts.append(f"atempo={rem:.6f}")
    return ",".join(parts)


def wrap(text, width=64):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines[:2]          # one-line cues; two only if it truly must wrap


def build_scene(sid, rec, vo, mult, force):
    src = os.path.join(OUT, rec["file"])
    wav = os.path.join(OUT, vo["wav"])
    dst = os.path.join(CUTS, f"{sid}@{mult:g}.mp4")
    if os.path.exists(dst) and not force:
        return dst, probe(dst)

    trim = rec["trim_start"]
    body = max(0.4, rec["duration"] - trim)
    target = vo["duration"]                 # match the narration exactly
    final = target / mult

    # video: trim -> fit to `target` -> apply the scene multiplier
    ratio = (target / body) / mult          # PTS scale, combined
    vf = [f"setpts={ratio:.6f}*PTS"]
    if body < target:                       # footage short: hold the last frame
        vf = [f"tpad=stop_mode=clone:stop_duration={target - body:.3f}",
              f"setpts={(1.0 / mult):.6f}*PTS"]
    vf.append(f"fps=30,scale=1440:900:flags=lanczos,format=yuv420p")

    # The caption is already in the footage -- record.py renders it in the
    # page. This ffmpeg build has no drawtext or subtitles filter, and burning
    # it browser-side gives proper text shaping for free.

    af = f"{atempo_chain(mult)},apad" if mult != 1.0 else "apad"

    run(["ffmpeg", "-y", "-v", "error",
         "-ss", f"{trim:.3f}", "-i", src, "-i", wav,
         "-filter_complex",
         f"[0:v]{','.join(vf)}[v];[1:a]{af}[a]",
         "-map", "[v]", "-map", "[a]",
         "-t", f"{final:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", dst])
    return dst, probe(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default=os.path.join(OUT, "cell4b-demo.mp4"))
    args = ap.parse_args()

    rec = json.load(open(os.path.join(OUT, "record.json")))
    vo = json.load(open(os.path.join(OUT, "vo.json")))
    os.makedirs(CUTS, exist_ok=True)

    order = sorted(set(rec) & set(vo))
    if not order:
        raise SystemExit("no scenes with both footage and narration")

    # scenes.json: per-scene speed dial, created at 1x on first run and never
    # overwritten afterwards -- it is the user's file.
    if os.path.exists(SCENES_JSON):
        cfg = json.load(open(SCENES_JSON))
    else:
        cfg = {"_help": "speed multiplier per scene; 1 = real time. "
                        "Edit, then run video/rerender.py.",
               "scenes": {}}
    cfg["scenes"] = {**{s: cfg.get("scenes", {}).get(s, 1) for s in order}}

    print(f"{'scene':16s} {'mult':>5s} {'vo':>7s} {'out':>7s}")
    print("-" * 40)
    parts, total = [], 0.0
    for sid in order:
        mult = float(cfg["scenes"].get(sid, 1) or 1)
        path, dur = build_scene(sid, rec[sid], vo[sid], mult, args.force)
        parts.append(path)
        total += dur
        print(f"{sid:16s} {mult:5g} {vo[sid]['duration']:6.2f}s {dur:6.2f}s")

    lst = os.path.join(CUTS, "concat.txt")
    with open(lst, "w") as fh:
        for p in parts:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", "-movflags", "+faststart", args.out])

    cfg["runtime_s"] = round(probe(args.out), 2)
    json.dump(cfg, open(SCENES_JSON, "w"), indent=1)
    print("-" * 40)
    print(f"{'TOTAL':16s} {'':5s} {'':7s} {cfg['runtime_s']:6.2f}s")
    print(f"\n-> {args.out}")
    print(f"   edit {os.path.relpath(SCENES_JSON, ROOT)} and run "
          f"video/rerender.py to change pacing without re-recording")


if __name__ == "__main__":
    main()
