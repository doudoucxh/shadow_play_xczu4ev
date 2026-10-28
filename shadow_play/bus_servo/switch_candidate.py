"""Switch between verified bus layouts with actuators off; never resume an attempt."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import subprocess
import time

from .layouts import BASE, manifest_layout
from .load_candidate import digest, verify


def idle_state(read, layout):
    state = dict(identity=read(0), version=read(4), faults=read(8), lease=read(16),
                 clock_hz=read(0x18), baudrate=read(0x1c),
                 buses={n:read(off) for n,off in layout.offsets.items()})
    if layout.name != 'dual': state['channels']=read(0x24)
    if (state['identity']!=layout.word or state['version']!=1 or state['faults'] or state['lease']
            or state['clock_hz']!=100000000 or state['baudrate']!=115200
            or any(state['buses'].values())
            or (layout.name!='dual' and state['channels']!=len(layout.buses))):
        raise RuntimeError('Expected clean idle bus state not present; no FIFO discard or fault clear')
    return state


def validate_source(marker, previous, boot_id, expected_sha):
    layout = manifest_layout(previous)
    if (manifest_layout(marker)!=layout or marker.get('boot_id')!=boot_id
            or marker.get('sha256')!=expected_sha or previous.get('sha256')!=expected_sha):
        raise RuntimeError('Source bus marker, boot or image differs from the reviewed state')
    return layout


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--previous-manifest',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--all-actuator-power-off-confirmed',action='store_true')
    p.add_argument('--boot-id')
    p.add_argument('--previous-image-sha')
    p.add_argument('--current-marker-sha')
    args=p.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    target=verify(args.image,manifest)
    previous=json.loads(args.previous_manifest.read_text(encoding='utf-8'))
    source=manifest_layout(previous)
    if source==target:raise ValueError('Use a separately reviewed reload procedure for the same layout')
    if not args.execute:
        print('BUS_SWITCH_OFFLINE_VALIDATED; no hardware access');return
    if not all((args.all_actuator_power_off_confirmed,args.boot_id,args.previous_image_sha,args.current_marker_sha)):
        raise ValueError('Current physical power-off, boot ID, source image and marker hashes required')
    if os.geteuid()!=0:raise RuntimeError('Root required')
    import fcntl
    from ..integrations.calibration.mmio32 import WordAccess
    marker_path=Path('/run/shadow-bus-servo-loaded.json')
    raw=marker_path.read_bytes();old=json.loads(raw)
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot_id!=args.boot_id or hashlib.sha256(raw).hexdigest()!=args.current_marker_sha:
        raise RuntimeError('Current boot or marker changed')
    source=validate_source(old,previous,boot_id,args.previous_image_sha)
    attempt=Path('/run/shadow-bus-servo-switch-'+target.identity+'.json')
    backup=Path('/run/shadow-bus-servo-before-'+target.identity+'.json')
    if attempt.exists() or backup.exists():raise RuntimeError('Switch attempt already consumed; never delete and rerun')
    incident=Path('/run/shadow-pwm-motion-inhibit')
    boot=Path('/run/media/mmcblk0p1')
    boot_hashes={n:digest(boot/n) for n in ('BOOT.BIN','image.ub','boot.scr','uEnv.txt')}
    incident_sha=digest(incident)
    if boot_hashes!=old['boot_hashes'] or incident_sha!=old['incident_sha256']:
        raise RuntimeError('Boot files or incident lock changed')
    def read_state(layout):
        fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:
            with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=BASE) as memory:
                words=WordAccess(memory)
                try:return idle_state(words.read,layout)
                finally:words.close()
        finally:os.close(fd)
    with open('/run/shadow-pwm.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=read_state(source)
        if before!=read_state(source):raise RuntimeError('Source state changed')
        busy=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
            try:
                if any(s in (proc/'maps').read_text() for s in ('/dev/mem','/dev/dpu','/dev/video')):busy.append(proc.name)
            except (FileNotFoundError,PermissionError,ProcessLookupError):pass
        if busy:raise RuntimeError('Stop reviewed PL consumers first: '+','.join(busy))
        if marker_path.read_bytes()!=raw:raise RuntimeError('Source marker changed')
        with attempt.open('x') as f:
            json.dump(dict(boot_id=boot_id,source_sha=args.previous_image_sha,target_sha=manifest['sha256'],
                           source_marker_sha=args.current_marker_sha,before=before,attempt_unix=time.time()),f)
            f.flush();os.fsync(f.fileno())
        marker_path.rename(backup)
        subprocess.run(['fpgautil','-b',str(args.image.resolve()),'-f','Full'],check=True,timeout=60)
        if Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()!='operating':
            raise RuntimeError('FPGA manager not operating; no automatic reload or rollback')
        after=read_state(target)
        if after!=read_state(target):raise RuntimeError('Candidate reset state changed')
        if digest(incident)!=incident_sha or any(digest(boot/n)!=h for n,h in boot_hashes.items()):
            raise RuntimeError('Boot files or incident lock changed during switch')
        if digest(backup)!=args.current_marker_sha:raise RuntimeError('Source backup changed')
        record=dict(manifest,boot_id=boot_id,loaded_unix=time.time(),boot_hashes=boot_hashes,
                    incident_sha256=incident_sha,previous_layout=source.name,previous_sha=args.previous_image_sha,
                    switch_attempt=str(attempt),scope='volatile bus layout switch; no servo packets sent')
        with marker_path.open('x') as f:json.dump(record,f,indent=2)
    print('BUS_SWITCH_LOADED_RX_IDLE_NO_PACKETS '+json.dumps(after),flush=True)


if __name__=='__main__':main()
