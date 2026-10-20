#!/usr/bin/env bash
# Installs Heartbeat Radar on a Raspberry Pi and starts it on boot.
# Run as your normal user (not with sudo); it asks for sudo when it needs it.
#
#   ./scripts/install.sh              web UI only
#   ./scripts/install.sh --display    also show the UI full screen on an attached display
#   ./scripts/install.sh --no-display turn the attached-display mode back off
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Run this as your normal user, not root: ./scripts/install.sh" >&2
  exit 1
fi

DISPLAY_MODE=""
for arg in "$@"; do
  case $arg in
    --display) DISPLAY_MODE=on ;;
    --no-display) DISPLAY_MODE=off ;;
    *) echo "Unknown option: $arg (use --display or --no-display)" >&2; exit 1 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE=/etc/systemd/system/heartbeat-radar.service
DISPLAY_SERVICE=/etc/systemd/system/heartbeat-display.service
DISPLAY_PAM=/etc/pam.d/heartbeat-display
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

# Page shown on an attached display (only used with install.sh --display).
# Change the port here too if you change --http-port above.
#HEARTBEAT_DISPLAY_URL="http://localhost:8000/?kiosk=1"
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

if [[ $DISPLAY_MODE == on ]]; then
  echo "==> Installing full-screen display (cage + Chromium)"
  if systemctl is-enabled --quiet display-manager 2>/dev/null; then
    echo "    Note: this Pi boots into a desktop. The radar display takes over the"
    echo "    first screen (tty1). Raspberry Pi OS Lite is recommended for display mode."
  fi
  if apt-cache show chromium >/dev/null 2>&1; then
    sudo apt-get install -y cage chromium
  else
    sudo apt-get install -y cage chromium-browser
  fi
  sudo usermod -aG video,render,input "$USER"
  chmod +x "$REPO_DIR/scripts/heartbeat-display.sh"

  # Gives the display its own login session on tty1 (from the cage wiki).
  sudo tee "$DISPLAY_PAM" >/dev/null <<'EOF'
auth     required pam_unix.so nullok
account  required pam_unix.so
session  required pam_unix.so
session  required pam_systemd.so
EOF

  sudo tee "$DISPLAY_SERVICE" >/dev/null <<EOF
[Unit]
Description=Heartbeat Radar full-screen display
After=heartbeat-radar.service systemd-user-sessions.service dbus.socket systemd-logind.service getty@tty1.service
Wants=heartbeat-radar.service dbus.socket systemd-logind.service
Conflicts=getty@tty1.service
ConditionPathExists=/dev/tty1

[Service]
User=$USER
EnvironmentFile=-$DEFAULTS
ExecStart=$REPO_DIR/scripts/heartbeat-display.sh
Restart=always
RestartSec=5
PAMName=heartbeat-display
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
StandardInput=tty-fail
StandardOutput=journal
StandardError=journal
UtmpIdentifier=tty1
UtmpMode=user

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable heartbeat-display
  sudo systemctl restart heartbeat-display
elif [[ $DISPLAY_MODE == off ]] && [[ -f $DISPLAY_SERVICE ]]; then
  echo "==> Removing full-screen display"
  sudo systemctl disable --now heartbeat-display
  sudo rm -f "$DISPLAY_SERVICE" "$DISPLAY_PAM"
  sudo systemctl daemon-reload
  sudo systemctl start getty@tty1
fi

echo
echo "Done. Open http://$(hostname).local:8000 from a phone or computer on the same network."
if [[ $DISPLAY_MODE == on ]]; then
  echo "The attached display shows the same view. Reboot once so the new group memberships apply."
fi
echo "Logs: journalctl -u heartbeat-radar -f"
