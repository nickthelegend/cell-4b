# CELL-4B demo — scene map

One scene per beat. Each records to its **own** video file, so any single scene
can be re-recorded or re-timed without touching the rest.

Recorded by driving the real viewer in a headless Chromium via Playwright's
`recordVideo`. Only the browser viewport is captured — nothing touches the
desktop. Every click and dropdown change is a real interaction against the real
`out/manifest.json` and the real GLBs; no staged screenshots, no faked numbers.

Viewport 1440 × 900, 30 fps.

| # | id | What happens | Narration beat |
|---|---|---|---|
| 01 | `intro` | Animated title card built in the page: CELL-4B wordmark draws in, subtitle fades up | What this is |
| 02 | `problem` | Assembled view, slow orbit | A Pi 4B enclosure for a blood-reading hardware wallet |
| 03 | `why_4b` | Assembled view, camera pushes toward the Pi through the shell | Why a 4B and not upstream's Pi Zero |
| 04 | `finding` | Sidebar note about the 28 mm standoff highlighted, then the optics panel | The 9 mm standoff cannot be built |
| 05 | `cutaway` | Switch to Cutaway, orbit, then hide the head to reveal the camera | Where the camera actually is |
| 06 | `ribbon` | Cutaway with the CSI ribbon isolated, orbit along its route | The ribbon had nowhere to go |
| 07 | `clearance` | Scroll the placement + clearance panels | Every component measured |
| 08 | `steps` | Step through build steps 1 → 10 in the dropdown | How it goes together |
| 09 | `explode` | Exploded view, slow orbit | The whole stack |
| 10 | `plates` | Plate 1 → Plate 4 | What you actually print |
| 11 | `audit` | Badge close-up, then the checks summary | 309 checks, 0 failed |
| 12 | `outro` | Animated end card: repo URL wipes in | Where to get it |

## Rules

- **No staged results.** The audit badge shows whatever the manifest says. If a
  check fails, the video shows it failing.
- **No console errors in frame.** The recorder asserts a clean console per
  scene and fails the run otherwise.
- **Pacing is driven by audio.** Each scene's clip is retimed to its measured
  Kokoro duration — speed-ramped if the footage runs long, last frame held if
  it runs short. Durations are measured from the generated WAV, never estimated.
- **Length first, speed after.** The full cut is assembled at 1×. `scenes.json`
  then carries a per-scene multiplier so runtime can be cut without cutting
  content: `python3 video/rerender.py`.
