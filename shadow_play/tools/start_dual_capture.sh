#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
host="${SHADOW_CAMERA_HOST:-192.168.45.1}"
session="capture-sessions/practice-$(date +%Y%m%d-%H%M%S)-$$"
exec ./build-capture/shadow_capture --backend simulation \
  --config config/capture.servos.practice.json \
  --frame-url "http://${host}:8765/front.jpg" \
  --top-url "http://${host}:8765/top.jpg" \
  --session "$session"
