"""Kokoro TTS: one narration WAV per scene, with its REAL measured duration.

    python3 video/tts.py

Durations are read back off the generated audio with ffprobe. Nothing is
estimated from word counts -- the whole point is that each scene's footage gets
paced to the audio that actually exists.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenes import SCENES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "video", "out")
VO = os.path.join(OUT, "vo")

VOICE = "af_heart"      # Kokoro's American-English default
SPEED = 1.0
SR = 24000


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0.0)


def main():
    os.makedirs(VO, exist_ok=True)
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipe = KPipeline(lang_code="a")
    meta = {}
    for sc in SCENES:
        sid, text = sc["id"], sc["say"]
        path = os.path.join(VO, f"{sid}.wav")
        # Kokoro yields torch tensors; soundfile wants numpy
        chunks = [np.asarray(a.detach().cpu().numpy() if hasattr(a, "detach")
                             else a, dtype="float32")
                  for _gs, _ps, a in pipe(text, voice=VOICE, speed=SPEED)]
        if not chunks:
            raise SystemExit(f"kokoro produced no audio for {sid}")
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        # a breath either side so cuts do not clip the first phoneme
        pad = np.zeros(int(0.25 * SR), dtype=audio.dtype)
        audio = np.concatenate([pad, audio, pad])
        sf.write(path, audio, SR)
        d = probe(path)
        meta[sid] = {"wav": f"vo/{sid}.wav", "duration": round(d, 3),
                     "text": text}
        print(f"  {sid:14s} {d:6.2f}s  {text[:58]}...")

    json.dump(meta, open(os.path.join(OUT, "vo.json"), "w"), indent=1)
    total = sum(v["duration"] for v in meta.values())
    print(f"\n{len(meta)} lines, {total:.1f}s of narration -> {VO}")


if __name__ == "__main__":
    main()
