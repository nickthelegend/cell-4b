"""Emit index.html from script.json, so scene timing cannot drift from the VO.

    python3 build_composition.py

Every scene's duration comes from its MEASURED narration length. The callout
text comes from the same records the narration was generated from, which were
themselves read off cad/spec.py -- so a coordinate on screen, the sentence
spoken over it, and the CAD all have one source.
"""
from __future__ import annotations

import html
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PAD = 0.45           # breath after each line
FPS = 30

BG, INK, DIM, ACCENT = "#0b0d10", "#eef2f7", "#9aa4b2", "#ff9d3c"


def esc(s):
    return html.escape(s or "", quote=True)


# A CSS id selector may not start with a digit -- "#00_title-big" throws
# in querySelectorAll. Every DOM id gets an "s" prefix.
def dom_id(sc):
    return "s" + sc["id"]


def scene_html(sc, i, start, dur, n):
    sid = dom_id(sc)
    kind = sc.get("kind", "step")
    img = (f'<img class="shot" src="{sc["shot"] and f"assets/steps/{sc['shot']}.png"}" alt="">'
           if sc.get("shot") else "")
    if kind in ("title", "outro"):
        inner = f'''
      <div class="card-mid">
        <div class="big" id="{sid}-big">{esc(sc["title"])}</div>
        <div class="rule" id="{sid}-rule"></div>
        <div class="sub" id="{sid}-sub">{esc(sc["sub"])}</div>
      </div>'''
    else:
        step = f"{i:02d} / {n:02d}"
        inner = f'''
      <div class="counter" id="{sid}-count">{step}</div>
      <div class="callout" id="{sid}-callout">
        <div class="part">{esc(sc["part"])}</div>
        <div class="kv"><span class="k">WHERE</span><span class="v mono">{esc(sc["where"])}</span></div>
        <div class="kv"><span class="k">HOW</span><span class="v">{esc(sc["how"])}</span></div>
        <div class="note">{esc(sc["note"])}</div>
      </div>'''
    return f'''    <div class="clip scene" id="{sid}" data-start="{start:.3f}" data-duration="{dur:.3f}">
      <div class="shotwrap" id="{sid}-shot">{img}</div>
      <div class="vig"></div>{inner}
    </div>
'''


