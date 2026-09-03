#!/usr/bin/env bash
# CELL-4B Pi setup. Idempotent, and does not assume passwordless sudo:
# anything needing root is reported for you to run, not silently attempted.
set -uo pipefail
cd "$(dirname "$0")/.."

HAVE_SUDO=0
sudo -n true 2>/dev/null && HAVE_SUDO=1

# apt names the tools; gpiozero and picamera2 come from apt DELIBERATELY --
# a pip copy of either cannot reach the hardware, and the failure looks
# exactly like a wiring fault.
APT="python3-gpiozero python3-picamera2 python3-pil i2c-tools python3-venv python3-lgpio"
MISSING=""
for p in $APT; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING="$MISSING $p"
done

echo "== apt =="
if [ -z "$MISSING" ]; then
  echo "  all present"
elif [ "$HAVE_SUDO" = 1 ]; then
  sudo apt-get update -qq && sudo apt-get install -y $MISSING
else
  echo "  MISSING:$MISSING"
  echo "  run:  sudo apt install$MISSING"
fi

echo
echo "== i2c bus =="
if [ -e /dev/i2c-1 ]; then
  echo "  /dev/i2c-1 present"
else
  echo "  /dev/i2c-1 MISSING -- the AS7341 (0x39) and OLED (0x3C) have no bus."
  if [ "$HAVE_SUDO" = 1 ]; then
    sudo raspi-config nonint do_i2c 0 && echo "  enabled; REBOOT to create /dev/i2c-1"
  else
    echo "  run:  sudo raspi-config nonint do_i2c 0 && sudo reboot"
  fi
fi

echo
echo "== python env =="
# --system-site-packages so the venv still sees apt's gpiozero and picamera2.
if [ ! -d .venv ]; then
  python3 -m venv --system-site-packages .venv || exit 1
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt && echo "  venv ready at $(pwd)/.venv"

echo
echo "== bus scan =="
# Debian keeps i2cdetect in /usr/sbin, off a normal user's PATH.
I2CDETECT=$(command -v i2cdetect || echo /usr/sbin/i2cdetect)
if [ -e /dev/i2c-1 ]; then
  "$I2CDETECT" -y 1 || echo "  (needs the i2c group: sudo usermod -aG i2c $USER, then log out and in)"
  echo
  echo "  Expect 39 (AS7341) and 3c or 3d (OLED)."
else
  echo "  skipped -- no /dev/i2c-1 yet"
fi

echo
echo "Next:  .venv/bin/python -m cell4b selftest"
