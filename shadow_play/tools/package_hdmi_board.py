"""Build a separate board integration release; no hardware or remote commands."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

RELEASE = 'shadow-theatre-board-20261017-r4'


def package(output, runtime_only=False, audio_bundle=None, websocket_wheel=None, include_hdmi_image=False, alsa_deb=None):
    root = Path(__file__).resolve().parents[1]
    ui = root / 'hdmi_ui'
    ui_inputs = ui / 'runtime' if runtime_only else ui
    release = RELEASE + '-runtime' if runtime_only else RELEASE
    files = [p for p in ui_inputs.rglob('*') if p.is_file() and
             '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log')]
    files += list((root/'integrations/follow').glob('*.py'))
    files += [root/'integrations/calibration'/n for n in ('mmio32.py','libservo_mmio32.so')]
    files += [root/'tools'/n for n in ('run_usb_follow.sh','usb_camera_probe.py')]
    if include_hdmi_image:
        files += [root/'integrations/calibration'/n for n in ('load_pwm_runtime.py','servo_pwm_device.py')]
        files += [root/'hardware/servo_pwm/release'/n for n in ('servo10_vision.bit.bin','servo10.manifest.json')]
    if any(p.is_symlink() for p in files):
        raise ValueError('Release inputs must be ordinary files')
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(files)}
    extras = {}
    if audio_bundle:
        audio_bundle = Path(audio_bundle)
        for source, target, expected in [
            ('usb_audio_play', 'usb_audio_play', '8684834abfc45f2823c4f3992ccd15b8c5bf3150b2757d7000b7a462cd59866d'),
            ('wusong-2-48k.mp3', 'wusong.mp3', 'e001fb858ab32e4d0217bd7c5262667f8f077025e12be19fb21b82a1a8bd13e7'),
            ('tinyalsa/LICENSE', 'TinyALSA-LICENSE', None), ('tinyalsa/NOTICE', 'TinyALSA-NOTICE', None),
            ('minimp3/LICENSE', 'minimp3-LICENSE', None)]:
            data = (audio_bundle/source).read_bytes()
            if expected and hashlib.sha256(data).hexdigest() != expected: raise ValueError('Audio input changed: '+source)
            extras['hdmi_ui/runtime/audio/'+target] = data
    if websocket_wheel:
        with zipfile.ZipFile(websocket_wheel) as wheel:
            for name in wheel.namelist():
                if name.startswith('websocket/') and name.endswith('.py') and '..' not in Path(name).parts:
                    extras['hdmi_ui/runtime/vendor/'+name] = wheel.read(name)
                elif name.endswith('/LICENSE'):
                    extras['hdmi_ui/runtime/vendor/websocket-client-LICENSE'] = wheel.read(name)
        if 'hdmi_ui/runtime/vendor/websocket/__init__.py' not in extras:
            raise ValueError('Invalid websocket-client wheel')
    if alsa_deb:
        data = Path(alsa_deb).read_bytes()
        if hashlib.sha256(data).hexdigest() != '9fa889400fcee4b92c8f4a2fafbb7f2cd33444d9ec1665a71002ab67c06114bb':
            raise ValueError('Unverified ARM64 ALSA package')
        offset, found = 8, False
        if data[:8] != b'!<arch>\n': raise ValueError('Invalid Debian archive')
        while offset+60 <= len(data):
            header=data[offset:offset+60]; length=int(header[48:58]); offset+=60
            if header[:16].decode().strip().rstrip('/').startswith('data.tar'):
                with tarfile.open(fileobj=io.BytesIO(data[offset:offset+length])) as archive:
                    for member in archive:
                        if member.name.endswith('/libasound.so.2.0.0') and member.isfile():
                            extras['hdmi_ui/runtime/vendor/lib/libasound.so.2']=archive.extractfile(member).read()
                            found=True
                        elif member.name.endswith('/libasound2/copyright') and member.isfile():
                            extras['hdmi_ui/runtime/vendor/ALSA-copyright']=archive.extractfile(member).read()
            offset+=length+(length%2)
        if not found: raise ValueError('Missing ALSA library')
    manifest.update({name:hashlib.sha256(data).hexdigest() for name,data in extras.items()})
    output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(str(output),'x:gz') as archive:
        for p in sorted(files):
            entry = archive.gettarinfo(str(p),release+'/shadow_play/'+p.relative_to(root).as_posix())
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = ''
            entry.mode = 0o644
            with p.open('rb') as handle:
                archive.addfile(entry,handle)
        for name, data in sorted(extras.items()):
            entry = tarfile.TarInfo(release+'/shadow_play/'+name)
            entry.mode = 0o755 if name.endswith('/usb_audio_play') else 0o644
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        payload = json.dumps(dict(release=release,files=manifest,
                                  deployed=False,motion_enabled=False),indent=2).encode()
        entry = tarfile.TarInfo(release+'/MANIFEST.json')
        entry.size = len(payload)
        archive.addfile(entry,io.BytesIO(payload))
    print(json.dumps(dict(archive=str(output.resolve()),files=len(manifest),
                         sha256=hashlib.sha256(output.read_bytes()).hexdigest())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--runtime-only', action='store_true', help='Omit source, docs and desktop screenshots for slow serial links')
    parser.add_argument('--audio-bundle', type=Path)
    parser.add_argument('--websocket-wheel', type=Path)
    parser.add_argument('--include-hdmi-image', action='store_true', help='Package the reviewed display-capable PL image; never load it automatically')
    parser.add_argument('--alsa-deb', type=Path, help='Fixed ARM64 ALSA dependency in the browser private directory')
    args = parser.parse_args()
    package(args.output, args.runtime_only, args.audio_bundle, args.websocket_wheel, args.include_hdmi_image, args.alsa_deb)
