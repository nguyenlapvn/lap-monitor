#!/usr/bin/env bash
# =====================================================================
#  lap-monitor - uninstaller
#  Stops and removes the systemd service + CLI command. Leaves your
#  config + data in place (delete them by hand for a full wipe).
#
#  Usage:  bash uninstall.sh   (run as root, or as a user with sudo)
# =====================================================================
set -euo pipefail

SERVICE_NAME="lap-monitor"
UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

# Use sudo only when not already root.
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
elif command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  echo "!! Need root privileges (or 'sudo')."
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Stopping and disabling ${SERVICE_NAME}..."
  $SUDO systemctl disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
  if [ -f "$UNIT" ]; then
    $SUDO rm -f "$UNIT"
    $SUDO systemctl daemon-reload
    echo "==> Removed $UNIT"
  fi
else
  echo "!! systemctl not found - nothing to remove."
fi

# Remove the CLI launcher and its short alias.
if [ -f /usr/local/bin/lap-monitor ]; then
  $SUDO rm -f /usr/local/bin/lap-monitor
  echo "==> Removed /usr/local/bin/lap-monitor"
fi
if [ -L /usr/local/bin/lapm ] || [ -f /usr/local/bin/lapm ]; then
  $SUDO rm -f /usr/local/bin/lapm
  echo "==> Removed /usr/local/bin/lapm"
fi

echo "==> Done. Your config.yaml and data/ (targets, history) were kept."
