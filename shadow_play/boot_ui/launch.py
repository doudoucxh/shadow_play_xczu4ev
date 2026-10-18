"""Cold boot display only. Never arm PWM, replay a story, or start inference."""
import hashlib
import grp
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

BASE = Path('/run/media/mmcblk0p2/piying')
ROOT = BASE/'shadow-theatre-board-20261017-r4-runtime'
IMAGE_SHA = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'


def digest(path):
    with path.open('rb') as source:
        h = hashlib.sha256()
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def run(*command, timeout=60):
    subprocess.run(command, check=True, timeout=timeout)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    marker = Path('/run/shadow-pwm-loaded.json')
    # This entry is cold-boot-only, not a live PL reset/recovery command.
    if marker.exists():
        raise RuntimeError('Display image already loaded; refusing live reconfiguration')
    manifest = json.loads((ROOT/'MANIFEST.json').read_text())
    if manifest.get('motion_enabled') is not False:
        raise RuntimeError('UI installation is not software-only')
    for name, expected in manifest['files'].items():
        path = (ROOT/'shadow_play'/name).resolve()
        if not path.is_relative_to(ROOT/'shadow_play') or digest(path) != expected:
            raise RuntimeError('Installed file checksum mismatch: '+name)
    calibration = ROOT/'shadow_play/integrations/calibration'
    if not (calibration/'.motion-inhibit').is_file():
        raise RuntimeError('Persistent motion inhibit is missing')
    Path('/run/shadow-pwm-motion-inhibit').write_text('Automatic display startup; motion disabled.\n')
    image = ROOT/'shadow_play/hardware/servo_pwm/release/servo10_vision.bit.bin'
    if digest(image) != IMAGE_SHA:
        raise RuntimeError('Unreviewed display image')
    for name in ('shadow-video', 'shadow-yolo-follow', 'shadow-yolo-pose', 'shadow-arm-chain', 'shadow-hw-init'):
        result = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True)
        if result.stdout.strip() not in ('inactive', 'failed', 'unknown'):
            raise RuntimeError('Legacy hardware service is active: '+name)
    # Actuators are not installed in this software-only deployment. The reviewed
    # loader verifies disabled reset outputs, and all persistent locks remain.
    run(sys.executable, str(calibration/'load_pwm_runtime.py'), '--image', str(image),
        '--manifest', str(image.with_name('servo10.manifest.json')),
        '--servo-power-off-confirmed', timeout=65)
    record = json.loads(marker.read_text())
    record['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker.write_text(json.dumps(record, indent=2)+'\n')
    try:
        grp.getgrnam('input')
    except KeyError:
        run('groupadd', '--system', 'input')
    rule = Path('/etc/udev/rules.d/71-shadow-theatre-input.rules')
    rule.write_text('SUBSYSTEM=="input", KERNEL=="event*", GROUP="input", MODE="0660"\n')
    run('udevadm', 'control', '--reload-rules')
    run('udevadm', 'trigger', '--subsystem-match=input', '--action=change')
    run('udevadm', 'settle', '--timeout=10')
    run('/bin/sh', str(ROOT/'start-software.sh'), timeout=45)
    # A running browser alone does not prove new pixels reached the HDMI sink.
    runtime = ROOT/'shadow_play/hdmi_ui/runtime'
    sys.path.insert(0, str(runtime))
    from browser_display import read_packet
    deadline = time.monotonic()+45
    previous = None
    while time.monotonic() < deadline:
        try:
            captured, _ = read_packet(Path('/run/shadow-ui/frame.bin'), time.monotonic())
            if previous is not None and captured > previous:
                break
            previous = captured
        except (OSError, ValueError):
            pass
        time.sleep(.25)
    else:
        raise RuntimeError('No consecutive fresh UI frames')
    for name in ('shadow-theatre-ui-r4', 'shadow-theatre-browser-r4', 'shadow-theatre-hdmi-r4'):
        run('systemctl', 'is-active', '--quiet', name)
    with urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=5) as response:
        status = json.load(response)
    result = dict(result='HOME_SERVICES_READY', boot_id=record['boot_id'],
                  uptime_seconds=float(Path('/proc/uptime').read_text().split()[0]),
                  motion_enabled=False, status=status)
    Path('/run/shadow-theatre-boot-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
