"""The 1.3" I2C OLED, on the same bus as the sensor.

spec.py calls it "SH1106/SSD1306" because 1.3 inch 4-pin modules ship as
either and the silkscreen often lies. So the driver is probed rather than
configured: SH1106 first (more common at 1.3 inch), SSD1306 as the fallback.
Guessing wrong gives you a display that is shifted a few columns or blank, not
an error, which is a miserable thing to debug at 1 a.m.

Everything here degrades to no-op if the panel is absent. A missing display
must never stop a measurement -- the numbers are the product, the screen is a
convenience.
"""
from __future__ import annotations

ADDR = 0x3C           # 0x3D on a few modules; both are probed


class Display:
    def __init__(self, width: int = 128, height: int = 64):
        self.dev = None
        self.width, self.height = width, height
        self._font = None
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import sh1106, ssd1306
            from PIL import ImageFont
            last = None
            for addr in (ADDR, 0x3D):
                for drv in (sh1106, ssd1306):
                    try:
                        self.dev = drv(i2c(port=1, address=addr),
                                       width=width, height=height)
                        break
                    except Exception as e:
                        last = e
                if self.dev:
                    break
            if self.dev is None:
                raise last or RuntimeError("no OLED found")
            self._font = ImageFont.load_default()
        except Exception as e:
            self.error = str(e)

    @property
    def ok(self) -> bool:
        return self.dev is not None

    def lines(self, *rows: str) -> None:
        """Draw up to 5 short rows. Silently does nothing with no panel."""
        if not self.ok:
            return
        from luma.core.render import canvas
        with canvas(self.dev) as d:
            for i, text in enumerate(rows[:5]):
                d.text((0, i * 12), text[:21], font=self._font, fill=255)

    def clear(self) -> None:
        if self.ok:
            self.dev.clear()
