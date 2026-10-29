"""Authorized cold boot of BS10, idle buses and the existing HDMI homepage.

Never infer that actuator power is off at future boots. No servo packets, lease,
motion or feedback RPC is started here. Live reconfiguration uses other tools.
"""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import subprocess
import sys
import time

BASE = Path('/run/media/mmcblk0p2/piying')
PACKAGE = BASE/'bus-servo-v1'
UI = BASE/'shadow-theatre-board-20261017-r4-runtime'
PACKAGE_SHA = 'f5e1d0a9fe66eeb0d9cfa837e4dc049d0728c34de2cfd305615cc93fd5e57434'
IMAGE_SHA = 'f1eb0f20063d57e9547f055ef15417fd621e2b6c8021f4b49c9355f3d7a30294'
UI_FILES = {
    'MANIFEST.json': '79518fc26c95bb80fc5b6ab9ef22971abf92636d4f9944674a0b4273792bc860',
    'start-software.sh': '10454280397da5bbad27587a00f08f97d2a96ad1aeee6816fafb029330064c3e',
    'units/shadow-theatre-ui-r4.service': 'bcfac223cd641136ec1c950e8e8d5af94b508cc813be422f326c4a8a145c0772',
    'units/shadow-theatre-browser-r4.service': '025316d7ebf6e11109f5205c4221472a8fb76bc71b256b45b62bbd8b4059dce4',
    'units/shadow-theatre-hdmi-r4.service': '96d5eb92272f35c5baba33f9fa577edf5f1a7b049074c67fea1763356ac61d91',
}
MARKERS = ('shadow-pwm-loaded.json', 'shadow-bus-servo-loaded.json',
           'shadow-bus-servo-load-attempt.json')
LEGACY = ('shadow-video', 'shadow-yolo-follow', 'shadow-yolo-pose',
          'shadow-arm-chain', 'shadow-hw-init')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_files(root, files):
    for name, expected in files.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != expected:
            raise RuntimeError('Installed file mismatch: '+name)


def verify_installation():
    if digest(PACKAGE/'MANIFEST.json') != PACKAGE_SHA:
        raise RuntimeError('Unexpected dual package manifest')
    files = json.loads((PACKAGE/'MANIFEST.json').read_text())['files']
    if len(files) != 25:
        raise RuntimeError('Incomplete dual package')
    verify_files(PACKAGE, files)
    verify_files(UI, UI_FILES)
    ui = json.loads((UI/'MANIFEST.json').read_text())
    if ui.get('motion_enabled') is not False:
        raise RuntimeError('UI motion must remain disabled')
    verify_files(UI/'shadow_play', ui['files'])
    if not (UI/'shadow_play/integrations/calibration/.motion-inhibit').is_file():
        raise RuntimeError('Persistent motion inhibit missing')
    sys.path.insert(0, str(PACKAGE))
    from shadow_play.bus_servo.load_candidate import verify
    manifest = json.loads((PACKAGE/'bus_servo.manifest.json').read_text())
    if verify(PACKAGE/'bus_servo.bit.bin', manifest).identity != 'BS10' or manifest['sha256'] != IMAGE_SHA:
        raise RuntimeError('Not the reviewed BS10 image')
    return manifest


def cold_guard(run_dir, uptime):
    if not 0 <= uptime < 240 or any((run_dir/name).exists() for name in MARKERS):
        raise RuntimeError('Cold boot only; prior load/attempt or late invocation')


def reset_state(read):
    expected = {0: 0x42533130, 4: 1, 8: 0, 16: 0, 0x18: 100000000,
                0x1c: 115200, 0x100: 0, 0x200: 0}
    actual = {offset: read(offset) for offset in expected}
    if actual != expected:
        raise RuntimeError('BS10 reset state is not idle: '+str(actual))
    return {hex(k): v for k, v in actual.items()}


