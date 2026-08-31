"""Re-cut the film after editing per-scene speeds. No re-recording.

    # 1. edit video/scenes.json, e.g. "08_steps": 3
    # 2.
    python3 video/rerender.py
    python3 video/rerender.py --target 90     # suggest multipliers for 90 s

`--target` does not cut content. It proposes a multiplier per scene, weighted
so long scenes absorb most of the compression and short ones stay watchable,
then writes them into scenes.json for you to accept or adjust by hand.

Audio is retimed with atempo, so speeding a scene up keeps the narrator's
pitch natural rather than making them a chipmunk.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID = os.path.join(ROOT, "video")
SCENES_JSON = os.path.join(VID, "scenes.json")
VO_JSON = os.path.join(VID, "out", "vo.json")

MAX_MULT = 6.0          # past this the narration is unintelligible
MIN_SCENE_S = 2.0       # never squeeze a scene below this


def suggest(target, vo, cfg):
    """Pick per-scene multipliers that hit `target` without dropping scenes."""
    ids = list(cfg["scenes"])
    base = {s: vo[s]["duration"] for s in ids}
    total = sum(base.values())
    if target >= total:
        print(f"target {target:.0f}s is already >= the {total:.0f}s cut; "
              f"leaving everything at 1x")
        return {s: 1 for s in ids}

    # Uniform speed-up first, then relax any scene that would fall under the
    # floor and push the difference onto the scenes that can still take it.
    need = total / target
    mult = {s: min(MAX_MULT, need) for s in ids}
    for _ in range(40):
        out = sum(base[s] / mult[s] for s in ids)
        if abs(out - target) < 0.4:
            break
        flex = [s for s in ids
                if base[s] / mult[s] > MIN_SCENE_S and mult[s] < MAX_MULT]
        if not flex:
            break
        k = (out - target) / max(1e-6, sum(base[s] / mult[s] for s in flex))
        for s in flex:
            mult[s] = max(1.0, min(MAX_MULT, mult[s] * (1 + k)))
    return {s: round(mult[s], 2) for s in ids}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float,
                    help="desired runtime in seconds; writes suggested "
                         "multipliers into scenes.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(SCENES_JSON):
        raise SystemExit("run video/assemble.py once first")
    cfg = json.load(open(SCENES_JSON))

    if args.target:
        vo = json.load(open(VO_JSON))
        cfg["scenes"] = suggest(args.target, vo, cfg)
        cfg["target_s"] = args.target
        json.dump(cfg, open(SCENES_JSON, "w"), indent=1)
        print(f"wrote multipliers for a {args.target:.0f}s target:")
        for s, m in cfg["scenes"].items():
            print(f"   {s:16s} {m:>5}x  "
                  f"{vo[s]['duration']:5.1f}s -> {vo[s]['duration']/m:5.1f}s")
        print()

    cmd = [sys.executable, os.path.join(VID, "assemble.py")]
    if args.force:
        cmd.append("--force")
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
