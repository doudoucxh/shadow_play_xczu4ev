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


def build(profile_path, destination, *, allow_motion=False, service_overlay=False, protocol_overlay=False):
    if protocol_overlay and not service_overlay:
        raise ValueError('Protocol overlay requires the explicit service overlay')
    raw = Path(profile_path).read_bytes()
    profile = Profile(json.loads(raw.decode('utf-8-sig')))
    if profile.layout.name != 'dual' or profile.data.get('electrical_3v3_verified') is not True:
        raise ValueError('Requires a confirmed dual electrical profile')
    confirmation = profile.data.get('electrical_verification', {})
    if confirmation.get('source') != 'user_report' or confirmation.get('layout') != 'dual':
        raise ValueError('The explicit dual-bus confirmation record is missing')
    motion_confirmation = profile.data.get('motion_verification', {})
    if type(allow_motion) is not bool:
        raise ValueError('Explicit boolean motion opt-in required')
    if allow_motion and (not all(profile.data.get(k) is True for k in
                                 ('electrical_3v3_verified','hardware_verified','mechanical_limits_verified'))
                         or motion_confirmation.get('source') != 'user_report'
                         or motion_confirmation.get('layout') != 'dual'
                         or not motion_confirmation.get('statement')):
        raise ValueError('Movement requires completed checks and the explicit user confirmation')
    permission = ' --allow-motion' if allow_motion else ''
    sha = hashlib.sha256(raw).hexdigest()
    files = {'bus_servo.json': raw}
    overlay_check = ''
    entry = '-m shadow_play.bus_servo.service'
    if service_overlay:
        files['service.py'] = (Path(__file__).resolve().parents[1]/'bus_servo/service.py').read_bytes()
        service_sha = hashlib.sha256(files['service.py']).hexdigest()
        overlay_check = f"if digest(profile.parent/'service.py') != {service_sha!r}:\n    raise RuntimeError('Console service checksum mismatch')\n"
        # Use the verified base package for dependencies and only replace this
        # module. The boot snapshot and its pinned manifest remain immutable.
        entry = ('-c "import runpy; runpy.run_path(\'' + CONSOLE_DIRECTORY +
                 '/service.py\', run_name=\'shadow_play.bus_servo.service\')[\'main\']()"')
        if protocol_overlay:
            files['protocol.py'] = (Path(__file__).resolve().parents[1]/'bus_servo/protocol.py').read_bytes()
            protocol_sha = hashlib.sha256(files['protocol.py']).hexdigest()
            overlay_check += f"if digest(profile.parent/'protocol.py') != {protocol_sha!r}:\n    raise RuntimeError('Console protocol checksum mismatch')\n"
            # Register the exact verified protocol before service/device/model
            # imports. Keep all other dependencies in the immutable base package.
            bootstrap = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location("
                         "'shadow_play.bus_servo.protocol', '" + CONSOLE_DIRECTORY + "/protocol.py'); "
                         "protocol = importlib.util.module_from_spec(spec); spec.loader.exec_module(protocol); "
                         "sys.modules[spec.name] = protocol; ")
            entry = entry.replace('-c "', '-c "' + bootstrap, 1)
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
{overlay_check}\
for name, expected in json.loads((root/'MANIFEST.json').read_text())['files'].items():
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or digest(path) != expected:
        raise RuntimeError('Dual runtime file mismatch: '+name)
VERIFY
export PYTHONPATH="$PWD"
exec python3 -u {entry} --profile {CONSOLE_DIRECTORY}/bus_servo.json --manifest bus_servo.manifest.json --allow-release{permission}
'''.encode('utf-8')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    files['start_console.sh'] = script
    for name, content in files.items():
        (destination/name).write_bytes(content)
    manifest = dict(schema='shadow.bus-console.v1', base_directory=BASE_DIRECTORY,
                    base_manifest_sha256=BASE_MANIFEST_SHA, profile_sha256=profile.fingerprint,
                    electrical_confirmation=confirmation,
                    motion_confirmation=motion_confirmation if allow_motion else None,
                    allow_release=True, allow_motion=allow_motion,
                    service_overlay=bool(service_overlay),
                    protocol_overlay=bool(protocol_overlay),
                    files={name: hashlib.sha256(content).hexdigest() for name, content in files.items()})
    (destination/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-motion',action='store_true',help='Enable manual angle/playback commands only with the recorded user confirmation')
    parser.add_argument('--service-overlay',action='store_true',help='Install the current service module while preserving the immutable boot package')
    parser.add_argument('--protocol-overlay',action='store_true',help='Use the verified current protocol with --service-overlay')
    args=parser.parse_args()
    print(json.dumps(build(args.profile,args.output,allow_motion=args.allow_motion,service_overlay=args.service_overlay,protocol_overlay=args.protocol_overlay),ensure_ascii=False))


if __name__=='__main__':
    main()