def run(*command, timeout=60):
    subprocess.run(command, check=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-cold-boot', action='store_true')
    args = parser.parse_args()
    manifest = verify_installation()
    if not args.execute_cold_boot:
        print('BUS_BOOT_FILES_VALIDATED_NO_HARDWARE')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    cold_guard(Path('/run'), float(Path('/proc/uptime').read_text().split()[0]))
    for name in LEGACY:
        result = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True)
        if result.stdout.strip() not in ('inactive', 'failed', 'unknown'):
            raise RuntimeError('Legacy hardware service active: '+name)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            maps = (proc/'maps').read_text()
            if any(device in maps for device in ('/dev/mem', '/dev/dpu', '/dev/video')):
                raise RuntimeError('PL consumer already active: '+proc.name)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    import fcntl
    from shadow_play.integrations.calibration.mmio32 import WordAccess
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    with open('/run/shadow-pwm.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cold_guard(Path('/run'), float(Path('/proc/uptime').read_text().split()[0]))
        with mmap.mmap(-1, 4096) as scratch:
            words = WordAccess(scratch)
            try:
                words.write(0, 0x42533130)
                if words.read(0) != 0x42533130:
                    raise RuntimeError('Native word self-test failed')
            finally:
                words.close()
        incident = Path('/run/shadow-pwm-motion-inhibit')
        if not incident.exists():
            with incident.open('x') as stream:
                stream.write('Automatic display startup; motion disabled.\n')
        incident_sha = digest(incident)
        with Path('/run/shadow-bus-servo-load-attempt.json').open('x') as stream:
            json.dump(dict(boot_id=boot_id, candidate_sha=IMAGE_SHA,
                           authorization='user requested persistent idle BS10 startup',
                           actuator_power='not inferred at boot', retry=False), stream)
        # One programming attempt. Failure leaves the attempt marker consumed.
        run('fpgautil', '-b', str(PACKAGE/'bus_servo.bit.bin'), '-f', 'Full')
        if Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() != 'operating':
            raise RuntimeError('FPGA not operating')
        fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
        try:
            with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0xA0060000) as memory:
                words = WordAccess(memory)
                try:
                    state = reset_state(words.read)
                finally:
                    words.close()
        finally:
            os.close(fd)
        if digest(incident) != incident_sha:
            raise RuntimeError('Motion inhibit changed')
        record = dict(manifest, boot_id=boot_id, loaded_unix=time.time(),
                      incident_sha256=incident_sha, reset_state=state,
                      scope='persistent cold boot; idle BS10; no servo packets')
        with Path('/run/shadow-bus-servo-loaded.json').open('x') as stream:
            json.dump(record, stream, indent=2)
    # Reuse the unchanged UI, with an isolated bus-compatible HDMI sink.
    import grp
    try:
        grp.getgrnam('input')
    except KeyError:
        run('groupadd', '--system', 'input')
    Path('/etc/udev/rules.d/71-shadow-theatre-input.rules').write_text(
        'SUBSYSTEM=="input", KERNEL=="event*", GROUP="input", MODE="0660"\n')
    run('udevadm', 'control', '--reload-rules')
    run('udevadm', 'trigger', '--subsystem-match=input', '--action=change')
    run('udevadm', 'settle', '--timeout=10')
    dropin = Path('/etc/systemd/system/shadow-theatre-hdmi-r4.service.d')
    dropin.mkdir()
    (dropin/'10-bus.conf').write_text(
        '[Unit]\nConditionPathExists=\nConditionPathExists=/run/shadow-bus-servo-loaded.json\n'
        '[Service]\nExecStart=\nExecStart=/usr/bin/python3 -u '+
        str(PACKAGE/'shadow_play/hdmi_ui/runtime/hdmi_sink.py')+'\nRestart=no\n')
    run('/bin/sh', str(UI/'start-software.sh'), timeout=45)
    run('systemctl', 'start', 'shadow-theatre-hdmi-r4.service')
    sys.path.insert(0, str(PACKAGE/'shadow_play/hdmi_ui/runtime'))
    from browser_display import read_packet
    previous = None
    deadline = time.monotonic()+45
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
        raise RuntimeError('No fresh consecutive UI frames')
    for name in ('shadow-theatre-ui-r4', 'shadow-theatre-browser-r4', 'shadow-theatre-hdmi-r4'):
        run('systemctl', 'is-active', '--quiet', name)
    result = dict(result='BS10_IDLE_HOME_READY', boot_id=boot_id, image_sha256=IMAGE_SHA,
                  servo_packets_sent=0, motion_enabled=False, automatic_start=True)
    Path('/run/shadow-theatre-boot-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('BS10_AUTOSTART_SUCCESS '+json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
