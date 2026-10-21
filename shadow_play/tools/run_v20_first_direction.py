"""Fresh read-only inspection by default; explicit single attended axis-7 check.

Optional existing Sony-preview observation; no full score, audio, slide command
or automatic next-probe option. Camera loss stops host leases and the check.
Uses the dedicated SD service, never the initialization GUI's motion entry point.
"""
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
import io

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / 'shadow_play/integrations/calibration'
sys.path.insert(0, str(CAL))
from v20_first_direction import (SCHEMA, IMAGE, HISTORICAL_SOURCE, MIDPOINT, MASK, ROUTE, digest,
                                 PREFIX, LATEST_LOG_SHA, LATEST_PULSES, route)
from servo_center_session import await_prompt

BOARD = '/run/media/mmcblk0p2/piying/v20-first-direction-20261018-r4'
LIB = BOARD + '/integrations/calibration'
FILES = ('v20_first_direction.py', 'servo_pwm_device.py', 'mmio32.py', 'libservo_mmio32.so')
CHECKPOINT = ROOT / 'shadow_play/config/task1_v20_midpoint_checkpoint_20261018.json'


def parse_event(line):
    # A shell prompt has no LF and can precede the first protocol event.
    offset = line.find(PREFIX)
    if offset == -1:
        return None
    leading = line[:offset].strip()
    if leading and not leading.endswith('#'):
        raise RuntimeError('Unexpected text before board event')
    return json.loads(line[offset + len(PREFIX):])


def valid_reference(state, pulses=MIDPOINT):
    if (state['armed'] or state['enabled_mask'] or state['faults'] or state['pending']
            or state['pulse_us'] != pulses or state['period_us'] != 20000 or state['clock_hz'] != 100000000):
        raise RuntimeError('Fresh clean OFF midpoint-command state required; no initialization attempted')


def completed_camera_reference(record):
    if record.get('user_requested_remain_stopped'):
        raise RuntimeError('Operator requested remain stopped; no automatic motion resume')
    if record.get('route_complete') is not True:
        raise RuntimeError('New completed midpoint-reference record required')
    valid_reference(record['state'])
    return dict(record['state'], boot_id=record['boot_id'])


def _read_camera_file(path, *, binary=False, encoding='utf-8'):
    """Allow a brief Windows file-replacement conflict, never cached data."""
    deadline = time.monotonic() + .15
    while True:
        try:
            return path.read_bytes() if binary else path.read_text(encoding=encoding)
        except (PermissionError, FileNotFoundError):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(.01, remaining))


class FreshCamera:
    def __init__(self, root, clock=time.time, monotonic=time.monotonic):
        self.root = Path(root).resolve()
        self.clock = clock
        self.monotonic = monotonic
        self.last_frame = None
        self.last_advance = monotonic()
        self.lock = threading.Lock()

    def sample(self, destination=None):
        from PIL import Image
        with self.lock:
            pointer = json.loads(_read_camera_file(self.root / 'current.json', encoding='utf-8-sig'))
            session = Path(pointer['directory']).resolve()
            if session.parent != self.root:
                raise RuntimeError('Unexpected camera session path')
            state = json.loads(_read_camera_file(session / 'status.json'))
            raw = _read_camera_file(session / 'latest.jpg', binary=True)
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                if im.format != 'JPEG':
                    raise RuntimeError('Camera JPEG decode failed')
                size = list(im.size)
            # Recheck age after any sharing-conflict wait and JPEG decode.
            age = self.clock() * 1000 - state['updated_unix_ms']
            frame = state['frames']
            if state['state'] != 'streaming' or not -1000 <= age <= 1500:
                raise RuntimeError('Camera not streaming fresh frames')
            if self.last_frame is not None and frame < self.last_frame:
                raise RuntimeError('Camera frame counter reset')
            if frame != self.last_frame:
                self.last_frame = frame
                self.last_advance = self.monotonic()
            elif self.monotonic() - self.last_advance > 1.5:
                raise RuntimeError('Camera frame counter stalled')
            if destination is not None:
                destination.write_bytes(raw)
            return dict(frame=frame, age_ms=age, updated_unix_ms=state['updated_unix_ms'],
                        sha256=hashlib.sha256(raw).hexdigest(), size=size)


