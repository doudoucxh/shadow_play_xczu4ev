#!/bin/sh
# Read-only diagnostics. No register writes, display changes, or service stops.
printf '\n== Expected project board ==\nMPSoC-P4 / XCZU4EV, Linux, target UI 1024x600\n'
printf '\n== Actual machine ==\n'
uname -a
if [ -r /proc/device-tree/model ]; then tr '\000' '\n' </proc/device-tree/model; fi
printf '\n== Runtime ==\n'
command -v python3 && python3 --version
for browser in chromium chromium-browser google-chrome; do
  if command -v "$browser" >/dev/null 2>&1; then "$browser" --version; fi
done
printf 'DISPLAY=%s\nWAYLAND_DISPLAY=%s\n' "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}"
printf '\n== Display/input device names ==\n'
for device in /dev/fb* /dev/dri/card* /dev/input/event* /dev/video*; do
  [ ! -e "$device" ] || ls -l "$device"
done
for status in /sys/class/drm/*/status; do
  [ ! -r "$status" ] || { printf '%s: ' "$status"; cat "$status"; }
done
if command -v xrandr >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then xrandr --current; fi
printf '\n== Existing project services (read only) ==\n'
if command -v systemctl >/dev/null 2>&1; then
  systemctl --no-pager --full status shadow-video.service shadow-yolo-follow.service 2>/dev/null || true
fi
printf '\nAn HTTP server or /dev/fb0 alone does not prove that a browser can scan out through the current PL HDMI design.\n'
