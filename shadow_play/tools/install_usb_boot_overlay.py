"""Install the reviewed USB-only U-Boot overlay with source checks and backup.

Does not replace BOOT.BIN/image.ub, reload PL, reboot, or issue motor commands.
Requires the USB FSBL previously verified on this board. Changes take effect at boot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

BOOT_SHA = '32dd1cd32f9675a4c9acaafe330f8e7a7853f1766637a117cf2b57bd536fe55f'
IMAGE_SHA = '0405950d4896f2b9f549ba03664d9fc746ff1c1150ae8aca608cc950c6727dcc'
OLD_ENV_SHA = '93e89d104c9f930009afab056bbca244bb80864ef1972868a283dc540bcef466'
OVERLAY_SHA = '80ffef7773fc79e1f46e98457de94e867bf99c406aadc9a0c531f430d1ec6b79'
ENV_SHA = 'c7c1db61b2dfac2bb6dad137a7d2f041345ff98eb76b4d594a1431918e800770'
OVERLAY_NAME = 'piying-usb2-20261010.dtbo'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_new(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != data:
        raise IOError('Read-back failed: '+str(path))


def install(boot, overlay, env, apply=False):
    for name, expected in (('BOOT.BIN', BOOT_SHA), ('image.ub', IMAGE_SHA)):
        if sha((boot/name).read_bytes()) != expected:
            raise ValueError('Unexpected active '+name)
    if sha(overlay) != OVERLAY_SHA:
        raise ValueError('Unreviewed USB overlay')
    if sha(env) != ENV_SHA:
        raise ValueError('Unreviewed USB environment')
    active = boot/'uEnv.txt'
    original = active.read_bytes()
    target = boot/OVERLAY_NAME
    backup = boot/'uEnv-before-usb-20261010.txt'
    if original == env:
        if (not target.exists() or target.read_bytes() != overlay or
                not backup.exists() or sha(backup.read_bytes()) != OLD_ENV_SHA):
            raise ValueError('Existing installation is incomplete')
        return 'ALREADY_INSTALLED'
    if sha(original) != OLD_ENV_SHA:
        raise ValueError('Active uEnv.txt changed; refusing to overwrite')
    for path, data in ((backup, original), (target, overlay)):
        if path.exists() and path.read_bytes() != data:
            raise ValueError('Existing file differs: '+str(path))
    temporary = boot/'uEnv.usb-new.txt'
    if temporary.exists():
        raise ValueError('Unfinished installation: '+str(temporary))
    if not apply:
        return 'PREFLIGHT_OK'
    for path, data in ((backup, original), (target, overlay)):
        if not path.exists():
            write_new(path, data)
    write_new(temporary, env)
    os.replace(temporary, active)
    if active.read_bytes() != env:
        raise IOError('Active environment verification failed; backup retained')
    return 'INSTALLED_REBOOT_REQUIRED'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-dir', type=Path, default=Path('/run/media/mmcblk0p1'))
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    result = install(args.boot_dir, args.overlay.read_bytes(), args.env.read_bytes(), args.install)
    if args.install: os.sync()
    print(json.dumps(dict(result=result, boot_dir=str(args.boot_dir))))


if __name__ == '__main__':
    main()
