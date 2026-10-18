"""Install a checked task-one audio patch on SD; no motion or boot interfaces."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path('/run/media/mmcblk0p2/piying/shadow-theatre-board-20261017-r4-runtime')
NAMES = {'hdmi_ui/runtime/board_audio.py', 'hdmi_ui/runtime/task1_audio.json',
         'hdmi_ui/runtime/audio/wusong.mp3'}
UNITS = ['shadow-theatre-ui-r4', 'shadow-theatre-browser-r4', 'shadow-theatre-hdmi-r4']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def payload(raw, expected):
    if sha(raw) != expected:
        raise ValueError('Audio patch checksum mismatch')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            if (member.name not in NAMES or member.name in files or
                    not member.isfile() or not 0 < member.size < 2*1024*1024):
                raise ValueError('Unexpected audio patch member')
            files[member.name] = archive.extractfile(member).read()
    if set(files) != NAMES:
        raise ValueError('Incomplete audio patch')
    track = json.loads(files['hdmi_ui/runtime/task1_audio.json'])
    if (track['schema'] != 'task1_audio_v1' or track['playback']['runtime_filename'] != 'wusong.mp3'
            or sha(files['hdmi_ui/runtime/audio/wusong.mp3']) != track['playback']['sha256']
            or track['playback']['sample_rate_hz'] != 48000 or track['playback']['channels'] != 2
            or not 0 < track['playback']['decoded_frames'] <= 48000*600):
        raise ValueError('Invalid audio metadata')
    ast.parse(files['hdmi_ui/runtime/board_audio.py'])
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--sha256', required=True)
    args = p.parse_args()
    files = payload(args.archive.read_bytes(), args.sha256)
    root = ROOT/'shadow_play'
    manifest_path = ROOT/'MANIFEST.json'
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    for name, expected in manifest['files'].items():
        path = root/name
        if not path.resolve().is_relative_to(root.resolve()) or sha(path.read_bytes()) != expected:
            raise ValueError('Installed manifest mismatch: '+name)
    status = json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=5))
    if status['camera']['running'] or status['audio']['running']:
        raise RuntimeError('Stop current camera/audio session before updating')
    backup = ROOT/'backups/task1-audio-v20-20261018'
    backup.mkdir(exist_ok=False)
    (backup/'MANIFEST.json').write_bytes(original_manifest)
    originals = {}
    for name in files:
        target = root/name
        originals[name] = target.read_bytes() if target.exists() else None
        if originals[name] is not None:
            saved = backup/name
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(originals[name])
    (backup/'existing-files.json').write_text(json.dumps({n:b is not None for n,b in originals.items()}, indent=2))
    subprocess.run(['systemctl', 'stop', *reversed(UNITS)], check=True)
    try:
        for name, data in files.items():
            target = root/name
            staged = target.with_name(target.name+'.task1-tmp')
            staged.write_bytes(data)
            staged.replace(target)
            manifest['files'][name] = sha(data)
        staged_manifest = manifest_path.with_suffix('.task1-tmp')
        staged_manifest.write_text(json.dumps(manifest, indent=2)+'\n')
        staged_manifest.replace(manifest_path)
        os.sync()
        for name, expected in manifest['files'].items():
            if sha((root/name).read_bytes()) != expected:
                raise RuntimeError('Post-install manifest mismatch: '+name)
    except BaseException:
        for name, data in originals.items():
            target = root/name
            if data is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(data)
        manifest_path.write_bytes(original_manifest)
        os.sync()
        raise
    finally:
        subprocess.run(['systemctl', 'start', *UNITS], check=True)
    print(json.dumps(dict(installed=True, manifest_files=len(manifest['files']), backup=str(backup),
                          hashes={name:sha(data) for name,data in files.items()})), flush=True)


if __name__ == '__main__':
    main()
