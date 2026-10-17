"""Install the r4 UI and browser on SD without starting motors or changing boot.

Activation starts HTTP and the ordinary-user browser. HDMI is a separate unit,
started only after the reviewed display image is independently verified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

RELEASE = 'shadow-theatre-board-20261017-r4-runtime'
FIREFOX_SHA = 'ad647ee920828da7495de7a5f3eb5ddad457b107e4932b3fac49ce700bbbb2b2'
BASE = Path('/run/media/mmcblk0p2/piying')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def extract_new(archive, folder, prefix):
    if folder.exists(): raise FileExistsError(str(folder))
    folder.mkdir(mode=0o755)
    with tarfile.open(archive) as source:
        for entry in source:
            parts = Path(entry.name).parts
            if not parts or parts[0] != prefix or '..' in parts or not (entry.isfile() or entry.isdir()):
                raise ValueError('Unexpected archive entry: '+entry.name)
            target = folder.joinpath(*parts[1:])
            if not target.resolve().is_relative_to(folder.resolve()): raise ValueError('Archive path escapes destination')
            if entry.isdir(): target.mkdir(parents=True, exist_ok=True, mode=0o755)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with target.open('xb') as output, source.extractfile(entry) as data:
                    while True:
                        block = data.read(1024*1024)
                        if not block: break
                        output.write(block)
                target.chmod(0o755 if entry.mode & 0o111 else 0o644)


def units(root, firefox):
    runtime = root/'shadow_play/hdmi_ui/runtime'
    return {
        'shadow-theatre-ui-r4.service': f'''[Unit]
Description=Shadow theatre UI, camera recognition and audio only
After=local-fs.target
StartLimitBurst=3
StartLimitIntervalSec=60
[Service]
ExecStart=/usr/bin/python3 -u {runtime}/serve.py
WorkingDirectory={runtime}
Restart=on-failure
RestartSec=3
KillMode=control-group
TimeoutStopSec=10
UMask=0027
''',
        'shadow-theatre-browser-r4.service': f'''[Unit]
Description=Sandboxed shadow theatre page renderer
Requires=shadow-theatre-ui-r4.service
After=shadow-theatre-ui-r4.service
StartLimitBurst=3
StartLimitIntervalSec=60
[Service]
User=petalinux
SupplementaryGroups=input
RuntimeDirectory=shadow-ui
RuntimeDirectoryMode=0750
ExecStart=/usr/bin/python3 -u {runtime}/browser_display.py --firefox {firefox}/firefox
Restart=on-failure
RestartSec=3
KillMode=control-group
TimeoutStopSec=12
NoNewPrivileges=true
UMask=0027
''',
        'shadow-theatre-hdmi-r4.service': f'''[Unit]
Description=Reviewed PL HDMI sink for fresh theatre browser frames
After=shadow-theatre-browser-r4.service
ConditionPathExists=/run/shadow-pwm-loaded.json
[Service]
ExecStart=/usr/bin/python3 -u {runtime}/hdmi_sink.py
Restart=no
KillMode=control-group
TimeoutStopSec=5
UMask=0027
'''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-archive', type=Path, required=True)
    parser.add_argument('--ui-sha256', required=True)
    parser.add_argument('--firefox-archive', type=Path, required=True)
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0: raise RuntimeError('Install requires root')
    if not BASE.is_dir() or not os.path.ismount(BASE.parent): raise RuntimeError('Persistent SD partition not mounted')
    if digest(args.ui_archive) != args.ui_sha256 or digest(args.firefox_archive) != FIREFOX_SHA:
        raise ValueError('Archive checksum mismatch')
    root, firefox = BASE/RELEASE, BASE/'firefox-158.0-arm64'
    extract_new(args.ui_archive, root, RELEASE)
    manifest = json.loads((root/'MANIFEST.json').read_text())
    if manifest['release'] != RELEASE or manifest['motion_enabled'] is not False:
        raise ValueError('Unexpected UI manifest')
    for name, expected in manifest['files'].items():
        path = root/'shadow_play'/name
        if not path.resolve().is_relative_to((root/'shadow_play').resolve()) or digest(path) != expected:
            raise ValueError('Installed file mismatch: '+name)
    extract_new(args.firefox_archive, firefox, 'firefox')
    unit_folder = root/'units'
    unit_folder.mkdir()
    for name, text in units(root, firefox).items():
        (unit_folder/name).write_text(text)
    # /etc belongs to the RAM rootfs on this board. Keep a repeatable launcher
    # on SD; do not imply systemctl enable survives reboot or rewrite image.ub.
    launcher = root/'start-software.sh'
    launcher.write_text(f'''#!/bin/sh
set -eu
for name in shadow-theatre-ui-r4.service shadow-theatre-browser-r4.service shadow-theatre-hdmi-r4.service; do
  source="{unit_folder}/$name"
  target="/etc/systemd/system/$name"
  if test -e "$target" || test -L "$target"; then
    test "$(readlink "$target")" = "$source" || {{ echo "Different existing unit: $name" >&2; exit 1; }}
  else
    ln -s "$source" "$target"
  fi
done
systemctl daemon-reload
systemctl start shadow-theatre-ui-r4.service shadow-theatre-browser-r4.service
if test -e /run/shadow-pwm-loaded.json; then
  systemctl start shadow-theatre-hdmi-r4.service
else
  echo 'UI renderer started. HDMI needs the independently verified runtime image.'
fi
''')
    launcher.chmod(0o755)
    result = dict(release=RELEASE, installed_files=len(manifest['files']), firefox_sha256=FIREFOX_SHA,
                  ui_archive_sha256=args.ui_sha256, motors_enabled=False, boot_files_changed=False,
                  boot_autostart=False, hdmi_started=False)
    if args.activate:
        for name in units(root, firefox):
            path = Path('/etc/systemd/system')/name
            if path.exists() or path.is_symlink(): raise FileExistsError(str(path))
            path.symlink_to(unit_folder/name)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'start', 'shadow-theatre-ui-r4.service', 'shadow-theatre-browser-r4.service'], check=True)
        result['activation_requested'] = True
    (root/'INSTALLATION.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
