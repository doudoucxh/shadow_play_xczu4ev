#!/bin/sh
# Installed bundle root, manually invoked by the PC. No boot auto-start.
set -eu
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -u -m shadow_play.bus_servo.service --profile shadow_play/config/bus_servo.json --manifest bus_servo.manifest.json --allow-motion
