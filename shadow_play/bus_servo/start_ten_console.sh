#!/bin/sh
# Independent ten-port signals. Start manually; no boot changes.
set -eu
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -u -m shadow_play.bus_servo.service --profile shadow_play/config/bus_servo_ten_port.json --manifest bus_servo.manifest.json --allow-release
