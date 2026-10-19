#!/usr/bin/env bash
# Installs Heartbeat Radar on a Raspberry Pi and starts it on boot.
# Run as your normal user (not with sudo); it asks for sudo when it needs it.
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Run this as your normal user, not root: ./scripts/install.sh" >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE=/etc/systemd/system/heartbeat-radar.service
DEFAULTS=/etc/default/heartbeat-radar

echo "==> Installing system packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip

echo "==> Creating virtualenv in $REPO_DIR/.venv"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install "$REPO_DIR"

echo "==> Allowing $USER to use serial ports"
sudo usermod -aG dialout "$USER"

if [[ ! -f $DEFAULTS ]]; then
  echo "==> Writing $DEFAULTS (edit this to change options)"
  sudo tee "$DEFAULTS" >/dev/null <<'EOF'
# Extra options for `heartbeat-radar serve`. See: heartbeat-radar serve --help
# Examples:
#   HEARTBEAT_RADAR_ARGS="--source sim"            # demo without the radar
#   HEARTBEAT_RADAR_ARGS="--flip-x --max-range 4"  # mirror the map, zoom in
HEARTBEAT_RADAR_ARGS=""
EOF
fi

echo "==> Installing systemd service"
sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Heartbeat Radar web UI
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
SupplementaryGroups=dialout
EnvironmentFile=-$DEFAULTS
ExecStart=$REPO_DIR/.venv/bin/heartbeat-radar serve \$HEARTBEAT_RADAR_ARGS
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now heartbeat-radar
sudo systemctl restart heartbeat-radar

echo
echo "Done. Open http://$(hostname).local:8000 from a phone or computer on the same network."
echo "Logs: journalctl -u heartbeat-radar -f"
