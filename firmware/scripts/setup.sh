#!/usr/bin/env bash
# CELL-4B Pi setup. Idempotent -- safe to re-run.
set -euo pipefail

echo "== apt packages =="
# gpiozero, picamera2 and i2c-tools come from apt deliberately. Installing
# picamera2 or gpiozero via pip gives you a second copy that cannot reach the
# hardware, and the failure looks like a wiring fault.
sudo apt-get update -qq
sudo apt-get install -y python3-gpiozero python3-picamera2 python3-pil \
                        i2c-tools python3-venv python3-lgpio

echo
echo "== interfaces =="
sudo raspi-config nonint do_i2c 0        # 0 == enable
echo "  I2C enabled"
if sudo raspi-config nonint get_camera 2>/dev/null | grep -q 1; then
  echo "  camera already enabled"
else
  sudo raspi-config nonint do_camera 0 2>/dev/null || \
    echo "  (camera is auto-detected on Bookworm; nothing to enable)"
fi

echo
echo "== python env =="
# --system-site-packages so the venv can still see apt's gpiozero/picamera2.
cd "$(dirname "$0")/.."
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "  venv ready at $(pwd)/.venv"

echo
echo "== bus =="
sudo i2cdetect -y 1 || true
echo
echo "Expect 39 (AS7341) and 3c or 3d (OLED)."
echo "Next:  .venv/bin/python -m cell4b selftest"
