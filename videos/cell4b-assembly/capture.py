"""Capture one framed still per assembly step, from the live viewer.

    ../../../.venv/bin/python capture.py

Playwright drives the real viewer headless, so every frame is the real CAD
geometry at the real coordinates -- nothing here is drawn by hand. Chrome
(sidebar, badge, hint) is hidden so the composition can put its own callouts
over clean renders.

Each SHOT names the build-step model, an orbit, and which parts to hide so the
component being fitted is actually visible rather than buried in a shell.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "assets", "steps")
VIEW = "http://localhost:8731/viewer/index.html"
W, H = 1920, 1080

# (id, model label, azimuth, elevation, distance mm, target xyz, hide[])
# Targets are real coordinates out of cad/spec.py: the read spot is
# (0, -32.4), the optical head runs 6.2..33.4, the Pi sits around (0, +33.6).
SPOT = [0, -32.4, 16]          # inside the optical head
DECK = [0, -32.4, 40]          # sensor deck / flip-mount
PI   = [0, 33.6, 14]           # over the board
WHOLE = [0, -6, 26]            # the assembly as a whole

CUT = "Cutaway \u2014 inside the optical head"

SHOTS = [
    # id, model, azimuth, elevation, distance mm, target, hide[]
    ("01_pi",        "Build step 1 - Pi 4B on its bosses",        -60, 40, 235, WHOLE, []),
    ("02_switch",    "Build step 1 - Pi 4B on its bosses",       -105, 26,  70, [14, -55, 6], ["mock_pi4b"]),
    ("03_baffle",    "Build step 2 - slot baffle",               -105, 26,  85, [0, -54, 7], ["mock_pi4b"]),
    # the cutaway keeps the head translucent, so the emitters read INSIDE it
    ("04_leds",      CUT,  -45, 20,  78, SPOT, ["mock_pi4b", "mock_laser", "mock_camera"]),
    ("05_laser",     CUT,  -95, 16,  85, [0, -32.4, 22], ["mock_pi4b", "mock_leds", "mock_camera"]),
    ("06_camera",    CUT,   20, 14,  85, [4, -32.4, 18], ["mock_pi4b", "mock_leds", "mock_laser"]),
    ("07_head",      "Build step 4 - optical head down",          -60, 30, 135, SPOT, []),
    ("08_ribbon",    CUT,  -25, 42, 175, [8, -8, 22], ["optical_head", "sensor_deck"]),
    ("09_tube",      CUT,  -60, 16,  72, [0, -32.4, 11], ["mock_pi4b", "mock_leds", "mock_laser", "mock_camera"]),
    ("10_as7341",    "Build step 8 - AS7341 on the flip-mount",   -60, 22,  95, DECK, ["shell_lower"]),
    ("11_touch",     "Build step 9 - touch collar + its LEDs",    -60, 18,  95, [0, -32.4, 48], ["shell_lower"]),
    ("12_cartridge", "Build step 10 - cartridge in to stop 2",   -112, 16, 175, [0, -52, 8], []),
    ("13_close",     "Build step 11 - upper shell, OLED, windows", -60, 40, 245, WHOLE, []),
    ("14_exploded",  "Exploded",                                  -52, 16, 430, [0, -16, 120], []),
]


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, channel="chromium",
                               args=["--enable-unsafe-swiftshader"])
        page = b.new_context(viewport={"width": W, "height": H},
                             device_scale_factor=1).new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(VIEW, wait_until="load")
        page.wait_for_function("() => window.__hf && window.__hf.ready()",
                               timeout=40000)

        for sid, label, az, el, dist, target, hide in SHOTS:
            page.select_option("#model", label=label)
            page.wait_for_function(
                "() => document.querySelectorAll('#parts .row').length > 0",
                timeout=40000)
            page.wait_for_timeout(1200)
            if hide:
                page.evaluate("ns => window.__hf.hide(ns)", hide)
            page.evaluate("a => window.__hf.chrome(false)", None)
            page.evaluate("a => window.__hf.view(a[0], a[1], a[2], a[3])",
                          [az, el, dist, target])
            page.wait_for_timeout(700)
            path = os.path.join(OUT, f"{sid}.png")
            page.locator("canvas").screenshot(path=path)
            page.evaluate("a => window.__hf.chrome(true)", None)
            meta[sid] = {"file": f"assets/steps/{sid}.png", "model": label}
            print(f"  {sid:14s} {label}")

        b.close()
    if errs:
        raise SystemExit(f"page errors during capture: {errs[:2]}")
    json.dump(meta, open(os.path.join(ROOT, "shots.json"), "w"), indent=1)
    print(f"\n{len(meta)} stills -> {OUT}")


if __name__ == "__main__":
    main()
