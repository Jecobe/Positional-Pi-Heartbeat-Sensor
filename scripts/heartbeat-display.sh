#!/usr/bin/env bash
# Shows the web UI full screen on the Pi's own display.
# Started on tty1 by heartbeat-display.service (see scripts/install.sh --display).
set -euo pipefail

URL="${HEARTBEAT_DISPLAY_URL:-http://localhost:8000/?kiosk=1}"
BROWSER="$(command -v chromium || command -v chromium-browser)"

# Chromium shows an error page (and never retries) if the server isn't up yet.
for _ in $(seq 120); do
  if python3 -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)' "$URL" 2>/dev/null; then
    break
  fi
  sleep 1
done

exec cage -- "$BROWSER" \
  --kiosk \
  --incognito \
  --ozone-platform=wayland \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=Translate \
  --no-first-run \
  --password-store=basic \
  --check-for-update-interval=31536000 \
  "$URL"
