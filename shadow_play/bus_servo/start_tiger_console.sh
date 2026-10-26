#!/bin/sh
# Independent BT04 bundle root, manually invoked; never a boot service.
set -eu
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -u -m shadow_play.bus_servo.service --profile shadow_play/config/bus_servo_tiger_four.json --manifest bus_servo.manifest.json --allow-motion
