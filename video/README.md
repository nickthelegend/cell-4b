# CELL-4B demo video

```bash
python3 -m http.server 8731                 # serve the viewer
../.venv/bin/python     video/record.py     # 12 scenes -> video/out/raw/*.webm
../.venv-tts/bin/python video/tts.py        # 12 Kokoro lines -> video/out/vo/*.wav
../.venv/bin/python     video/assemble.py   # -> video/out/cell4b-demo.mp4
```

`recording.md` is the scene map. `scenes.py` holds each scene's narration line
and the actions that drive the viewer.

## How it records

Playwright drives a **headless Chromium** and captures with the browser
context's own `recordVideo`. Only the browser viewport is written to a file —
the desktop is never touched and the machine stays usable while it runs. Every
click, dropdown change and orbit is a real interaction against the real
`out/manifest.json` and the real GLBs.

**One browser context per scene, so one video file per scene.** Any single
scene can be re-recorded without disturbing the others:

```bash
../.venv/bin/python video/record.py --only 05_cutaway
```

Two guards keep the footage honest:

- the recorder **fails the run** if any console error appears while recording,
  so nothing ships with errors in frame;
- nothing is staged — the audit badge shows whatever the manifest says. When
  the on-screen pair count changed from 52 to 60, the narration was rewritten
  to match rather than the other way round.

## Pacing

Each scene is cut to its **measured** narration length — read back off the
generated WAV with ffprobe, never estimated. Footage that runs long is
speed-ramped; footage that runs short holds its last frame. No scene is ever
cut short of its line.

## Changing runtime without cutting content

`scenes.json` carries a speed multiplier per scene.

```bash
python3 video/rerender.py                 # apply whatever is in scenes.json
python3 video/rerender.py --target 75     # pick multipliers to hit 75 s
```

Video is retimed with `setpts`, audio with `atempo`, so pitch stays natural.
Scene mp4s are cached and keyed on their multiplier — changing one scene
re-encodes only that scene. Nothing is re-recorded and no content is dropped.

## Subtitles

One narration line = one cue. The caption is rendered **in the page** rather
than burned by ffmpeg: this ffmpeg build has no `drawtext` or `subtitles`
filter, and the browser gives proper text shaping for free. Because the cue is
in the footage and static, retiming can never desync it.

## Two virtualenvs

Kokoro needs spacy, which has no wheels for Python 3.14, so TTS lives in its
own 3.10 environment:

```bash
python3.10 -m venv .venv-tts && .venv-tts/bin/pip install kokoro soundfile
```