def run(port_name, output, execute=False, resume=False, camera_observed=False):
    import serial
    output.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()
    worker = None
    begun = False
    result = None
    camera = FreshCamera(ROOT / 'camera_liveview/output') if camera_observed else None
    captures = []
    port = serial.Serial(None, 115200, timeout=.05, write_timeout=.5)
    port.dtr = False
    port.rts = False
    port.port = port_name
    port.open()
    pending = b''
    log_lock = threading.Lock()
    with (output / 'serial.jsonl').open('x', encoding='utf-8') as log:
        def record(kind, value):
            with log_lock:
                log.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), kind: value}) + '\n')
                log.flush()
        def send(value):
            record('send', value)
            port.write(value.encode('ascii'))
        def receive_until(test, seconds):
            nonlocal pending
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    value = test(line.strip().decode('utf-8', 'replace'))
                    if value is not None:
                        return value
                data = port.read(4096)
                if data:
                    record('receive', data.decode('utf-8', 'replace'))
                    pending += data
            raise TimeoutError('No expected board acknowledgement; no retry')
        try:
            port.write(b'\r')
            if await_prompt(port, 6, service='attended-initial-pose-v1') != 'root':
                raise RuntimeError('Existing manual service owns the terminal; stop it before this check')
            send('stty -echo\r')
            time.sleep(.2)
            port.read_all()
            hashes = {n: hashlib.sha256((CAL / n).read_bytes()).hexdigest() for n in FILES}
            checks = repr(hashes)
            # A short, read-only program verifies installed dependencies as well as the live state.
            code = ("import json,hashlib,sys;from pathlib import Path;"
                    "p=Path('" + LIB + "');h=" + checks + ";"
                    "assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v for n,v in h.items());"
                    "sys.path.insert(0,str(p));from servo_pwm_device import Registers,PwmDevice;"
                    "r=Registers();s=PwmDevice(r).status();r.close();"
                    "m=json.loads(Path('/run/shadow-pwm-loaded.json').read_text());"
                    "print('V20_INSPECT '+json.dumps(dict(state=s,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),marker=m,locks=[hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in ['/run/shadow-pwm-motion-inhibit',str(p/'.motion-inhibit')]])),flush=True)")
            encoded = base64.b64encode(code.encode()).decode()
            send("python3 -u -c \"import base64;exec(base64.b64decode('" + encoded + "'))\"\r")
            inspected = receive_until(lambda line: json.loads(line[12:]) if line.startswith('V20_INSPECT ') else None, 8)
            record('inspected', inspected)
            (output / 'inspection.json').write_text(json.dumps(inspected, indent=2), encoding='utf-8')
            print('FRESH_READ_ONLY ' + json.dumps(inspected), flush=True)
            if not execute:
                return inspected
            if camera_observed:
                completed = json.loads((ROOT / 'shadow_play/config/v20_first_direction_result_20261018.json').read_text(encoding='utf-8'))
                checkpoint = completed_camera_reference(completed)
                expected_pulses = MIDPOINT
                captures.append(dict(stage='before', **camera.sample(output / 'camera-before.jpg')))
            elif resume:
                record_path = ROOT / 'shadow_play/config/v20_first_direction_result_20261018.json'
                interruption = json.loads(record_path.read_text(encoding='utf-8'))
                if (interruption['board_log_sha256'] != LATEST_LOG_SHA
                        or interruption.get('observer_ready_for_next_first_check') is not True
                        or interruption.get('current_rods_clear_for_next_first_check') is not True):
                    raise RuntimeError('Recorded interruption and fresh onsite review required')
                checkpoint = dict(interruption['state'], boot_id=interruption['boot_id'])
                expected_pulses = LATEST_PULSES
            else:
                checkpoint = json.loads(CHECKPOINT.read_text(encoding='utf-8'))['board']
                expected_pulses = MIDPOINT
            valid_reference(inspected['state'], expected_pulses)
            if (inspected['boot_id'] != checkpoint['boot_id'] or inspected['state']['sequence'] != checkpoint['sequence']
                    or inspected['marker'].get('boot_id') != inspected['boot_id']
                    or inspected['marker'].get('sha256') != IMAGE):
                raise RuntimeError('Midpoint checkpoint changed; no stale binding or automatic recovery')
            source = ROOT / 'shadow_play/config/tiger_map_a_result.20261012.json'
            if hashlib.sha256(source.read_bytes()).hexdigest() != HISTORICAL_SOURCE:
                raise RuntimeError('Historical source changed')
            original = json.loads(source.read_text(encoding='utf-8'))
            matching = [r for r in original['events'] if r.get('event') == 'probe_complete' and r.get('axis') == 1]
            if len(matching) != 1 or matching[0]['state']['pulse_us'][6:] != [1540, 1500, 1500, 1500]:
                raise RuntimeError('Historical target provenance mismatch')
            plan = dict(schema=SCHEMA, session_id=uuid.uuid4().hex, boot_id=inspected['boot_id'],
                        expected_sequence=inspected['state']['sequence'], expected_pulse_us=expected_pulses,
                        route_sha256=digest(route(expected_pulses[6])), historical_source_sha256=HISTORICAL_SOURCE,
                        operator_midpoint_reference=True, onsite_observer=True, camera_required=camera_observed,
                        enabled_mask=MASK, interruption_reviewed=resume)
            (output / 'plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
            target = BOARD + '/run-' + plan['session_id'] + '.json'
            data = base64.b64encode(json.dumps(plan).encode()).decode()
            # Exclusive plan creation prevents accidental replacement of a prior run.
            code = ("import base64,os;f=open('" + target + "','xb');f.write(base64.b64decode('" + data + "'));f.close();"
                    "os.execv('/usr/bin/python3',['python3','-u','" + LIB + "/v20_first_direction.py','" + target + "','--execute-one-direction-check'])")
            encoded = base64.b64encode(code.encode()).decode()
            send("PYTHONPATH=" + LIB + " python3 -u -c \"import base64;exec(base64.b64decode('" + encoded + "'))\"\r")
            ready = receive_until(parse_event, 8)
            if ready.get('event') != 'ready' or ready.get('session_id') != plan['session_id']:
                raise RuntimeError('Expected one-use ready acknowledgement')
            valid_reference(ready['state'], expected_pulses)
            if ready['state']['sequence'] != plan['expected_sequence']:
                raise RuntimeError('Ready sequence mismatch')
            # No review pause while energized. This slower check has a twelve-second schedule.
            begun = True
            send(': # V20_BEGIN ' + plan['session_id'] + '\n')
            def leases():
                while not stop.wait(.3):
                    try:
                        if camera is not None:
                            camera.sample()
                        send(': # V20_LEASE ' + plan['session_id'] + '\n')
                    except BaseException as error:
                        record('lease_failure', type(error).__name__)
                        try:
                            send(': # V20_STOP\n')
                        except Exception:
                            pass
                        stop.set()
                        return
            worker = threading.Thread(target=leases, daemon=True)
            worker.start()
            end = time.monotonic() + 20
            while time.monotonic() < end:
                event = receive_until(parse_event, 12)
                print(json.dumps(event), flush=True)
                if camera is not None and event.get('event') == 'frame':
                    index = event['index']
                    captures.append(dict(stage='frame_' + str(index),
                        **camera.sample(output / ('camera-frame-' + str(index) + '.jpg'))))
                if event.get('event') == 'outputs_off':
                    result = event
                    break
            if result is None:
                raise RuntimeError('Missing final OFF acknowledgement; never repeat the attempt')
            if (result['state']['armed'] or result['state']['enabled_mask'] or result['state']['pending']
                    or result['state']['faults']):
                raise RuntimeError('Final OFF state mismatch')
            (output / 'result.json').write_text(json.dumps(dict(plan=plan, result=result,
                onsite_direction_verified=False, observer_note=None, camera_captures=captures,
                board_log=target.replace('.json', '.board.jsonl')),
                indent=2), encoding='utf-8')
            if not result['route_complete'] or result['state']['pulse_us'] != MIDPOINT:
                raise RuntimeError('Check did not complete; inspect stop record, do not auto-return')
            return result
        finally:
            stop.set()
            if worker is not None:
                worker.join(1)
            if begun and result is None:
                try:
                    send(': # V20_STOP\n')
                    time.sleep(.15)
                    port.write(b'\x03')
                    time.sleep(.25)
                except Exception:
                    pass
            # Restore terminal echo only after the service has released the terminal.
            try:
                port.write(b'\r')
                if await_prompt(port, 4, service='attended-initial-pose-v1') == 'root':
                    port.write(b'stty echo\r')
            finally:
                port.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', default='COM17')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute-next-first-check', action='store_true')
    p.add_argument('--resume-inspected-interruption', action='store_true',
                   help='Only the recorded latest OFF72 interruption after its new onsite review')
    p.add_argument('--camera-observed-recheck', action='store_true',
                   help='A new binding from the completed midpoint record with continuous fresh-camera leases')
    a = p.parse_args()
    if a.resume_inspected_interruption and a.camera_observed_recheck:
        p.error('Choose one current reference source')
    run(a.port, a.output, a.execute_next_first_check, a.resume_inspected_interruption, a.camera_observed_recheck)