def main():
    scenes = json.load(open(os.path.join(ROOT, "script.json")))
    steps = [s for s in scenes if s.get("kind", "step") == "step"]
    n = len(steps)

    t, timed, audio, tl = 0.0, [], [], []
    step_i = 0
    for sc in scenes:
        dur = sc["duration"] + PAD
        if sc.get("kind", "step") == "step":
            step_i += 1
        timed.append(scene_html(sc, step_i, t, dur, n))
        audio.append(f'    <audio id="vo-{dom_id(sc)}" src="{sc["wav"]}" '
                     f'data-start="{t:.3f}"></audio>')
        tl.append(build_tl(sc, t, dur))
        t += dur

    total = round(t, 3)
    doc = f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: {BG}; }}
      body {{ font-family: "Inter", ui-sans-serif, system-ui, sans-serif; color: {INK}; }}
      .mono {{ font-family: "JetBrains Mono", ui-monospace, monospace; }}

      .scene {{ position: absolute; inset: 0; width: 1920px; height: 1080px;
                background: {BG}; overflow: hidden; }}
      .shotwrap {{ position: absolute; inset: 0; width: 1920px; height: 1080px; }}
      .shot {{ width: 1920px; height: 1080px; object-fit: cover; display: block; }}
      .vig {{ position: absolute; inset: 0;
              background: radial-gradient(ellipse at 62% 45%,
                          rgba(0,0,0,0) 38%, rgba(0,0,0,.55) 100%); }}

      .counter {{ position: absolute; top: 54px; right: 64px; font-size: 22px;
                  letter-spacing: .18em; color: {DIM};
                  font-family: "JetBrains Mono", ui-monospace, monospace; }}

      .callout {{ position: absolute; left: 84px; bottom: 92px; width: 760px;
                  padding: 34px 38px 30px; border-radius: 16px;
                  background: rgba(9,11,14,.82);
                  border: 1px solid rgba(255,255,255,.10);
                  border-left: 4px solid {ACCENT}; }}
      .part {{ font-size: 44px; font-weight: 650; letter-spacing: -.02em;
               margin-bottom: 20px; line-height: 1.1; }}
      .kv {{ display: flex; align-items: baseline; gap: 18px; margin-bottom: 10px; }}
      .k {{ flex: none; width: 88px; font-size: 15px; letter-spacing: .16em;
            color: {DIM}; }}
      .v {{ font-size: 26px; line-height: 1.35; }}
      .v.mono {{ color: {ACCENT}; }}
      .note {{ margin-top: 18px; padding-top: 16px; font-size: 20px;
               line-height: 1.45; color: {DIM};
               border-top: 1px solid rgba(255,255,255,.10); }}

      .card-mid {{ position: absolute; inset: 0; display: flex;
                   flex-direction: column; align-items: center;
                   justify-content: center; text-align: center; }}
      .big {{ font-size: 104px; font-weight: 700; letter-spacing: -.035em; }}
      .rule {{ height: 3px; width: 420px; background: {ACCENT}; margin: 26px 0 22px; }}
      .sub {{ font-size: 30px; color: {DIM}; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0"
         data-duration="{total}" data-width="1920" data-height="1080">
{''.join(timed)}
{chr(10).join(audio)}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join(tl)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
'''
    open(os.path.join(ROOT, "index.html"), "w").write(doc)
    print(f"index.html — {len(scenes)} scenes, {total:.1f}s "
          f"({total/60:.1f} min), {int(total*FPS)} frames")


def build_tl(sc, t, dur):
    """Seek-safe motion only: transforms and opacity, absolute-positioned."""
    sid = dom_id(sc)
    L = []
    a = f"{t:.3f}"
    if sc.get("shot"):
        # slow push-in on the shot wrapper, never on the timed clip itself
        L.append(f'      tl.fromTo("#{sid}-shot", {{ scale: 1.0, xPercent: 0 }},'
                 f' {{ scale: 1.06, xPercent: -1, duration: {dur:.3f},'
                 f' ease: "none" }}, {a});')
    if sc.get("kind", "step") == "step":
        L.append(f'      tl.fromTo("#{sid}-callout", {{ autoAlpha: 0, y: 26 }},'
                 f' {{ autoAlpha: 1, y: 0, duration: 0.55,'
                 f' ease: "power3.out" }}, {a});')
        L.append(f'      tl.fromTo("#{sid}-count", {{ autoAlpha: 0 }},'
                 f' {{ autoAlpha: 1, duration: 0.4 }}, {a});')
        # lint: an exit fade that lands on the clip boundary needs a hard kill,
        # or a non-linear seek can land past the fade holding stale visibility
        L.append(f'      tl.to("#{sid}-callout", {{ autoAlpha: 0, duration: 0.35 }},'
                 f' {t + dur - 0.35:.3f});')
        L.append(f'      tl.set("#{sid}-callout", {{ autoAlpha: 0 }},'
                 f' {t + dur:.3f});')
        L.append(f'      tl.set("#{sid}-count", {{ autoAlpha: 0 }},'
                 f' {t + dur:.3f});')
    else:
        L.append(f'      tl.fromTo("#{sid}-big", {{ autoAlpha: 0, y: 34 }},'
                 f' {{ autoAlpha: 1, y: 0, duration: 0.8,'
                 f' ease: "power3.out" }}, {a});')
        L.append(f'      tl.fromTo("#{sid}-rule", {{ scaleX: 0 }},'
                 f' {{ scaleX: 1, duration: 0.7, ease: "power3.inOut" }},'
                 f' {t + 0.55:.3f});')
        L.append(f'      tl.fromTo("#{sid}-sub", {{ autoAlpha: 0, y: 18 }},'
                 f' {{ autoAlpha: 1, y: 0, duration: 0.6,'
                 f' ease: "power3.out" }}, {t + 0.9:.3f});')
    return chr(10).join(L)


if __name__ == "__main__":
    main()
