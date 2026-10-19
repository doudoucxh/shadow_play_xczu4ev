"""One-use, power-off installation of the explicitly requested UART pin trial.

Never changes boot files, removes motion locks, or transmits motor packets.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from load_rail_query_candidate import CALIBRATION, digest, verify_candidate
from zdt_uartlite_telemetry import SWAPPED_PORTS, validate_pin_map

STANDARD_SHA = 'ea680d88d2d149157490ebbe27b253b3814d6d2df17aeebb477047bb4bc81e90'


def verify_swapped(manifest, image_sha):
    verify_candidate(manifest, image_sha, expected_ports=SWAPPED_PORTS)
    validate_pin_map(manifest['rail_uart'], 'swapped')
    if (manifest.get('previous_sha256') != STANDARD_SHA or image_sha == STANDARD_SHA or
            manifest['rail_uart'].get('swapped_design_checks') != 'RAIL_UART_SWAPPED_DESIGN_CHECKS_PASS'):
        raise ValueError('Not the separately checked swapped-pin trial')


def verify_bundle(folder, image_sha):
    bundle = json.loads((folder/'MANIFEST.json').read_text())
    if (bundle.get('image_sha') != image_sha or bundle.get('motion_enabled') is not False or
            bundle.get('pin_map') != 'swapped'):
        raise ValueError('Unverified swapped display/data bundle')
    for name, expected in bundle['files'].items():
        original = folder/name
        member = original.resolve()
        if (not member.is_relative_to(folder.resolve()) or original.is_symlink() or
                digest(member) != expected):
            raise ValueError('Bundle content mismatch: '+name)


def stopped(state, sequence):
    return not any(state[k] for k in ('armed','enabled_mask','pending','faults')) and state['sequence'] == sequence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-sha', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--expected-sequence', type=int, required=True)
    parser.add_argument('--execute-load', action='store_true')
    parser.add_argument('--all-actuator-power-off-confirmed', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    verify_swapped(manifest, args.image_sha)
    if digest(args.image) != args.image_sha:
        raise ValueError('Image hash mismatch')
    verify_bundle(args.manifest.parent, args.image_sha)
    if not args.execute_load:
        print('SWAPPED_UART_OFFLINE_CHECK_PASS')
        return
    if not args.all_actuator_power_off_confirmed:
        raise ValueError('Fresh physical actuator power-off confirmation required')
    sys.path.insert(0, str(CALIBRATION))
    from servo_pwm_device import PwmDevice, Registers
    marker_path = Path('/run/shadow-pwm-loaded.json')
    old_raw = marker_path.read_bytes()
    old = json.loads(old_raw)
    backup = Path('/run/shadow-pwm-before-uart-swap-20261019.json')
    incident = Path('/run/shadow-pwm-motion-inhibit')
    incident_sha = digest(incident)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if (boot != args.boot_id or old.get('boot_id') != boot or
            old.get('sha256') != STANDARD_SHA or backup.exists()):
        raise ValueError('Expected current image/boot changed, or this load was already attempted')
    r = Registers()
    try:
        if not stopped(PwmDevice(r).status(), args.expected_sequence):
            raise ValueError('PWM is not in the bound stopped state')
    finally:
        r.close()
    subprocess.run(['systemctl','stop','shadow-rail-query-hdmi'], check=True, timeout=20)
    busy = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if any(device in (p/'maps').read_text() for device in ('/dev/mem','/dev/dpu','/dev/video')):
                busy.append(p.name)
        except OSError:
            pass
    if busy:
        subprocess.run(['systemctl','start','shadow-rail-query-hdmi'], check=True, timeout=20)
        raise ValueError('PL mappings remain owned: '+','.join(busy))
    if marker_path.read_bytes() != old_raw:
        raise ValueError('Loaded image marker changed during preflight')
    marker_path.rename(backup)
    subprocess.run([sys.executable, str(CALIBRATION/'load_pwm_runtime.py'),
        '--image', str(args.image), '--manifest', str(args.manifest),
        '--servo-power-off-confirmed'], check=True, timeout=65)
    loaded = json.loads(marker_path.read_text())
    if loaded.get('sha256') != args.image_sha or digest(incident) != incident_sha:
        raise ValueError('Loaded image or incident lock verification failed')
    loaded.update(boot_id=boot, rail_query_only_commissioning=True, uart_pin_swap_trial=True)
    marker_path.write_text(json.dumps(loaded, indent=2)+'\n')
    r = Registers()
    try:
        after = PwmDevice(r).status()
        if not stopped(after, 0):
            raise ValueError('Expected reset with all outputs off')
    finally:
        r.close()
    sink = args.manifest.parent/'shadow_play/hdmi_ui/runtime/hdmi_sink.py'
    subprocess.run(['systemd-run','--unit=shadow-uart-swap-hdmi','--property=Restart=no',
                    sys.executable,'-u',str(sink)], check=True, timeout=15)
    time.sleep(1)
    active = subprocess.run(['systemctl','is-active','--quiet','shadow-uart-swap-hdmi']).returncode == 0
    print('SWAPPED_UART_LOADED '+json.dumps(dict(state=after,boot_id=boot,image_sha=args.image_sha,
        all_actuator_power_off_confirmed=True,incident_lock_unchanged=True,
        display_active=active,motor_packets_sent=False)), flush=True)


if __name__ == '__main__':
    main()
