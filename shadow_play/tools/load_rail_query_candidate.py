"""Install a verified dual-UART candidate into volatile PL, with actuator power off.

Uses the existing motor-off loader; never starts a motor or edits boot files.
The old HDMI sink is stopped because its mappings cannot survive reconfiguration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from zdt_uartlite_telemetry import PORTS

BASE_SHA = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
PINS = ['D14', 'D15', 'F13', 'G13', 'G14', 'G15', 'J14', 'E13', 'E14', 'E15']
CALIBRATION = Path('/run/media/mmcblk0p2/piying/shadow-theatre-board-20261017-r4-runtime/shadow_play/integrations/calibration')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_candidate(manifest, image_sha, *, expected_ports=PORTS):
    rail = manifest.get('rail_uart', {})
    if (manifest.get('sha256') != image_sha or image_sha == BASE_SHA or
            len(image_sha) != 64 or manifest.get('image_kind') != 'servo10_vision' or
            manifest.get('design_checks') != 'SERVO_IMAGE_DESIGN_CHECKS_PASS' or
            manifest.get('bus_skew_check') != 'SERVO_BUS_SKEW_CHECK_PASS' or
            manifest.get('register_base') != 0xA0030000 or manifest.get('pins') != PINS or
            manifest.get('clock_hz') != 100000000 or manifest.get('period_us') != 20000 or
            manifest.get('part') != 'xczu4ev-sfvc784-2-i' or
            manifest.get('channels') != 10 or manifest.get('reset_outputs') != 'disabled' or
            not manifest.get('wns_ns', -1) >= 0 or not manifest.get('whs_ns', -1) >= 0 or
            not manifest.get('wpws_ns', -1) >= 0 or
            rail.get('design_checks') != 'RAIL_UART_DESIGN_CHECKS_PASS' or
            rail.get('ports') != expected_ports or rail.get('baud') != 115200 or rail.get('format') != '8N1'):
        raise ValueError('Unverified candidate image, timing, pins or UART map')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-sha', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--expected-sequence', type=int, required=True)
    parser.add_argument('--execute-load', action='store_true')
    parser.add_argument('--all-actuator-power-off-confirmed', action='store_true')
    parser.add_argument('--start-candidate-display', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    verify_candidate(manifest, args.image_sha)
    if digest(args.image) != args.image_sha:
        raise ValueError('Image content hash mismatch')
    if args.start_candidate_display:
        bundle = json.loads((args.manifest.parent/'MANIFEST.json').read_text())
        if bundle.get('image_sha') != args.image_sha or bundle.get('motion_enabled') is not False:
            raise ValueError('Unverified display bundle')
        for name, expected in bundle['files'].items():
            member = (args.manifest.parent/name).resolve()
            if not member.is_relative_to(args.manifest.parent.resolve()) or digest(member) != expected:
                raise ValueError('Display bundle content mismatch: '+name)
    if not args.execute_load:
        print('CANDIDATE_OFFLINE_CHECK_PASS')
        return
    if not args.all_actuator_power_off_confirmed:
        raise ValueError('Servo and both rail power must be physically off before PL reload')
    sys.path.insert(0, str(CALIBRATION))
    from servo_pwm_device import PwmDevice, Registers
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker_path = Path('/run/shadow-pwm-loaded.json')
    old_raw = marker_path.read_bytes()
    old = json.loads(old_raw)
    backup = Path('/run/shadow-pwm-before-rail-uart-20261019.json')
    incident = Path('/run/shadow-pwm-motion-inhibit')
    incident_sha = digest(incident)
    if (boot_id != args.boot_id or old.get('boot_id') != boot_id or
            old.get('sha256') != BASE_SHA or backup.exists()):
        raise ValueError('Boot/base image changed or this load has already been attempted')
    r = Registers()
    try:
        state = PwmDevice(r).status()
        if (state['armed'] or state['enabled_mask'] or state['pending'] or state['faults'] or
                state['sequence'] != args.expected_sequence):
            raise ValueError('PWM is not at the expected stopped state')
    finally:
        r.close()
    subprocess.run(['systemctl', 'stop', 'shadow-theatre-hdmi-r4'], check=True, timeout=20)
    busy = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if any(d in (p/'maps').read_text() for d in ('/dev/mem', '/dev/dpu', '/dev/video')):
                busy.append(p.name)
        except OSError:
            pass
    if busy:
        subprocess.run(['systemctl', 'start', 'shadow-theatre-hdmi-r4'], check=True, timeout=20)
        raise ValueError('PL mappings remain owned by PIDs: ' + ','.join(busy))
    # Atomically preserve the loaded-image marker, never the incident lock.
    # The existing loader refuses replacement while that marker is present.
    if marker_path.read_bytes() != old_raw:
        raise ValueError('Image marker changed during preflight')
    marker_path.rename(backup)
    subprocess.run([sys.executable, str(CALIBRATION/'load_pwm_runtime.py'),
        '--image', str(args.image), '--manifest', str(args.manifest),
        '--servo-power-off-confirmed'], check=True, timeout=65)
    loaded = json.loads(marker_path.read_text())
    if loaded.get('sha256') != args.image_sha or digest(incident) != incident_sha:
        raise ValueError('Loaded-image or incident-lock verification failed')
    loaded['boot_id'] = boot_id
    loaded['rail_query_only_commissioning'] = True
    marker_path.write_text(json.dumps(loaded, indent=2)+'\n')
    r = Registers()
    try:
        after = PwmDevice(r).status()
    finally:
        r.close()
    display_active = False
    if args.start_candidate_display:
        sink = args.manifest.resolve().parent/'shadow_play/hdmi_ui/runtime/hdmi_sink.py'
        subprocess.run(['systemd-run', '--unit=shadow-rail-query-hdmi', '--property=Restart=no',
                        sys.executable, '-u', str(sink)], check=True, timeout=15)
        time.sleep(1)
        display_active = subprocess.run(['systemctl', 'is-active', '--quiet',
                                        'shadow-rail-query-hdmi']).returncode == 0
    print('RAIL_CANDIDATE_LOADED ' + json.dumps(dict(
        state=after, boot_id=boot_id, image_sha=args.image_sha,
        all_actuator_power_off_confirmed=True, incident_lock_unchanged=True,
        motor_packets_sent=False, original_hdmi_sink_stopped=True,
        candidate_hdmi_active=display_active)), flush=True)


if __name__ == '__main__':
    main()
