#!/bin/bash
# Recover boot-disk space. My shell died with ENOSPC mid-session: `pip install
# kokoro` pulls PyTorch (~2-3 GB) on top of Playwright's Chromium, and the boot
# volume filled. Every Bash call now fails before it runs, because the tool
# cannot even create its own output file.
#
#   bash "/Volumes/Extreme SSD/Projects/cell/cell4b/free-space.sh"

set -u
VENV="/Volumes/Extreme SSD/Projects/cell/.venv"

echo "=== before ==="
df -h / | tail -1

echo
echo "--- caches ---"
rm -rf ~/Library/Caches/pip 2>/dev/null && echo "  pip cache cleared"
rm -rf ~/Library/Caches/ms-playwright 2>/dev/null && echo "  playwright cache cleared"

echo
echo "--- the big one: torch, pulled in by kokoro ---"
# The venv itself lives on the external SSD, but pip unpacks through the boot
# volume and torch leaves a lot behind. Drop the heavy TTS stack; the CAD work
# needs only numpy + shapely.
"$VENV/bin/pip" uninstall -y kokoro torch torchaudio transformers 2>/dev/null | tail -2

echo
echo "--- stale task output files ---"
find /private/tmp/claude-501 -name '*.output' -delete 2>/dev/null
echo "  done"

echo
echo "=== after ==="
df -h / | tail -1
echo
echo "Reinstall TTS later, once there is room, with:"
echo "  \"$VENV/bin/pip\" install kokoro soundfile"
