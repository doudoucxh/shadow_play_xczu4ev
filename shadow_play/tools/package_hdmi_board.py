"""Build a separate board integration release; no hardware or remote commands."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

RELEASE = 'shadow-theatre-board-20261016-r3'


def package(output):
    root = Path(__file__).resolve().parents[1]
    ui = root / 'hdmi_ui'
    files = [p for p in ui.rglob('*') if p.is_file() and
             '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log')]
    files += list((root/'integrations/follow').glob('*.py'))
    files += [root/'integrations/calibration'/n for n in ('mmio32.py','libservo_mmio32.so')]
    files += [root/'tools'/n for n in ('run_usb_follow.sh','usb_camera_probe.py')]
    if any(p.is_symlink() for p in files):
        raise ValueError('Release inputs must be ordinary files')
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(files)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(str(output),'x:gz') as archive:
        for p in sorted(files):
            entry = archive.gettarinfo(str(p),RELEASE+'/shadow_play/'+p.relative_to(root).as_posix())
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = ''
            entry.mode = 0o644
            with p.open('rb') as handle:
                archive.addfile(entry,handle)
        payload = json.dumps(dict(release=RELEASE,files=manifest,
                                  deployed=False,motion_enabled=False),indent=2).encode()
        entry = tarfile.TarInfo(RELEASE+'/MANIFEST.json')
        entry.size = len(payload)
        archive.addfile(entry,io.BytesIO(payload))
    print(json.dumps(dict(archive=str(output.resolve()),files=len(files),
                         sha256=hashlib.sha256(output.read_bytes()).hexdigest())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    package(parser.parse_args().output)
