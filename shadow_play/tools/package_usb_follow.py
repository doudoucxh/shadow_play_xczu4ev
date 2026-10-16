#!/usr/bin/env python3
"""Package USB FOLLOW sources without models, credentials, or captured images."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def package(destination):
    root = Path(__file__).resolve().parents[1]
    # Includes ui_frame_feed.py, imported even when UI publishing is disabled.
    files = list((root/'integrations/follow').glob('*.py'))
    if root/'integrations/follow/ui_frame_feed.py' not in files:
        raise FileNotFoundError('Missing FOLLOW UI frame publisher dependency')
    files += [root/'integrations/calibration'/name for name in ('mmio32.py','libservo_mmio32.so')]
    files += [root/'tools'/name for name in ('usb_camera_probe.py','run_usb_follow.sh')]
    files += [root/'tests'/name for name in
              ('test_usb_camera.py', 'test_follow_sender.py', 'test_ui_frame_feed.py')]
    files += [root/'docs/usb_camera_migration.md']
    manifest = {str(p.relative_to(root)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in files}
    with tarfile.open(destination, 'x:gz') as archive:
        for path in files:
            archive.add(path, arcname='shadow-usb-camera-20261010/'+path.relative_to(root).as_posix())
        data = (json.dumps(manifest, indent=2)+'\n').encode()
        entry = tarfile.TarInfo('shadow-usb-camera-20261010/SHA256.json')
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
    print(json.dumps(dict(archive=str(destination),files=len(files),
                         sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    package(parser.parse_args().destination)
