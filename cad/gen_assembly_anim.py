"""Emit the 3-D assembly animation payload: one GLB + an insertion manifest.

    ../.venv/bin/python cad/gen_assembly_anim.py

Two things the ordinary build does not produce:

  * every part as its OWN node -- the three LEDs are one mesh in the viewer,
    but they go into three different bores at three different times;
  * an INSERTION VECTOR per part, so the animation moves each one along the
    axis it is genuinely fitted along. An LED slides down its own 45 deg bore,
    the head drops on +Z, the cartridge slides in from the front. That is the
    difference between an assembly demo and parts fading in.

Vectors come from spec.py, so what the animation shows is how the part is
actually installed, not a guess that looks plausible.
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bodies as BD
import mocks as M
import partlib as pl
import parts as P
import spec as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "glb")


def bore_dir(tilt_deg, az_deg):
    """Unit vector pointing OUT along a bore axis -- the way the part comes in."""
    t, a = math.radians(tilt_deg), math.radians(az_deg)
    return [math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t)]


def main():
    placed = P.assembly()
    nodes, steps = [], []

    def add(name, mesh, colour, vec, dist, step, label, detail, alpha=1.0):
        nodes.append((name, mesh, colour, alpha))
        steps.append({"node": name, "step": step, "label": label,
                      "detail": detail,
                      "vec": vec, "dist": dist})

    UP, FRONT = [0, 0, 1], [0, -1, 0]

    add("shell_lower", placed["shell_lower"], "#3A3F46", UP, 0, 0,
        "Lower shell", "the base everything else lands on")
    add("mock_pi4b", M.pi4b(), "#1E6B4E", UP, 42, 1,
        "Raspberry Pi 4B", "4 x M2.5 into the 58 x 49 bosses")
    add("mock_switch", M.switch(), "#6B6B6B", UP, 26, 2,
        "Cartridge switch", "lever into the channel; also the laser interlock")
    add("slot_baffle", placed["slot_baffle"], "#2E3238", UP, 26, 3,
        "Slot baffle", "6 mm behind the mouth, notched for the switch")

    # the three LEDs, each on its own bore, inserted from outside
    for nm, az, label in (("led1", S.AZ_LED1, "White LED #1"),
                          ("led2", S.AZ_LED2, "White LED #2"),
                          ("ir", S.AZ_IR, "940 nm IR LED")):
        add(f"mock_{nm}", BD.led_body(nm), "#E8E4D0",
            bore_dir(S.LED_ANGLE, az), 46, 4,
            label, f"45 deg bore, azimuth {az:.0f}, seats at 12.00 mm")

    add("mock_laser", BD.laser_body(), "#B04A4A",
        bore_dir(S.LASER_ANGLE, S.AZ_LASER), 46, 5,
        "650 nm laser", "30 deg, azimuth 270 -- exits the head's top")
    add("mock_camera", BD.camera_body(), "#3B4A5A",
        bore_dir(S.CAMERA_ANGLE, S.AZ_CAMERA), 52, 6,
        "OV5647 camera", "45 deg, 20.00 mm, lens removed")
    add("optical_head", placed["optical_head"], "#2E3238", UP, 60, 7,
        "Optical head", "down onto its three lugs -- 115, 180, 305 deg")
    add("mock_csi_ribbon", M.csi_ribbon(), "#C8A24A", UP, 34, 8,
        "CSI ribbon", "110 mm: out +X, on edge, over the header")
    add("aperture_tube", placed["aperture_tube"], "#2E3238", UP, 30, 9,
        "Aperture tube", "flange up -- this fixes the 3 mm spot")
    add("sensor_deck", placed["sensor_deck"], "#2E3238", UP, 34, 10,
        "Sensor deck", "three ears, one M2.5 each -- none through the middle")
    add("mock_as7341", M.as7341(), "#2B6CB0", UP, 30, 11,
        "AS7341", "4 x M2 at 25.5 x 18.0 -- flat deck, no screw heads")
    add("sensor_carrier", placed["sensor_carrier"], "#2E3238", UP, 26, 12,
        "Flip-mount carrier", "symmetric -- clamps the board either way up")
    add("touch_collar", placed["touch_collar"], "#3A4048", UP, 30, 13,
        "Touch collar", "carries the touch LEDs, aimed UP")
    add("mock_touch_leds", M.touch_leds(), "#E8E4D0", UP, 30, 14,
        "Touch LEDs", "white + IR at 45 deg / 12 mm, at the fingertip")
    add("mock_cartridge", M.cartridge_in_place(), "#EDF1F5", FRONT, 62, 15,
        "Cartridge", "slides to STOP2 -- well on the read spot")
    add("mock_oled", M.oled(), "#1A2A3A", UP, 30, 16,
        "1.3in OLED", "four posts under the ceiling")
    add("mock_touch_window", M.touch_window(), "#9FD8E8", UP, 24, 17,
        "Ring window", "into its rebate from BELOW", 0.5)
    add("shell_upper", placed["shell_upper"], "#3A3F46", UP, 74, 18,
        "Upper shell", "closes the lap joint")
    add("oled_bezel", placed["oled_bezel"], "#2E3238", UP, 26, 19,
        "OLED bezel", "masks the window to the active area")

    os.makedirs(OUT, exist_ok=True)
    pl.glb_write(os.path.join(OUT, "assembly_anim.glb"),
                 [(n, m, c, a) for n, m, c, a in nodes])

    man = {"steps": steps,
           "readSpot": [S.RS_X, S.RS_Y, S.Z_SAMPLE],
           "env": [S.ENV_X, S.ENV_Y, S.ENV_Z]}
    json.dump(man, open(os.path.join(OUT, "assembly.json"), "w"), indent=1)
    print(f"assembly_anim.glb  {len(nodes)} nodes")
    for s in steps:
        print(f"  {s['step']:2d}  {s['node']:20s} "
              f"in along ({s['vec'][0]:+.2f},{s['vec'][1]:+.2f},{s['vec'][2]:+.2f})"
              f" x {s['dist']:.0f} mm   {s['label']}")


if __name__ == "__main__":
    main()
