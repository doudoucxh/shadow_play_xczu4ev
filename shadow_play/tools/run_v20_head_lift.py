"""Read-only by default; one new user-requested axis-8 check with Sony leases."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / 'shadow_play/integrations/calibration'
sys.path.insert(0, str(CAL))
from v20_head_lift import SCHEMA, SOURCE_SHA, FRAMES
from v20_first_direction import IMAGE, MIDPOINT, PREFIX, digest
from run_v20_first_direction import FreshCamera, parse_event, valid_reference
from servo_center_session import await_prompt

BOARD = '/run/media/mmcblk0p2/piying/v20-head-lift-20261018'
LIB = BOARD + '/integrations/calibration'
FILES = ('v20_head_lift.py', 'v20_first_direction.py', 'servo_pwm_device.py', 'mmio32.py', 'libservo_mmio32.so')


def run(output, execute=False, port_name='COM17'):
    import serial
    output.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()
    worker = None
    started = False
    final = audit = None
    port = serial.Serial(None, 115200, timeout=.05, write_timeout=.5)
    port.dtr = port.rts = False
    port.port = port_name
    pending = b''
    lock = threading.Lock()
    camera = FreshCamera(ROOT / 'camera_liveview/output')
    captures = []
    with (output / 'serial.jsonl').open('x', encoding='utf-8') as log:
        def record(key, value):
            with lock:
                log.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), **{key: value})) + '\n')
                log.flush()
        def send(value):
            if len(value) > 3800:
                raise ValueError('Canonical terminal command too long')
            record('send', value)
            port.write(value.encode('ascii'))
        def receive(test, seconds):
            nonlocal pending
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    result = test(line.strip().decode('utf-8', 'replace'))
                    if result is not None:
                        return result
                raw = port.read(4096)
                if raw:
                    pending += raw
                    record('receive', raw.decode('utf-8', 'replace'))
            raise TimeoutError('No expected board acknowledgement; no retry')
        def python(code, prefix=''):
            encoded = base64.b64encode(code.encode('utf-8')).decode()
            send(prefix + "python3 -u -c \"import base64;exec(base64.b64decode('" + encoded + "'))\"\r")
        try:
            port.open(); port.write(b'\r')
            if await_prompt(port, 6, service='attended-initial-pose-v1') != 'root':
                raise RuntimeError('Terminal is owned by another manual session')
            send('stty -echo\r'); time.sleep(.2); port.read_all()
            hashes = {n: hashlib.sha256((CAL / n).read_bytes()).hexdigest() for n in FILES}
            python("import sys,json,hashlib;from pathlib import Path;p=Path('" + LIB + "');h=" + repr(hashes)
                   + ";assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v for n,v in h.items());"
                     "sys.path.insert(0,str(p));from servo_pwm_device import Registers,PwmDevice;"
                     "r=Registers();s=PwmDevice(r).status();r.close();"
                     "print('HEAD_INSPECT '+json.dumps(dict(state=s,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()))),flush=True)")
            inspected = receive(lambda s: json.loads(s.split('HEAD_INSPECT ', 1)[1]) if 'HEAD_INSPECT ' in s else None, 8)
            (output / 'inspection.json').write_text(json.dumps(inspected, indent=2), encoding='utf-8')
            print('READ_ONLY ' + json.dumps(inspected), flush=True)
            if not execute:
                return inspected
            valid_reference(inspected['state'])
            previous = json.loads((ROOT / 'shadow_play/config/v20_first_direction_result_20261018.json').read_text(encoding='utf-8'))
            # Preserve the old stop record. This entry needs a new explicit request
            # and its own fixed axis-8 permission; it never edits the axis-7 guard.
            if (not previous['route_complete'] or previous['state']['sequence'] != inspected['state']['sequence']
                    or previous['state']['pulse_us'] != MIDPOINT or previous['boot_id'] != inspected['boot_id']
                    or inspected['marker'].get('boot_id') != inspected['boot_id']
                    or inspected['marker'].get('sha256') != IMAGE):
                raise RuntimeError('Fresh state differs from the original completed-run reference')
            historical = ROOT / 'shadow_play/config/tiger_map_a_result.20261012.json'
            if hashlib.sha256(historical.read_bytes()).hexdigest() != SOURCE_SHA:
                raise RuntimeError('Historical source changed')
            rows = json.loads(historical.read_text(encoding='utf-8'))['events']
            target = [r for r in rows if r.get('event') == 'probe_complete' and r.get('axis') == 3]
            if len(target) != 1 or target[0]['state']['pulse_us'][6:] != [1500, 1540, 1500, 1500]:
                raise RuntimeError('Head-lift target provenance mismatch')
            request_id = uuid.uuid4().hex
            request = dict(request_id=request_id, user_request='Direct real-hardware operation requested in this chat',
                           supersedes_prior_user_stop_for_this_one_check=True, channel=8,
                           pulse_range_us=[1500, 1540], camera_required=True, full_show=False)
            (output / 'new-request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
            plan = dict(schema=SCHEMA, session_id=uuid.uuid4().hex, boot_id=inspected['boot_id'],
                        expected_sequence=inspected['state']['sequence'], expected_pulse_us=MIDPOINT,
                        route_sha256=digest(FRAMES), historical_source_sha256=SOURCE_SHA,
                        camera_required=True, onsite_observer=True, new_request_id=request_id,
                        new_hardware_request=True, prior_log_path=previous['source_log_path'],
                        prior_log_sha256=previous['board_log_sha256'])
            captures.append(dict(stage='before', **camera.sample(output / 'camera-before.jpg')))
            (output / 'plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
            target_path = BOARD + '/run-' + plan['session_id'] + '.json'
            data = base64.b64encode(json.dumps(plan).encode()).decode()
            python("import base64,os;f=open('" + target_path + "','xb');f.write(base64.b64decode('" + data + "'));f.close();"
                   "os.execv('/usr/bin/python3',['python3','-u','" + LIB + "/v20_head_lift.py','" + target_path + "','--execute-one-head-lift'])",
                   prefix='PYTHONPATH=' + LIB + ' ')
            ready = receive(parse_event, 8)
            if ready.get('event') != 'ready' or ready.get('session_id') != plan['session_id']:
                raise RuntimeError('One-use ready response mismatch')
            valid_reference(ready['state'])
            if ready['state']['sequence'] != plan['expected_sequence']:
                raise RuntimeError('State changed before explicit begin')
            started = True
            send(': # V20_BEGIN ' + plan['session_id'] + '\n')
            def leases():
                while not stop.wait(.3):
                    try:
                        camera.sample()
                        send(': # V20_LEASE ' + plan['session_id'] + '\n')
                    except BaseException as error:
                        record('lease_failure', type(error).__name__)
                        try: send(': # V20_STOP\n')
                        except Exception: pass
                        stop.set(); return
            worker = threading.Thread(target=leases, daemon=True); worker.start()
            while audit is None:
                event = receive(parse_event, 18)
                print(json.dumps(event), flush=True)
                if event.get('event') == 'frame':
                    index = event['index']
                    captures.append(dict(stage='frame_' + str(index),
                        **camera.sample(output / ('camera-frame-' + str(index) + '.jpg'))))
                elif event.get('event') == 'outputs_off':
                    final = event
                    if not event['route_complete']: break
                elif event.get('event') == 'audit': audit = event
            result = dict(request=request, plan=plan, result=final, audit=audit, camera_captures=captures,
                          physical_motion_verified=False, observer_note=None)
            (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            if final is None or not final['route_complete']:
                raise RuntimeError('Route incomplete; no automatic return or retry')
            valid_reference(final['state'])
            return result
        finally:
            stop.set()
            if worker is not None: worker.join(1)
            if port.is_open:
                try:
                    if started and final is None:
                        send(': # V20_STOP\n'); time.sleep(.15); port.write(b'\x03'); time.sleep(.2)
                    port.write(b'\r')
                    if await_prompt(port, 4, service='attended-initial-pose-v1') == 'root':
                        port.write(b'stty echo\r')
                finally: port.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--port', default='COM17')
    p.add_argument('--execute-new-hardware-request', action='store_true')
    a = p.parse_args()
    run(a.output, a.execute_new_hardware_request, a.port)
