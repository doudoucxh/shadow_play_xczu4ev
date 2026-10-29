"""Build/install an independently checked BS10 startup FIT. Run on the board.

No PL loading or actuator command is issued by this installer. Installation
changes the next boot selection only, after verifying a separately named FIT.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

try:
    from .install_ui_autostart import cpio, digest, write_new, ITS, PART_SHA
except ImportError:
    from install_ui_autostart import cpio, digest, write_new, ITS, PART_SHA

BOOT = Path('/run/media/mmcblk0p1')
WORK = Path('/run/media/mmcblk0p2/piying/boot-bus-20261029')
NAME = 'image-bus-20261029.ub'
EXPECTED = {
    'BOOT.BIN': '32dd1cd32f9675a4c9acaafe330f8e7a7853f1766637a117cf2b57bd536fe55f',
    'image.ub': '0405950d4896f2b9f549ba03664d9fc746ff1c1150ae8aca608cc950c6727dcc',
    'boot.scr': '9ada4d88212468c12d2710b0fae35df42c4c72134bafa82b2ae5aca82570a7f1',
    'uEnv.txt': '9d69a9577cad6d2ce87591bd4d125fe90c543dce3ca05ecc248056ccaa6e6ba8',
    'image-ui-20261018.ub': 'df660e3aa4d3262cbe61db2236910392b92dd554fa60e2672c2cdf8335cd0b9b',
}
OLD_BACKUP = 'image.ub.previous-20260922_205145'
OLD_BACKUP_SHA = 'a3d935db943f9db98ed0b105c0dc52dda04e2e924a27b5849e08e6cad021811e'


def new_environment(original):
    old = b'fatload mmc 0:1 0x10000000 image-ui-20261018.ub && bootm start'
    if original.count(old) != 1:
        raise ValueError('Unexpected active boot selection')
    return original.replace(old, b'fatload mmc 0:1 0x10000000 '+NAME.encode()+b' && bootm start')


def bootstrap(launcher_sha):
    return f'''import hashlib, os, subprocess, time
from pathlib import Path
mount = Path('/run/media/mmcblk0p2')
launcher = mount/'piying/boot-bus-20261029/launch.py'
deadline = time.monotonic()+80
while not (os.path.ismount(mount) and launcher.is_file()):
    if time.monotonic() >= deadline: raise RuntimeError('SD runtime not ready')
    time.sleep(.25)
if hashlib.sha256(launcher.read_bytes()).hexdigest() != '{launcher_sha}':
    raise RuntimeError('SD launcher checksum mismatch')
subprocess.run(['/usr/bin/python3', '-u', str(launcher), '--execute-cold-boot'], check=True, timeout=170)
'''.encode()


def overlay(source):
    dirs = ('etc', 'etc/systemd', 'etc/systemd/system',
            'etc/systemd/system/multi-user.target.wants', 'usr', 'usr/local', 'usr/local/lib')
    entries = [(name, stat.S_IFDIR | 0o755, b'') for name in dirs]
    entries.extend([
        ('usr/local/lib/shadow-theatre-bootstrap.py', stat.S_IFREG | 0o644,
         bootstrap(digest(source/'launch.py'))),
        ('etc/systemd/system/shadow-theatre-boot.service', stat.S_IFREG | 0o644,
         (source/'shadow-theatre-boot.service').read_bytes()),
        ('etc/systemd/system/multi-user.target.wants/shadow-theatre-boot.service',
         stat.S_IFLNK | 0o777, b'../shadow-theatre-boot.service'),
    ])
    for name in ('shadow-video', 'shadow-yolo-follow', 'shadow-yolo-pose', 'shadow-arm-chain', 'shadow-hw-init'):
        entries.append(('etc/systemd/system/'+name+'.service', stat.S_IFLNK | 0o777, b'/dev/null'))
    return gzip.compress(cpio(entries), mtime=0)


def copy_new(source, destination):
    with source.open('rb') as inp, destination.open('xb') as out:
        shutil.copyfileobj(inp, out)
        out.flush()
        os.fsync(out.fileno())
    if digest(source) != digest(destination):
        raise RuntimeError('Copy verification failed: '+str(destination))


def archive_inactive_backup():
    source = BOOT/OLD_BACKUP
    target = WORK/OLD_BACKUP
    if OLD_BACKUP.encode() in (BOOT/'uEnv.txt').read_bytes() or digest(source) != OLD_BACKUP_SHA:
        raise RuntimeError('Inactive backup identity/reference changed')
    copy_new(source, target)
    os.sync()
    if digest(target) != OLD_BACKUP_SHA or digest(source) != OLD_BACKUP_SHA:
        raise RuntimeError('Archive hash mismatch')
    # Only this exact, inactive, independently verified backup is removed from FAT.
    source.unlink()
    os.sync()
    return dict(source=str(source), backup=str(target), sha256=OLD_BACKUP_SHA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--archive-known-old-backup', action='store_true')
    args = parser.parse_args()
    if not os.path.ismount(BOOT) or not os.path.ismount(WORK.parents[1]):
        raise RuntimeError('Both SD partitions required')
    for name, expected in EXPECTED.items():
        if digest(BOOT/name) != expected:
            raise RuntimeError('Unexpected active boot file: '+name)
    # Validate the installed runtime without opening hardware before changing boot.
    subprocess.run(['/usr/bin/python3', str(args.source/'launch.py')], check=True, timeout=30)
    WORK.mkdir()  # Never overwrite a prior attempt.
    candidate = WORK/NAME
    for index, name in enumerate(('kernel', 'fdt', 'original-ramdisk')):
        subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(WORK/name), str(BOOT/'image.ub')],
                       check=True, stdout=subprocess.DEVNULL)
        if digest(WORK/name) != PART_SHA[index]:
            raise RuntimeError('Original FIT component mismatch')
    with gzip.open(WORK/'original-ramdisk', 'rb') as inp:
        if inp.read(6) != b'070701':
            raise RuntimeError('Original initramfs is not newc')
    patch = overlay(args.source)
    write_new(WORK/'overlay.cpio.gz', patch)
    with (WORK/'ramdisk-ui').open('xb') as out, (WORK/'original-ramdisk').open('rb') as inp:
        shutil.copyfileobj(inp, out)
        out.write(patch)
    (WORK/'boot.its').write_text(ITS.replace('automatic SD homepage', 'idle BS10 dual bus startup'))
    subprocess.run(['mkimage', '-f', 'boot.its', NAME], cwd=WORK, check=True)
    for index, name in enumerate(('kernel', 'fdt', 'ramdisk-ui')):
        output = WORK/('verify-'+name)
        subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(output), str(candidate)],
                       check=True, stdout=subprocess.DEVNULL)
        if digest(output) != digest(WORK/name):
            raise RuntimeError('Candidate component changed: '+name)
    copy_new(args.source/'launch.py', WORK/'launch.py')
    original_env = (BOOT/'uEnv.txt').read_bytes()
    env = new_environment(original_env)
    record = dict(original=EXPECTED, candidate=NAME, candidate_sha256=digest(candidate),
                  kernel_sha256=PART_SHA[0], fdt_sha256=PART_SHA[1],
                  launcher_sha256=digest(WORK/'launch.py'), overlay_sha256=hashlib.sha256(patch).hexdigest(),
                  new_uenv_sha256=hashlib.sha256(env).hexdigest(), installed=False,
                  automatic_start=True, servo_packets_on_boot=0, motion_enabled=False)
    if args.install:
        if args.archive_known_old_backup:
            record['archived_inactive_backup'] = archive_inactive_backup()
        if shutil.disk_usage(BOOT).free < candidate.stat().st_size+8*1024*1024:
            raise RuntimeError('Insufficient boot partition space')
        for name, expected in EXPECTED.items():
            if digest(BOOT/name) != expected:
                raise RuntimeError('Boot source changed during build')
        if (BOOT/NAME).exists():
            raise FileExistsError('Candidate already on boot partition')
        write_new(WORK/'uEnv-before-bus-20261029.txt', original_env)
        write_new(BOOT/'uEnv-before-bus-20261029.txt', original_env)
        copy_new(candidate, BOOT/(NAME+'.tmp'))
        os.replace(BOOT/(NAME+'.tmp'), BOOT/NAME)
        write_new(BOOT/'uEnv.bus-tmp.txt', env)
        os.sync()
        os.replace(BOOT/'uEnv.bus-tmp.txt', BOOT/'uEnv.txt')
        os.sync()
        if digest(BOOT/'uEnv.txt') != record['new_uenv_sha256']:
            raise RuntimeError('Environment mismatch; backups retained')
        record['installed'] = True
    (WORK/'INSTALLATION.json').write_text(json.dumps(record, indent=2)+'\n')
    os.sync()
    print('BUS_BOOT_INSTALLATION '+json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
