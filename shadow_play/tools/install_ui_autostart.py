"""Build a separate FIT with an additive initramfs startup overlay; opt-in install.

Keeps BOOT.BIN, image.ub and USB overlay intact. Only the reviewed uEnv load
filename changes. Run on the board with the boot_ui source directory alongside.
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

BOOT = Path('/run/media/mmcblk0p1')
WORK = Path('/run/media/mmcblk0p2/piying/boot-ui-20261018')
NAME = 'image-ui-20261018.ub'
EXPECTED = {
    'BOOT.BIN': '32dd1cd32f9675a4c9acaafe330f8e7a7853f1766637a117cf2b57bd536fe55f',
    'image.ub': '0405950d4896f2b9f549ba03664d9fc746ff1c1150ae8aca608cc950c6727dcc',
    'boot.scr': '9ada4d88212468c12d2710b0fae35df42c4c72134bafa82b2ae5aca82570a7f1',
    'uEnv.txt': 'c7c1db61b2dfac2bb6dad137a7d2f041345ff98eb76b4d594a1431918e800770',
}
PART_SHA = [
    '29bbb9db5228855b3657f63cae0d17a641b4963c9f9f5c1e8f6b6119986813fa',
    'f380f2125ed3fd8ab2416ca0f22844074c32bb6532dd2d1b42406c1a49ec6e8b',
    'e1ffbe1369ab895eceecb59c2fbcfaa10a6fc7e6617466ac68b1665ed57972c5',
]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def cpio(entries):
    """Small deterministic newc archive; entries are (path, mode, bytes)."""
    result = bytearray()
    for number, (name, mode, data) in enumerate([*entries, ('TRAILER!!!', 0, b'')], 1):
        if name.startswith('/') or '..' in Path(name).parts or '\\' in name:
            raise ValueError('Unsafe archive path')
        encoded = name.encode()+b'\0'
        fields = [number, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
        result += b'070701'+''.join('%08x' % x for x in fields).encode()+encoded
        result += b'\0'*(-len(result) % 4)
        result += data
        result += b'\0'*(-len(result) % 4)
    result += b'\0'*(-len(result) % 512)
    return bytes(result)


def new_environment(original):
    old = b'fatload mmc 0:1 0x10000000 image.ub && bootm start'
    if original.count(old) != 1:
        raise ValueError('Unexpected U-Boot load entry')
    return original.replace(old, b'fatload mmc 0:1 0x10000000 '+NAME.encode()+b' && bootm start')


def bootstrap(launcher_sha):
    return f'''import hashlib, os, subprocess, time
from pathlib import Path
mount = Path('/run/media/mmcblk0p2')
launcher = mount/'piying/boot-ui-20261018/launch.py'
deadline = time.monotonic()+80
while not (os.path.ismount(mount) and launcher.is_file()):
    if time.monotonic() >= deadline: raise RuntimeError('SD runtime not ready')
    time.sleep(.25)
if hashlib.sha256(launcher.read_bytes()).hexdigest() != '{launcher_sha}':
    raise RuntimeError('SD launcher checksum mismatch')
subprocess.run(['/usr/bin/python3', '-u', str(launcher)], check=True, timeout=150)
'''.encode()


def overlay(source):
    launch = (source/'launch.py').read_bytes()
    dirs = ['etc', 'etc/systemd', 'etc/systemd/system',
            'etc/systemd/system/multi-user.target.wants', 'usr', 'usr/local', 'usr/local/lib']
    entries = [(d, stat.S_IFDIR | 0o755, b'') for d in dirs]
    entries += [('usr/local/lib/shadow-theatre-bootstrap.py', stat.S_IFREG | 0o644,
                 bootstrap(hashlib.sha256(launch).hexdigest())),
                ('etc/systemd/system/shadow-theatre-boot.service', stat.S_IFREG | 0o644,
                 (source/'shadow-theatre-boot.service').read_bytes()),
                ('etc/systemd/system/multi-user.target.wants/shadow-theatre-boot.service',
                 stat.S_IFLNK | 0o777, b'../shadow-theatre-boot.service')]
    for name in ('shadow-video', 'shadow-yolo-follow', 'shadow-yolo-pose', 'shadow-arm-chain', 'shadow-hw-init'):
        entries.append(('etc/systemd/system/'+name+'.service', stat.S_IFLNK | 0o777, b'/dev/null'))
    return gzip.compress(cpio(entries), mtime=0)


ITS = '''/dts-v1/;
/ {
 description = "Shadow theatre automatic SD homepage";
 #address-cells = <1>;
 images {
  kernel-1 { description = "Unchanged Linux kernel"; data = /incbin/("kernel");
   type = "kernel"; arch = "arm64"; os = "linux"; compression = "gzip";
   load = <0x00200000>; entry = <0x00200000>; hash-1 { algo = "sha256"; }; };
  fdt-system-top.dtb { description = "Unchanged board device tree"; data = /incbin/("fdt");
   type = "flat_dt"; arch = "arm64"; compression = "none"; hash-1 { algo = "sha256"; }; };
  ramdisk-1 { description = "Original initramfs plus UI boot overlay"; data = /incbin/("ramdisk-ui");
   type = "ramdisk"; arch = "arm64"; os = "linux"; compression = "none"; hash-1 { algo = "sha256"; }; };
 };
 configurations { default = "conf-system-top.dtb";
  conf-system-top.dtb { description = "Linux, FDT and UI startup";
   kernel = "kernel-1"; fdt = "fdt-system-top.dtb"; ramdisk = "ramdisk-1"; };
 };
};
'''


def write_new(path, data):
    with path.open('xb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if not os.path.ismount(BOOT) or not os.path.ismount(WORK.parents[1]):
        raise RuntimeError('SD partitions must be mounted')
    for name, expected in EXPECTED.items():
        if digest(BOOT/name) != expected:
            raise RuntimeError('Unexpected active boot file: '+name)
    WORK.mkdir(exist_ok=True)
    candidate = WORK/NAME
    if candidate.exists():
        raise FileExistsError('Candidate already exists; inspect before rebuilding')
    for index, name in enumerate(('kernel', 'fdt', 'original-ramdisk')):
        output = WORK/name
        subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(output), str(BOOT/'image.ub')],
                       check=True, stdout=subprocess.DEVNULL)
        if digest(output) != PART_SHA[index]:
            raise RuntimeError('Original FIT component mismatch')
    with gzip.open(WORK/'original-ramdisk', 'rb') as original:
        if original.read(6) != b'070701':
            raise RuntimeError('Not a newc initramfs')
    patch = overlay(args.source)
    (WORK/'overlay.cpio.gz').write_bytes(patch)
    with (WORK/'ramdisk-ui').open('xb') as out, (WORK/'original-ramdisk').open('rb') as old:
        shutil.copyfileobj(old, out)
        out.write(patch)
    (WORK/'boot.its').write_text(ITS)
    subprocess.run(['mkimage', '-f', 'boot.its', NAME], cwd=WORK, check=True)
    for index, name in enumerate(('kernel', 'fdt', 'ramdisk-ui')):
        output = WORK/('verify-'+name)
        subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(output), str(candidate)],
                       check=True, stdout=subprocess.DEVNULL)
        if digest(output) != digest(WORK/name):
            raise RuntimeError('Candidate component changed: '+name)
    shutil.copyfile(args.source/'launch.py', WORK/'launch.py')
    original_env = (BOOT/'uEnv.txt').read_bytes()
    env = new_environment(original_env)
    record = dict(original=EXPECTED, candidate=NAME, candidate_sha256=digest(candidate),
                  kernel_sha256=PART_SHA[0], fdt_sha256=PART_SHA[1],
                  launcher_sha256=digest(WORK/'launch.py'),
                  overlay_sha256=hashlib.sha256(patch).hexdigest(),
                  new_uenv_sha256=hashlib.sha256(env).hexdigest(), installed=False)
    if args.install:
        if shutil.disk_usage(BOOT).free < candidate.stat().st_size+8*1024*1024:
            raise RuntimeError('Boot partition lacks candidate space; preserve backups before retrying')
        backup = BOOT/'uEnv-before-ui-20261018.txt'
        if backup.exists() or (BOOT/NAME).exists():
            raise FileExistsError('Prior UI boot installation exists')
        write_new(backup, original_env)
        with candidate.open('rb') as src, (BOOT/(NAME+'.tmp')).open('xb') as dest:
            shutil.copyfileobj(src, dest)
            dest.flush()
            os.fsync(dest.fileno())
        if digest(BOOT/(NAME+'.tmp')) != record['candidate_sha256']:
            raise RuntimeError('SD candidate copy mismatch')
        os.replace(BOOT/(NAME+'.tmp'), BOOT/NAME)
        write_new(BOOT/'uEnv.ui-tmp.txt', env)
        os.sync()
        os.replace(BOOT/'uEnv.ui-tmp.txt', BOOT/'uEnv.txt')
        os.sync()
        if digest(BOOT/'uEnv.txt') != record['new_uenv_sha256']:
            raise RuntimeError('Active environment mismatch; backup retained')
        record['installed'] = True
    (WORK/'INSTALLATION.json').write_text(json.dumps(record, indent=2)+'\n')
    print('UI_BOOT_CANDIDATE '+json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
