"""Restore the preserved standard UART image after this exact direction trial.

Power-off only; no boot changes, motor packets, or motion-lock removal.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from load_rail_query_candidate import CALIBRATION, digest, verify_candidate
from load_swapped_uart_candidate import STANDARD_SHA
from zdt_uartlite_telemetry import validate_pin_map

TRIAL_SHA='2a6f3675d13254225e4d41abcbdb1d48f347a2bcdba5dbb233abfd155450958e'
STANDARD=Path('/run/media/mmcblk0p2/piying/rail-uart-query-20261019')


def check_identities(current, preserved, boot):
    if (current.get('sha256')!=TRIAL_SHA or preserved.get('sha256')!=STANDARD_SHA or
            current.get('boot_id')!=boot or preserved.get('boot_id')!=boot or
            current.get('uart_pin_swap_trial') is not True):
        raise ValueError('Not the expected trial and preserved standard image in this boot')
    validate_pin_map(current.get('rail_uart',{}),'swapped')


def start_standard_display(boot):
    marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    if (marker.get('sha256')!=STANDARD_SHA or marker.get('boot_id')!=boot or
            Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=boot):
        raise ValueError('Standard display image/boot mismatch')
    bundle=json.loads((STANDARD/'MANIFEST.json').read_text())
    for name in ('shadow_play/integrations/follow/usb_hdmi.py',
                 'shadow_play/hdmi_ui/runtime/hdmi_sink.py',
                 'shadow_play/hdmi_ui/runtime/browser_display.py'):
        if digest(STANDARD/name)!=bundle['files'][name]:
            raise ValueError('Standard display source mismatch')
    # Stopped transient units may be garbage-collected; recreate the service.
    sink=STANDARD/'shadow_play/hdmi_ui/runtime/hdmi_sink.py'
    subprocess.run(['systemd-run','--unit=shadow-uart-restored-hdmi','--property=Restart=no',
                    sys.executable,'-u',str(sink)],check=True,timeout=15)
    time.sleep(1)
    return subprocess.run(['systemctl','is-active','--quiet','shadow-uart-restored-hdmi']).returncode==0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boot-id',required=True)
    p.add_argument('--expected-sequence',type=int,required=True)
    p.add_argument('--execute-restore',action='store_true')
    p.add_argument('--all-actuator-power-off-confirmed',action='store_true')
    args=p.parse_args()
    image=STANDARD/'servo10_dual_uart.bit.bin'
    manifest=STANDARD/'servo10_dual_uart.manifest.json'
    verify_candidate(json.loads(manifest.read_text()),STANDARD_SHA)
    if digest(image)!=STANDARD_SHA:raise ValueError('Preserved image hash mismatch')
    bundle=json.loads((STANDARD/'MANIFEST.json').read_text())
    if bundle.get('image_sha')!=STANDARD_SHA or bundle.get('motion_enabled') is not False:
        raise ValueError('Preserved bundle identity mismatch')
    for name,expected in bundle['files'].items():
        original=STANDARD/name;member=original.resolve()
        if original.is_symlink() or not member.is_relative_to(STANDARD.resolve()) or digest(member)!=expected:
            raise ValueError('Preserved bundle hash mismatch: '+name)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker=Path('/run/shadow-pwm-loaded.json')
    old_raw=marker.read_bytes();old=json.loads(old_raw)
    preserved=json.loads(Path('/run/shadow-pwm-before-uart-swap-20261019.json').read_text())
    if boot!=args.boot_id:raise ValueError('Boot changed')
    check_identities(old,preserved,boot)
    backup=Path('/run/shadow-pwm-after-uart-swap-20261019.json')
    if backup.exists():raise ValueError('Restore already attempted')
    if not args.execute_restore:
        print('UART_RESTORE_OFFLINE_CHECK_PASS')
        return
    if not args.all_actuator_power_off_confirmed:
        raise ValueError('Fresh physical actuator power-off confirmation required')
    sys.path.insert(0,str(CALIBRATION))
    from servo_pwm_device import PwmDevice,Registers
    r=Registers()
    try:
        state=PwmDevice(r).status()
        if any(state[k] for k in ('armed','enabled_mask','pending','faults')) or state['sequence']!=args.expected_sequence:
            raise ValueError('Expected stopped state changed')
    finally:r.close()
    incident=Path('/run/shadow-pwm-motion-inhibit');incident_sha=digest(incident)
    subprocess.run(['systemctl','stop','shadow-uart-swap-hdmi'],check=True,timeout=20)
    busy=[]
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:
            if any(d in (process/'maps').read_text() for d in ('/dev/mem','/dev/dpu','/dev/video')):
                busy.append(process.name)
        except OSError:pass
    if busy:
        subprocess.run(['systemctl','start','shadow-uart-swap-hdmi'],check=True,timeout=20)
        raise ValueError('PL mappings remain owned: '+','.join(busy))
    if marker.read_bytes()!=old_raw:raise ValueError('Marker changed during preflight')
    marker.rename(backup)
    subprocess.run([sys.executable,str(CALIBRATION/'load_pwm_runtime.py'),'--image',str(image),
        '--manifest',str(manifest),'--servo-power-off-confirmed'],check=True,timeout=65)
    loaded=json.loads(marker.read_text())
    if loaded.get('sha256')!=STANDARD_SHA or digest(incident)!=incident_sha:
        raise ValueError('Restored image or incident lock verification failed')
    loaded.update(boot_id=boot,rail_query_only_commissioning=True,uart_pin_swap_trial_finished=True)
    marker.write_text(json.dumps(loaded,indent=2)+'\n')
    r=Registers()
    try:
        state=PwmDevice(r).status()
        if any(state[k] for k in ('armed','enabled_mask','pending','faults','sequence')):
            raise ValueError('Expected reset with all outputs off')
    finally:r.close()
    active=start_standard_display(boot)
    print('UART_STANDARD_RESTORED '+json.dumps(dict(state=state,boot_id=boot,image_sha=STANDARD_SHA,
        incident_lock_unchanged=True,display_active=active,motor_packets_sent=False)),flush=True)


if __name__=='__main__':main()
