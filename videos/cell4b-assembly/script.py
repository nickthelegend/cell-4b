"""The assembly script: one scene per component.

Every `where` string is read off cad/spec.py -- see the table printed by
`cad/audit.py` under seat/ and function/. Nothing here is invented.

    ../../../.venv-tts/bin/python script.py     # -> assets/vo/*.wav + script.json
"""
from __future__ import annotations

import json
import os
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
VO = os.path.join(ROOT, "assets", "vo")

SCENES = [
    dict(id="00_title", shot=None, kind="title",
         title="CELL-4B", sub="assembly, component by component",
         say="CELL 4B, assembled component by component. Every position here "
             "is read straight off the CAD."),
    dict(id="01_pi", shot="01_pi", part="Raspberry Pi 4B",
         where="(0, 33.6, 6.4)", how="4 x M2.5 into the 58 x 49 bosses",
         note="GPIO header faces the FRONT, toward the optics",
         say="Start with the Pi 4B. Four M2.5 screws into the fifty eight by "
             "forty nine bosses, with the GPIO header facing the front so the "
             "jumper runs to the optics stay short."),
    dict(id="02_switch", shot="02_switch", part="Cartridge switch",
         where="(14.0, -58.2, 2.4)", how="lever into the cartridge channel",
         note="ALSO the laser interlock — wire it in series with the laser supply",
         say="The cartridge switch goes beside the slot, its lever reaching "
             "into the channel. This is also the laser's hardware interlock, "
             "so wire it in series with the laser supply, not into a GPIO."),
    dict(id="03_baffle", shot="03_baffle", part="Slot baffle",
         where="6 mm behind the slot mouth", how="press fit, notch over the switch",
         note="stops 1 mm below the head skirt — together they are light-tight",
         say="The slot baffle presses in six millimetres behind the mouth. Its "
             "notch clears the switch, and it stops just under the head's "
             "skirt. Together those two make the slot light tight."),
    dict(id="04_leds", shot="04_leds", part="White LEDs + 940 nm IR",
         where="45°, 12.00 mm from the read spot",
         how="from OUTSIDE, into the three side bores",
         note="azimuth 45 and 225 for the whites, 135 for the IR",
         say="Three LEDs go into the head's side bores at forty five degrees. "
             "Whites opposed at forty five and two twenty five, the nine forty "
             "nanometre infrared at one thirty five. Push each until the dome "
             "bottoms at twelve millimetres."),
    dict(id="05_laser", shot="05_laser", part="650 nm laser",
         where="30°, azimuth 270, 22.00 mm",
         how="the one bore that exits the head's TOP",
         note="coherent source is mandatory — an LED makes no speckle at all",
         say="The six fifty nanometre laser sits at thirty degrees, azimuth two "
             "seventy. It is the only bore that leaves through the top face. "
             "It must be a laser: an LED has microns of coherence length and "
             "produces no speckle at all."),
    dict(id="06_camera", shot="06_camera", part="OV5647 camera",
         where="45°, azimuth 0, 20.00 mm", how="lens REMOVED, into its own pocket",
         note="96% of it sits inside the head — the pocket is cut for it",
         say="The camera goes in at forty five degrees, twenty millimetres from "
             "the read spot, with its lens removed. Almost all of it ends up "
             "inside the head, so the block has a pocket cut for it."),
    dict(id="07_head", shot="07_head", part="Optical head",
         where="3 lugs at r = 28", how="M2.5 down through each lug into the shell",
         note="fit every emitter BEFORE this goes down",
         say="Now the head drops onto its three lugs. They sit outside the optical "
             "body on purpose, so no screw ever crosses a bore. Fit every emitter before "
             "this point: once the deck is on, the LED bores are unreachable."),
    dict(id="08_ribbon", shot="08_ribbon", part="CSI ribbon",
         where="110 mm route", how="out the +X side, ON EDGE, then over the header",
         note="buy 150 mm — a 100 mm ribbon will not reach",
         say="Route the camera ribbon before the deck caps it. Out through the "
             "head's side, turned on edge to drop down the channel, then flat "
             "again and over the GPIO header. That run is a hundred and ten "
             "millimetres, so buy a hundred and fifty."),
    dict(id="09_tube", shot="09_tube", part="Aperture tube",
         where="(0, -32.4, 7.4)", how="flange UP into the counterbore",
         note="Ø3 × 6 — this is what fixes the 3 mm spot",
         say="The aperture tube goes in flange up. Three millimetres by six, "
             "and it is the single element that fixes the three millimetre spot "
             "inside the four millimetre well."),
    dict(id="10_as7341", shot="10_as7341", part="AS7341 — the flip-mount",
         where="chip DOWN at 35.8 · chip UP at 37.4",
         how="one board, one pad, two orientations",
         note="chip down reads the cartridge; chip up reads a fingertip",
         say="Here is the trick. The same AS7341, the same four screws, mounted "
             "either way up. Chip down reads the cartridge below. Chip up reads "
             "a fingertip above. The carrier is symmetric, so one board serves "
             "both tiers."),
    dict(id="11_touch", shot="11_touch", part="Touch collar",
         where="45° UP, azimuth 0 and 180", how="white + IR aimed at the fingertip",
         note="same 45°/12 mm geometry as the blood tier, pointed the other way",
         say="For the touch tier, the collar carries a white and an infrared LED "
             "at the same forty five degrees and twelve millimetres, aimed up at "
             "the finger instead of down at the cartridge."),
    dict(id="12_cartridge", shot="12_cartridge", part="Cartridge",
         where="slides to STOP2, 42.1 mm in", how="well lands on the read spot",
         note="8.9 mm stays proud — that is what you pull it out by",
         say="The cartridge slides in to stop two, forty two point one "
             "millimetres, which puts its well exactly on the read spot. Eight "
             "point nine millimetres stays proud, and that is what you pull a "
             "blood contact part back out by."),
    dict(id="13_close", shot="13_close", part="OLED, windows, upper shell",
         where="ceiling", how="Ø10 window goes in from BELOW",
         note="the ring port is a through-hole — one axis, finger above, cartridge below",
         say="Finally the OLED on its posts, the ten millimetre window into its "
             "rebate from underneath, and the upper shell. The ring port is a "
             "through hole, so one optical axis serves the finger above and the "
             "cartridge below."),
    dict(id="14_exploded", shot="14_exploded", kind="outro",
         title="404 checks · 0 failed",
         sub="github.com/nickthelegend/cell-4b",
         say="Thirteen printed parts, four hundred and four geometry "
             "checks, and the build refuses to write an S T L if any of them "
             "fail. Everything is on GitHub."),
]

VOICE, SR = "af_heart", 24000


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0.0)


def main():
    os.makedirs(VO, exist_ok=True)
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="a")

    out = []
    for sc in SCENES:
        path = os.path.join(VO, f"{sc['id']}.wav")
        chunks = [np.asarray(a.detach().cpu().numpy() if hasattr(a, "detach") else a,
                             dtype="float32")
                  for _g, _p, a in pipe(sc["say"], voice=VOICE, speed=1.0)]
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        pad = np.zeros(int(0.30 * SR), dtype=audio.dtype)
        sf.write(path, np.concatenate([pad, audio, pad]), SR)
        d = probe(path)
        rec = dict(sc)
        rec["wav"] = f"assets/vo/{sc['id']}.wav"
        rec["duration"] = round(d, 3)
        out.append(rec)
        print(f"  {sc['id']:14s} {d:6.2f}s  {sc.get('part', sc.get('title',''))}")

    json.dump(out, open(os.path.join(ROOT, "script.json"), "w"), indent=1)
    print(f"\n{len(out)} scenes, {sum(r['duration'] for r in out):.1f}s of narration")


if __name__ == "__main__":
    main()
