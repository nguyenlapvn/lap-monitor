#!/usr/bin/env bash
# =====================================================================
#  lap-monitor - uninstaller
#  Stops and removes the systemd service. Leaves your config + data
#  in place (delete them by hand if you want a full wipe).
#
#  Usage:  bash uninstall.sh
# =====================================================================
set -euo pipefail

SERVICE_NAME="lap-monitor"
UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Stopping and disabling ${SERVICE_NAME}..."
  sudo systemctl disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
  if [ -f "$UNIT" ]; then
    sudo rm -f "$UNIT"
    sudo systemctl daemon-reload
    echo "==> Removed $UNIT"
  fi
else
  echo "!! systemctl not found - nothing to remove."
fi

# Remove the CLI launcher.
if [ -f /usr/local/bin/lap-monitor ]; then
  sudo rm -f /usr/local/bin/lap-monitor
  echo "==> Removed /usr/local/bin/lap-monitor"
fi

echo "==> Done. Your config.yaml and data/ (targets, history) were kept."
