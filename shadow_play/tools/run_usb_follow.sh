#!/bin/sh
# USB capture has no dependency on shadow-video.service or OV5640 boot_guard.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for unit in shadow-yolo-follow.service shadow-video.service; do
    if systemctl is-active --quiet "$unit"; then
        echo "Stop $unit before using the independent USB path." >&2
        exit 1
    fi
done
export PYTHONDONTWRITEBYTECODE=1
python3 "$ROOT/tools/usb_camera_probe.py"
exec python3 -u "$ROOT/integrations/follow/board_usb_follow.py" "$@"
