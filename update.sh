#!/usr/bin/env bash
# =====================================================================
#  lap-monitor - update script
#  Run on the target machine to pull the latest code and restart.
#  Usage:  bash update.sh        (or: chmod +x update.sh && ./update.sh)
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Current version:"
python3 -m lap_monitor --version || true

echo "==> Pulling latest code from git..."
git pull --ff-only

echo "==> Installing/updating dependencies..."
if pip3 install -r requirements.txt --break-system-packages 2>/dev/null; then
  :
else
  # Older pip without --break-system-packages
  pip3 install -r requirements.txt
fi

# If running as the 'lap-monitor' systemd service, restart it.
if command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet lap-monitor 2>/dev/null; then
  echo "==> Restarting systemd service 'lap-monitor'..."
  sudo systemctl restart lap-monitor
  echo "    Done. Check status:  systemctl status lap-monitor"
else
  echo "==> Not a systemd service. If running under tmux, restart it manually:"
  echo "    tmux attach -t lap-monitor   # Ctrl+C, then: python3 -m lap_monitor serve"
fi

echo "==> Updated to:"
python3 -m lap_monitor --version
