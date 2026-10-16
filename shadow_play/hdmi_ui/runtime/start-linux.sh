#!/bin/sh
# Run inside the board's existing X11/Wayland graphical login session.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PORT=${SHADOW_UI_PORT:-8765}
PYTHON=${SHADOW_UI_PYTHON:-python3}
URL="http://127.0.0.1:$PORT/"
command -v "$PYTHON" >/dev/null 2>&1 || { echo "Python 3 is required. See README_CN.md." >&2; exit 1; }
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "No graphical session detected. This board may currently output through the PL/VDMA pipeline." >&2
  echo "Run sh runtime/check-board.sh, then follow docs/BOARD_INTEGRATION_CN.md. Starting an HTTP server alone does not drive HDMI." >&2
  exit 2
fi
if [ "$(id -u)" = 0 ]; then
  echo "Start the browser as the graphical-session user, not root. This script does not disable the browser sandbox." >&2
  exit 2
fi
BROWSER=${SHADOW_UI_BROWSER:-}
if [ -z "$BROWSER" ]; then
  for candidate in chromium chromium-browser google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then BROWSER=$candidate; break; fi
  done
fi
[ -n "$BROWSER" ] || { echo "A native ARM64 Chromium browser is required. See docs/BOARD_INTEGRATION_CN.md." >&2; exit 2; }
PROFILE=${SHADOW_UI_PROFILE:-${XDG_DATA_HOME:-$HOME/.local/share}/shadow-theatre-hdmi}
LOG_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/shadow-theatre-hdmi
mkdir -p "$PROFILE" "$LOG_DIR"
SERVER_PID=
BROWSER_PID=
cleanup() {
  if [ -n "$BROWSER_PID" ]; then kill "$BROWSER_PID" 2>/dev/null || true; fi
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT HUP INT TERM
if ! "$PYTHON" - "$PORT" "$SCRIPT_DIR/web/index.html" <<'PY'
import hashlib,json,sys,urllib.request
from pathlib import Path
expected=hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
try:
    with urllib.request.urlopen('http://127.0.0.1:'+sys.argv[1]+'/health.json',timeout=1) as r:
        health=json.load(r)
        assert health.get('app')=='shadow-theatre-hdmi' and health.get('ui_sha256')==expected
except Exception:
    raise SystemExit(1)
PY
then
  "$PYTHON" "$SCRIPT_DIR/serve.py" --port "$PORT" >"$LOG_DIR/server.log" 2>&1 &
  SERVER_PID=$!
fi
"$PYTHON" - "$PORT" "$SCRIPT_DIR/web/index.html" <<'PY'
import hashlib,json,sys,time,urllib.request
from pathlib import Path
expected=hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
for _ in range(40):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+sys.argv[1]+'/health.json',timeout=.5) as r:
            health=json.load(r)
            assert health.get('app')=='shadow-theatre-hdmi' and health.get('ui_sha256')==expected
        break
    except Exception:
        time.sleep(.1)
else:
    raise SystemExit('The matching UI did not start. Close the old UI and stop its server before retrying. Check server.log; an occupied port is not terminated automatically.')
PY
"$BROWSER" --kiosk --app="$URL" --window-size=1024,600 --window-position=0,0 \
  --force-device-scale-factor=1 --user-data-dir="$PROFILE" --no-first-run \
  --disable-session-crashed-bubble --overscroll-history-navigation=0 \
  --touch-events=enabled --password-store=basic >"$LOG_DIR/browser.log" 2>&1 &
BROWSER_PID=$!
wait "$BROWSER_PID"
