"""Validate a bus candidate offline; an explicit execute loads volatile PL only."""
import argparse
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import subprocess
import time

from .layouts import BASE, manifest_layout


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(image, manifest):
    layout = manifest_layout(manifest)
    if (manifest.get('sha256') != digest(image)
            or any(type(manifest.get(k)) not in (int,float) or not math.isfinite(manifest[k]) or manifest[k]<0
                   for k in ('wns_ns','whs_ns','wpws_ns'))):
        raise ValueError('Candidate checks/identity/image hash mismatch')
    return layout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--all-actuator-power-off-confirmed',action='store_true')
    parser.add_argument('--boot-id')
    parser.add_argument('--previous-image-sha')
    parser.add_argument('--expected-off-sequence',type=int)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    layout=verify(args.image,manifest)
    if not args.execute:
        print('BUS_CANDIDATE_OFFLINE_VALIDATED; hardware was not opened')
        return
    if (not args.all_actuator_power_off_confirmed or args.expected_off_sequence is None
            or not args.boot_id or not args.previous_image_sha):
        raise ValueError('Current physical power-off, boot ID, previous image hash and OFF sequence required')
    if os.geteuid()!=0:
        raise RuntimeError('Root required')
    from ..integrations.calibration.mmio32 import WordAccess
    import fcntl
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    old_path=Path('/run/shadow-pwm-loaded.json')
    old_bytes=old_path.read_bytes();old=json.loads(old_bytes)
    attempt=Path('/run/shadow-bus-servo-load-attempt.json')
    new_marker=Path('/run/shadow-bus-servo-loaded.json')
    if (boot_id!=args.boot_id or old.get('sha256')!=args.previous_image_sha
            or old.get('boot_id')!=boot_id or old.get('register_base')!=0xA0030000
            or old.get('image_kind')!='servo10_vision' or attempt.exists() or new_marker.exists()):
        raise RuntimeError('Current boot/image changed or load attempt already consumed')
    incident=Path('/run/shadow-pwm-motion-inhibit')
    incident_sha=digest(incident)
    boot=Path('/run/media/mmcblk0p1')
    boot_hashes={name:digest(boot/name) for name in ('BOOT.BIN','image.ub','boot.scr','uEnv.txt')}
    with open('/run/shadow-pwm.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with mmap.mmap(-1,4096) as scratch:
            words=WordAccess(scratch)
            try:
                words.write(0,layout.word)
                if words.read(0)!=layout.word:raise RuntimeError('Native 32-bit access self-test failed')
            finally:words.close()
        fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:
            with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA0030000) as memory:
                words=WordAccess(memory)
                try:
                    for _ in range(2):
                        if (words.read(0)!=0x53503130 or words.read(8)!=0 or words.read(12)!=0
                                or words.read(16)!=0 or words.read(0x24)!=0 or words.read(0x20)!=args.expected_off_sequence):
                            raise RuntimeError('Expected clean SP10 OFF state not present')
                finally:words.close()
        finally:os.close(fd)
        busy=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
            try:
                if any(name in (proc/'maps').read_text() for name in ('/dev/mem','/dev/dpu','/dev/video')):busy.append(proc.name)
            except (FileNotFoundError,PermissionError,ProcessLookupError):pass
        if busy:
            raise RuntimeError('Stop reviewed PL consumers first; mapped process IDs: '+','.join(busy))
        if old_path.read_bytes()!=old_bytes or digest(incident)!=incident_sha:
            raise RuntimeError('Preflight state changed')
        with attempt.open('x') as stream:
            json.dump({'boot_id':boot_id,'previous_sha':args.previous_image_sha,'candidate_sha':manifest['sha256'],'attempt_unix':time.time()},stream)
        backup=Path('/run/shadow-pwm-before-bus-servo.json')
        if backup.exists():raise RuntimeError('Previous marker backup already exists')
        old_path.rename(backup)
        # No retry or automatic rollback after an uncertain programming result.
        subprocess.run(['fpgautil','-b',str(args.image.resolve()),'-f','Full'],check=True,timeout=60)
        if Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()!='operating':
            raise RuntimeError('FPGA manager is not operating')
        fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:
            with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=BASE) as memory:
                words=WordAccess(memory)
                try:
                    if (words.read(0)!=layout.word or words.read(4)!=1 or words.read(8)!=0 or words.read(16)!=0
                            or words.read(0x18)!=100000000 or words.read(0x1c)!=115200
                            or any(words.read(offset)!=0 for offset in layout.offsets.values())
                            or (layout.name!='dual' and words.read(0x24)!=len(layout.buses))):
                        raise RuntimeError('Unexpected bus candidate reset state')
                finally:words.close()
        finally:os.close(fd)
        if digest(incident)!=incident_sha or any(digest(boot/name)!=sha for name,sha in boot_hashes.items()):
            raise RuntimeError('Incident or boot hashes changed')
        record=dict(manifest,boot_id=boot_id,loaded_unix=time.time(),boot_hashes=boot_hashes,
                    incident_sha256=incident_sha,scope='volatile candidate; no servo packets sent')
        with new_marker.open('x') as stream:json.dump(record,stream,indent=2)
    print('BUS_CANDIDATE_LOADED_RX_IDLE_NO_PACKETS')


if __name__=='__main__':main()
