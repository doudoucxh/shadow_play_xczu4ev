#!/usr/bin/env python3
"""Manage a bounded CSV-only controller session on the board (no camera capture)."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

UNIT = 'piying-controller-demo.service'
ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / 'output/latest-controller.json'


def run(*args, check=True, capture=False):
    return subprocess.run(args, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None,
                          env=dict(os.environ, SYSTEMD_PAGER='cat', PAGER='cat'))


def info():
    if not LATEST.exists():
        raise RuntimeError('No controller session recorded in this package')
    data = json.loads(LATEST.read_text())
    output = Path(data['output']).resolve()
    if output.parent != (ROOT / 'output').resolve() or not output.name.startswith('controller-'):
        raise RuntimeError('Unexpected session output path')
    return data, output


def start(args):
    state = run('systemctl', 'show', UNIT, '-p', 'ActiveState', '--value',
                check=False, capture=True).stdout.strip()
    if state not in ('inactive', 'failed', ''):
        raise RuntimeError('Controller is already running or changing state; use status/stop')
    out = ROOT / 'output' / ('controller-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    out.mkdir(parents=True, exist_ok=False)
    cmd = [str(ROOT / 'bin/shadow_show'), '--mode', args.mode, '--seconds', str(args.seconds),
           '--realtime', '--audio', 'clock', '--listen', '56000', '--control-port', '56001',
           '--motor-format', 'csv', '--output', str(out / 'angles.csv'),
           '--record-input', str(out / 'inputs.jsonl'),
           '--record-commands', str(out / 'commands.csv')]
    data = dict(output=str(out), mode=args.mode, seconds=args.seconds, unit=UNIT,
                scope='CSV targets only; silent clock; external camera sender required in camera mode')
    (out / 'session.json').write_text(json.dumps(data, indent=2) + '\n')
    run('systemctl', 'reset-failed', UNIT, check=False, capture=True)
    run('systemd-run', '--unit=' + UNIT, '--service-type=simple',
        '--property=WorkingDirectory=' + str(ROOT),
        '--property=StandardOutput=append:' + str(out / 'controller.log'),
        '--property=StandardError=append:' + str(out / 'controller.log'),
        '--property=RuntimeMaxSec=' + str(args.seconds + 10),
        '--property=TimeoutStopSec=5', *cmd)
    LATEST.write_text(json.dumps(data, indent=2) + '\n')
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        log = (out / 'controller.log').read_text() if (out / 'controller.log').exists() else ''
        if 'Control UDP: 127.0.0.1:56001' in log:
            print('CONTROLLER_READY ' + str(out))
            return
        if run('systemctl', 'is-active', '--quiet', UNIT, check=False, capture=True).returncode:
            raise RuntimeError('Controller exited before readiness: ' + log)
        time.sleep(.05)
    run('systemctl', 'stop', UNIT, check=False)
    raise RuntimeError('Readiness timed out; controller stopped')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    s = sub.add_parser('start')
    s.add_argument('--mode', choices=('script', 'touch', 'camera'), default='script')
    s.add_argument('--seconds', type=int, default=92)
    sub.add_parser('status')
    sub.add_parser('stop')
    c = sub.add_parser('command')
    c.add_argument('value', choices=('script', 'touch', 'camera', 'stop', 'reset-inputs'))
    args = p.parse_args()
    if os.geteuid() != 0:
        p.error('Run as root to manage the transient systemd unit')
    if args.action == 'start':
        if not 10 <= args.seconds <= 3600:
            p.error('--seconds must be 10..3600')
        start(args)
    elif args.action == 'status':
        data, out = info()
        print(json.dumps(data, indent=2))
        run('systemctl', 'show', UNIT, '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result',
            '-p', 'ExecMainStatus', '--no-pager', check=False)
        log = out / 'controller.log'
        if log.exists():
            print('\n'.join(log.read_text().splitlines()[-12:]))
    elif args.action == 'stop':
        info()
        run('systemctl', 'stop', UNIT)
        print('CONTROLLER_STOPPED (CSV process only; vision service unchanged)')
    else:
        info()
        run('systemctl', 'is-active', '--quiet', UNIT)
        run(str(ROOT / 'bin/shadow_send'), '--port', '56001', '--command', args.value)
        print('Command sent; use status and recorded commands to verify acceptance')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
