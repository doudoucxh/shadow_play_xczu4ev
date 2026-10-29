"""Prepare a versioned dual-bus console profile without changing the boot package.

The boot FIT pins bus-servo-v1. Keep that immutable and reuse its verified
service with an explicit, separately installed operator configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path

from shadow_play.bus_servo.model import Profile

BASE_MANIFEST_SHA = 'f5e1d0a9fe66eeb0d9cfa837e4dc049d0728c34de2cfd305615cc93fd5e57434'
BASE_DIRECTORY = '/run/media/mmcblk0p2/piying/bus-servo-v1'
CONSOLE_DIRECTORY = '/run/media/mmcblk0p2/piying/bus-servo-dual-console-v1'


def build(profile_path, destination):
    raw = Path(profile_path).read_bytes()
    profile = Profile(json.loads(raw.decode('utf-8-sig')))
    if profile.layout.name != 'dual' or profile.data.get('electrical_3v3_verified') is not True:
        raise ValueError('Requires a confirmed dual electrical profile')
    if (profile.data.get('hardware_verified') is not False
            or profile.data.get('mechanical_limits_verified') is not False):
        raise ValueError('This console update does not enable movement')
    confirmation = profile.data.get('electrical_verification', {})
    if confirmation.get('source') != 'user_report' or confirmation.get('layout') != 'dual':
        raise ValueError('The explicit dual-bus confirmation record is missing')
    sha = hashlib.sha256(raw).hexdigest()
    script = f'''#!/bin/sh
set -eu
cd {BASE_DIRECTORY}
python3 - <<'VERIFY'
import hashlib, json
from pathlib import Path
root = Path({BASE_DIRECTORY!r})
profile = Path({CONSOLE_DIRECTORY!r})/'bus_servo.json'
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
if digest(root/'MANIFEST.json') != {BASE_MANIFEST_SHA!r}:
    raise RuntimeError('Dual boot package manifest changed')
if digest(profile) != {sha!r}:
    raise RuntimeError('Confirmed console profile checksum mismatch')
for name, expected in json.loads((root/'MANIFEST.json').read_text())['files'].items():
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or digest(path) != expected:
        raise RuntimeError('Dual runtime file mismatch: '+name)
VERIFY
export PYTHONPATH="$PWD"
exec python3 -u -m shadow_play.bus_servo.service --profile {CONSOLE_DIRECTORY}/bus_servo.json --manifest bus_servo.manifest.json --allow-release
'''.encode('utf-8')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'bus_servo.json').write_bytes(raw)
    (destination/'start_console.sh').write_bytes(script)
    manifest = dict(schema='shadow.bus-console.v1', base_directory=BASE_DIRECTORY,
                    base_manifest_sha256=BASE_MANIFEST_SHA, profile_sha256=profile.fingerprint,
                    electrical_confirmation=confirmation, allow_release=True, allow_motion=False,
                    files={'bus_servo.json': sha, 'start_console.sh': hashlib.sha256(script).hexdigest()})
    (destination/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.profile,args.output),ensure_ascii=False))


if __name__=='__main__':
    main()
