"""Package/install the isolated first-direction check; installation never starts it."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

RELEASE = 'v20-first-direction-20261018-r4'
DEST = Path('/run/media/mmcblk0p2/piying') / RELEASE
PREFIX = 'integrations/calibration/'
NAMES = ('v20_first_direction.py', 'servo_pwm_device.py', 'mmio32.py', 'libservo_mmio32.so')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(output):
    source = Path(__file__).resolve().parents[1] / 'integrations/calibration'
    files = {PREFIX + name: (source / name).read_bytes() for name in NAMES}
    files[PREFIX + '.motion-inhibit'] = b'Only the attended one-use axis-7 first-direction check; ordinary motion inhibited.\n'
    manifest = dict(release=RELEASE, autostart=False, files={n: sha(b) for n, b in files.items()})
    files['MANIFEST.json'] = json.dumps(manifest, indent=2).encode()
    with tarfile.open(output, 'x:gz') as archive:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            item.mode = 0o644
            archive.addfile(item, io.BytesIO(data))
    print(json.dumps(dict(archive=str(output), sha256=sha(output.read_bytes()))))


def install(archive, expected):
    raw = archive.read_bytes()
    if sha(raw) != expected:
        raise ValueError('Archive hash mismatch')
    allowed = {PREFIX + n for n in NAMES} | {PREFIX + '.motion-inhibit', 'MANIFEST.json'}
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as bundle:
        for item in bundle:
            if item.name not in allowed or item.name in files or not item.isfile() or not 0 < item.size < 256 * 1024:
                raise ValueError('Unexpected bundle member')
            files[item.name] = bundle.extractfile(item).read()
    if set(files) != allowed:
        raise ValueError('Incomplete installation')
    manifest = json.loads(files['MANIFEST.json'])
    if manifest['release'] != RELEASE or manifest['autostart'] is not False or set(manifest['files']) != allowed - {'MANIFEST.json'}:
        raise ValueError('Wrong release manifest')
    for name, expected_hash in manifest['files'].items():
        if sha(files[name]) != expected_hash:
            raise ValueError('Member checksum mismatch')
        if name.endswith('.py'):
            compile(files[name], name, 'exec')
    if not os.path.ismount(DEST.parent.parent):
        raise RuntimeError('Persistent SD partition is not mounted')
    if DEST.exists():
        if any(not (DEST / n).is_file() or sha((DEST / n).read_bytes()) != sha(b) for n, b in files.items()):
            raise FileExistsError('Different existing installation; preserve for inspection')
        print('ALREADY_INSTALLED_NO_SERVICE_STARTED')
        return
    DEST.mkdir()
    for name, data in files.items():
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    os.sync()
    if any(sha((DEST / n).read_bytes()) != sha(b) for n, b in files.items()):
        raise RuntimeError('Installed checksum mismatch')
    print(json.dumps(dict(installed=str(DEST), manifest_entries=len(manifest['files']), service_started=False, motor_commands_sent=False)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['build', 'install'])
    p.add_argument('archive', type=Path)
    p.add_argument('--sha256')
    a = p.parse_args()
    if a.mode == 'build':
        build(a.archive)
    else:
        install(a.archive, a.sha256)
