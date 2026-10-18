"""Package/install an isolated manual initialization service; never start it."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

RELEASE='servo-initial-pose-20261018'
DEST=Path('/run/media/mmcblk0p2/piying')/RELEASE
NAMES=('initial_pose_console.py','initial_pose_model.py','attended_center_console.py',
       'center_console.py','board_server.py','tcp_bridge.py','servo_pwm_device.py',
       'mmio32.py','libservo_mmio32.so')
PREFIX='integrations/calibration/'


def sha(data):return hashlib.sha256(data).hexdigest()


def build(output):
    source=Path(__file__).resolve().parents[1]/'integrations/calibration'
    files={PREFIX+n:(source/n).read_bytes() for n in NAMES}
    files[PREFIX+'.motion-inhibit']=b'Manual initial-angle application only; ordinary motion remains inhibited.\n'
    manifest=dict(release=RELEASE,files={n:sha(b) for n,b in files.items()},autostart=False)
    files['MANIFEST.json']=json.dumps(manifest,indent=2).encode()
    with tarfile.open(output,'x:gz') as archive:
        for name,data in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644
            archive.addfile(entry,io.BytesIO(data))
    print(json.dumps(dict(archive=str(output),sha256=sha(output.read_bytes()))))


def install(archive,expected):
    raw=archive.read_bytes()
    if sha(raw)!=expected:raise ValueError('Archive checksum mismatch')
    files={};allowed={PREFIX+n for n in NAMES}|{PREFIX+'.motion-inhibit','MANIFEST.json'}
    with tarfile.open(fileobj=io.BytesIO(raw)) as source:
        for entry in source:
            if entry.name not in allowed or entry.name in files or not entry.isfile() or not 0<entry.size<256*1024:
                raise ValueError('Unexpected service member')
            files[entry.name]=source.extractfile(entry).read()
    if set(files)!=allowed:raise ValueError('Incomplete service bundle')
    manifest=json.loads(files['MANIFEST.json'])
    if manifest['release']!=RELEASE or set(manifest['files'])!=allowed-{'MANIFEST.json'}:
        raise ValueError('Wrong service manifest')
    for name,expected_hash in manifest['files'].items():
        if sha(files[name])!=expected_hash:raise ValueError('File checksum mismatch: '+name)
        if name.endswith('.py'):compile(files[name],name,'exec')
    if not os.path.ismount(DEST.parent.parent):raise RuntimeError('Persistent SD partition is not mounted')
    if DEST.exists():
        if any(not (DEST/n).is_file() or sha((DEST/n).read_bytes())!=sha(data) for n,data in files.items()):
            raise FileExistsError('Different installation already exists; preserve it for review')
        print('ALREADY_INSTALLED_NO_SERVICE_STARTED');return
    DEST.mkdir()
    for name,data in files.items():
        path=DEST/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    os.sync()
    if any(sha((DEST/n).read_bytes())!=sha(data) for n,data in files.items()):raise RuntimeError('Installed checksum mismatch')
    print(json.dumps(dict(installed=str(DEST),files=len(manifest['files']),service_started=False,motor_commands_sent=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='mode',required=True)
    b=s.add_parser('build');b.add_argument('archive',type=Path)
    i=s.add_parser('install');i.add_argument('archive',type=Path);i.add_argument('--sha256',required=True)
    args=p.parse_args()
    if args.mode=='build':build(args.archive)
    else:install(args.archive,args.sha256)
