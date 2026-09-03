#!/usr/bin/env bash
# The one step that needs root: create /dev/i2c-1 for the AS7341 and the OLED.
# Split out of setup.sh so the privileged part is one short, readable thing you
# can check before running rather than a sudo buried in a longer script.
set -uo pipefail

if [ -e /dev/i2c-1 ]; then
  echo "/dev/i2c-1 already exists -- nothing to do."
  exit 0
fi

echo "This enables I2C1 on GPIO2/3 and reboots. It needs your password."
echo

sudo raspi-config nonint do_i2c 0 || { echo "raspi-config failed"; exit 1; }

if grep -qE '^dtparam=i2c_arm=on' /boot/firmware/config.txt; then
  echo "  config.txt now carries dtparam=i2c_arm=on"
else
  echo "  WARNING: no dtparam=i2c_arm=on in config.txt -- check it by hand"
fi

# Membership is what lets you talk to the bus WITHOUT sudo afterwards. Usually
# already set on Pi OS; adding it twice is harmless.
if id -nG | tr ' ' '\n' | grep -qx i2c; then
  echo "  you are already in the i2c group"
else
  sudo usermod -aG i2c "$USER" && echo "  added you to the i2c group"
fi

echo
read -rp "Reboot now? [y/N] " a
case "$a" in
  [yY]*) sudo reboot ;;
  *) echo "Not rebooting. /dev/i2c-1 appears after the next boot." ;;
esac
