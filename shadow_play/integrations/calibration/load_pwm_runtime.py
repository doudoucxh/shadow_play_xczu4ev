#!/usr/bin/env python3
"""Load the reviewed servo10+vision image into volatile PL, with motors off.

No overlays, device-driver unbinding, SD writes, or boot configuration edits.
Reboot returns to the existing SD image. This is a commissioning deployment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from servo_pwm_device import BASE, PINS, PwmDevice, Registers


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--servo-power-off-confirmed',required=True,action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0: raise RuntimeError('Root required')
    manifest=json.loads(args.manifest.read_text())
    if (manifest.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS' or
        manifest.get('bus_skew_check')!='SERVO_BUS_SKEW_CHECK_PASS' or
        manifest.get('image_kind')!='servo10_vision' or manifest.get('register_base')!=BASE or
        manifest.get('pins')!=list(PINS) or manifest.get('sha256')!=digest(args.image)):
        raise RuntimeError('Reviewed manifest/image identity mismatch')
    if not manifest.get('wns_ns',-1)>=0 or not manifest.get('whs_ns',-1)>=0:
        raise RuntimeError('Timing has not been verified')
    # Confirm the native access library works against ordinary RAM before PL
    # reconfiguration. This does not open any device or emit a PWM pulse.
    import mmap
    from mmio32 import WordAccess
    with mmap.mmap(-1,4096) as scratch:
        access=WordAccess(scratch)
        try:
            access.write(12,0x41524d31)
            if access.read(12)!=0x41524d31: raise RuntimeError('MMIO library RAM test failed')
        finally: access.close()
    # Any user process mapping a PL device must exit before full reconfiguration.
    busy=[]
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid(): continue
        try:
            maps=(process/'maps').read_text()
            if any(name in maps for name in ('/dev/mem','/dev/dpu','/dev/video')):
                busy.append(process.name)
        except (FileNotFoundError,ProcessLookupError,PermissionError): pass
    if busy: raise RuntimeError('Device mappings still owned by PIDs: '+','.join(busy))
    import fcntl
    with open('/run/shadow-pwm.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        marker=Path('/run/shadow-pwm-loaded.json')
        if marker.exists(): raise RuntimeError('PWM image already marked loaded; inspect before replacing it')
        boot=Path('/run/media/mmcblk0p1')
        before={p.name:digest(p) for p in boot.iterdir() if p.is_file() and p.name in
                ('BOOT.BIN','image.ub','boot.scr','uEnv.txt')}
        subprocess.run(['fpgautil','-b',str(args.image.resolve()),'-f','Full'],check=True,timeout=45)
        if Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()!='operating':
            raise RuntimeError('FPGA manager did not report operating')
        after={name:digest(boot/name) for name in before}
        if before!=after: raise RuntimeError('Unexpected boot-file hash change')
        record=dict(manifest,loaded_unix=time.time(),boot_hashes=after,
                    scope='volatile runtime image; motors remain off')
        marker.write_text(json.dumps(record,indent=2)+'\n')
    registers=Registers()
    try:
        state=PwmDevice(registers).status()
        if (state['armed'] or state['enabled_mask'] or state['faults'] or state['pending'] or
            state['sequence'] or state['clock_hz']!=100000000):
            PwmDevice(registers).off()
            raise RuntimeError('Unexpected PWM reset state: '+json.dumps(state))
        print(json.dumps({'result':'RUNTIME_IMAGE_LOADED_OUTPUTS_OFF','state':state,
                          'boot_hashes_unchanged':after},indent=2),flush=True)
    finally:
        registers.close()


if __name__=='__main__': main()
