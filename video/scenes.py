"""Scene definitions: narration text + the actions that drive the viewer.

Each scene is a dict:
    id       file-safe name
    say      the single narration line (one line -> one subtitle cue)
    actions  list of (verb, args) executed against the live page
    min_s    floor on recorded length, so short narration still gets footage

Verbs the recorder understands:
    model   <label>      pick a model from the dropdown, wait for it to load
    orbit   <deg> <s>    drag-orbit the canvas by N degrees over N seconds
    zoom    <notches>    scroll-zoom the canvas
    hide    <name...>    untick parts by mesh name
    show    <name...>    tick them back
    scroll  <px>         scroll the sidebar
    hold    <s>          just record
    title   <a> <b>      run the in-page animated card
"""

SCENES = [
    dict(
        id="01_intro", min_s=5.0,
        say="CELL 4B is a Raspberry Pi 4B enclosure for CELL, "
            "an open source hardware wallet that reads a drop of blood.",
        actions=[("title", ["CELL-4B", "Pi 4B enclosure for z0r0z/cell"]),
                 ("hold", [4.0])],
    ),
    dict(
        id="02_problem", min_s=7.0,
        say="Upstream's shells are hard coded to a Pi Zero bay, and the Pi Zero "
            "2 W is unobtainable in India. So this rebuilds the same instrument "
            "around a board you can actually buy.",
        actions=[("model", ["Assembled + components"]), ("hold", [1.0]),
                 ("orbit", [110, 6.0])],
    ),
    dict(
        id="03_why_4b", min_s=6.0,
        say="Everything upstream calls optics is preserved exactly. Everything "
            "it calls derived — walls, bosses, bays — is regenerated from "
            "Python.",
        actions=[("model", ["Assembled (printed only)"]), ("hold", [0.8]),
                 ("zoom", [3]), ("orbit", [70, 4.5])],
    ),
    dict(
        id="04_finding", min_s=8.0,
        say="Building it surfaced a blocking defect upstream. A nine millimetre "
            "sensor standoff cannot coexist with five millimetre LEDs at forty "
            "five degrees. The longest LED body that fits is zero point seven "
            "three millimetres.",
        actions=[("model", ["Assembled + components"]),
                 ("scroll", [900]), ("hold", [5.0])],
    ),
    dict(
        id="05_cutaway", min_s=9.0,
        say="The camera is invisible from outside because it sits inside the "
            "optical head, fourteen millimetres from the read spot. Hiding the "
            "head reveals it.",
        actions=[("scroll", [0]), ("model", ["Cutaway — inside the optical head"]),
                 ("hold", [1.0]), ("orbit", [60, 3.0]),
                 ("hide", ["optical_head", "sensor_deck"]), ("hold", [1.5]),
                 ("orbit", [70, 3.5])],
    ),
    dict(
        id="06_ribbon", min_s=8.0,
        say="Its ribbon had nowhere to go. Nothing in the design accounted for "
            "it. The route is now a hundred and ten millimetres, on edge "
            "through a twelve millimetre gap, and every millimetre is checked.",
        # each scene records in its own browser context, so it must build its
        # own state. `prep` runs before the clock starts and is trimmed off.
        prep=[("model", ["Cutaway — inside the optical head"]),
              ("hide", ["optical_head", "sensor_deck"])],
        actions=[("hide", ["mock_pi4b"]), ("hold", [1.2]),
                 ("orbit", [90, 5.0]), ("show", ["mock_pi4b"]), ("hold", [1.5])],
    ),
    dict(
        id="07_clearance", min_s=8.0,
        # keep this count in step with manifest.json -- it is on screen
        say="Every component is measured surface to surface against every other. "
            "Sixty pairs, with designed contacts told apart from collisions "
            "by penetration depth.",
        actions=[("model", ["Assembled + components"]),
                 ("scroll", [620]), ("hold", [3.0]), ("scroll", [980]),
                 ("hold", [3.5])],
    ),
    dict(
        id="08_steps", min_s=16.0,
        say="It assembles in ten steps. Emitters go into the head before it "
            "closes, the ribbon is routed before the deck caps it, and the "
            "cartridge slides in to stop two with its well on the read spot.",
        actions=[("scroll", [0])] +
                [("model", [f"Build step {i} - {t}"]) for i, t in [
                    (1, "Pi 4B on its bosses"), (2, "slot baffle"),
                    (3, "emitters into the head"), (4, "optical head down"),
                    (5, "CSI ribbon routed"), (6, "aperture tube"),
                    (7, "sensor deck"), (8, "AS7341 + retainer"),
                    (9, "cartridge in to stop 2"),
                    (10, "upper shell, OLED, windows")]],
    ),
    dict(
        id="09_explode", min_s=8.0,
        say="Exploded, each component rides with the part it mounts to, so the "
            "build order reads straight off it.",
        actions=[("model", ["Exploded"]), ("hold", [1.0]), ("orbit", [120, 6.0])],
    ),
    dict(
        id="10_plates", min_s=9.0,
        say="Four plates, all inside a P1S bed. Shells, optics, and twenty "
            "cartridges printed from one white spool in one session, because "
            "that patch is a photometric reference.",
        actions=[("model", ["Plate 1 - shell lower"]), ("hold", [1.6]),
                 ("model", ["Plate 2 - shell upper"]), ("hold", [1.6]),
                 ("model", ["Plate 3 - optics + small parts"]), ("hold", [1.8]),
                 ("model", ["Plate 4 - cartridges"]), ("hold", [2.4])],
    ),
    dict(
        id="11_audit", min_s=6.0,
        say="Three hundred and nine checks. The build refuses to write an STL "
            "if any of them fail.",
        actions=[("model", ["Assembled + components"]), ("hold", [1.2]),
                 ("zoom", [2]), ("hold", [3.0])],
    ),
    dict(
        id="12_outro", min_s=5.0,
        say="Parametric source, printable STLs and the findings are on GitHub, "
            "at nickthelegend slash cell dash 4B.",
        actions=[("title", ["github.com/nickthelegend/cell-4b",
                            "309 checks · 12 parts · 4 plates"]),
                 ("hold", [4.0])],
    ),
]
