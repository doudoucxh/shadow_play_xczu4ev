"""Bounded, explicitly requested ID10 brake stream; not a motion controller.

Default invocation is offline. This cannot prevent motion before a powered
servo accepts a command, and an ACK is not physical-stop verification.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import time

FRAME = b'#010PULM!'
OFFSET = 0x400
INTERVAL = .02
MAX_SECONDS = 30


def stream_brake(reg, seconds=MAX_SECONDS, *, clock=time.monotonic,
                 sleep=time.sleep, canceled=lambda: False, emit=lambda event: None):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= MAX_SECONDS:
        raise ValueError('Brake window must be in (0, 30] seconds')
    started = clock()
    deadline = started + seconds
    next_send = started
    maximum_frames = math.ceil(seconds / INTERVAL)
    frames, received, last_rx = 0, bytearray(), None

    def finish(status, states=None):
        result = {'status': status, 'frames_queued': frames, 'rx_hex': received.hex(),
                  'elapsed_s': clock() - started, 'bus_states': states,
                  'physical_stop_verified': False, 'startup_motion_prevented': False}
        emit({'event': 'finished', **result})
        return result

    while clock() < deadline:
        if canceled():
            return finish('canceled')
        states = [reg.read(n) for n in (0x100, 0x200, 0x300, 0x400)]
        if reg.read(8) or reg.read(0x10) or any(v >> 24 for v in states):
            return finish('controller_or_uart_fault', states)
        if any(states[:3]):
            return finish('unexpected_other_port_activity', states)
        busy, count = bool(states[3] & 1), (states[3] >> 8) & 511
        if frames == 0 and (busy or count):
            return finish('initial_bus_not_idle', states)
        if count:
            if len(received) + count > 256:
                return finish('oversized_reply', states)
            for _ in range(count):
                received.append(reg.read(OFFSET + 4) & 255)
            last_rx = clock()
        # Any received byte stops further transmissions. Wait briefly for the
        # current reply; never discard a partial reply to continue the stream.
        if received:
            if not busy and clock() - last_rx >= .002:
                reply = bytes(received).strip(b'\r\n')
                if reply == b'#010POK!':
                    return finish('acknowledged_id10', states)
                if reply == b'#OK!':
                    return finish('acknowledged_without_id', states)
                return finish('unrecognized_reply', states)
        elif not busy and clock() >= next_send and frames < maximum_frames:
            if canceled() or clock() >= deadline:
                break
            # Only the fourth-port staging and TX-start registers are written.
            # No ARM, heartbeat, reset, fault-clear, broadcast or release.
            emit({'event': 'queueing', 'sequence': frames + 1,
                  'elapsed_s': clock() - started, 'tx_hex': FRAME.hex()})
            for index, byte in enumerate(FRAME):
                reg.write(OFFSET + 8, index << 8 | byte)
            if canceled() or clock() >= deadline:
                return finish('canceled_before_tx')
            reg.write(OFFSET + 12, len(FRAME))
            frames += 1
            next_send = clock() + INTERVAL  # no catch-up burst after a delay
            emit({'event': 'transmitting', 'frames_queued': frames,
                  'remaining_s': max(0, deadline - clock())})
        sleep(min(.001, max(0, deadline - clock())))
    return finish('canceled' if canceled() else 'window_expired',
                  [reg.read(n) for n in (0x100, 0x200, 0x300, 0x400)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--binding', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'offline': True, 'id': 10, 'pin': 'G13',
                          'frame_ascii': FRAME.decode(), 'window_s': MAX_SECONDS,
                          'interval_s': INTERVAL, 'maximum_frames': 1500,
                          'physical_stop_guaranteed': False}))
        return
    if args.binding is None:
        parser.error('--binding is required for execution')
    binding = json.loads(args.binding.read_text())
    root = Path('/run/media/mmcblk0p2/piying/bus-servo-tiger-four-v1')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(Path(__file__)) != binding['program_sha256']:
        raise RuntimeError('Brake program changed after review')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot != binding['boot_id'] or sha(root/'MANIFEST.json') != binding['package_sha256']:
        raise RuntimeError('Boot or installed package changed')
    package = json.loads((root/'MANIFEST.json').read_text())
    for name, digest in package['files'].items():
        if sha(root/name) != digest:
            raise RuntimeError('Installed file changed: ' + name)
    marker = json.loads(Path('/run/shadow-bus-servo-loaded.json').read_text())
    if marker['sha256'] != binding['image_sha256'] or marker['boot_id'] != boot:
        raise RuntimeError('Loaded image changed')
    incident = Path('/run/shadow-pwm-motion-inhibit')
    if sha(incident) != binding['incident_sha256']:
        raise RuntimeError('Incident marker changed')
    if sha(root/'FEEDBACK_ATTEMPT_20261027.jsonl') != binding['canceled_query_sha256']:
        raise RuntimeError('Canceled query evidence changed')
    from shadow_play.bus_servo.device import Mmio
    from shadow_play.bus_servo.model import Profile
    profile = Profile.load(root/'shadow_play/config/bus_servo_tiger_four.json')
    if (profile.layout.name != 'tiger-four-port' or profile.axes[10].ident != 10
            or profile.layout.pins[profile.axes[10].bus] != 'G13'
            or profile.data.get('electrical_3v3_verified') is not True):
        raise RuntimeError('ID10 wiring/electrical configuration changed')
    for name, digest in marker['boot_hashes'].items():
        if sha(Path('/run/media/mmcblk0p1')/name) != digest:
            raise RuntimeError('Boot file changed')
    reg = Mmio(root/'bus_servo.manifest.json', expected_layout='tiger-four-port')
    run = root/'id10-brake-20261027-v1'
    try:
        if any(reg.read(n) for n in (8, 16, 256, 512, 768, 1024)):
            raise RuntimeError('Initial controller is not idle; no reset or clear is attempted')
        run.mkdir(exist_ok=False)  # one new attempt, never reuse/cancel old markers
        canceled = [False]
        def cancel(signum, frame):
            canceled[0] = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, cancel)
        metadata = {'boot_id': boot, 'image_sha256': marker['sha256'],
                    'binding': binding, 'frame_ascii': FRAME.decode(),
                    'scope': 'ID10 brake only; no angle/release/configuration commands'}
        (run/'binding.json').write_text(json.dumps(metadata, indent=2))
        last_progress = [-1.0]
        with (run/'events.jsonl').open('x') as journal:
            def emit(event):
                journal.write(json.dumps(event) + '\n')
                journal.flush()
                if event['event'] in ('transmitting', 'finished'):
                    now = time.monotonic()
                    if event['event'] == 'finished' or now - last_progress[0] >= .2:
                        tmp = run/'status.tmp'
                        tmp.write_text(json.dumps({'boot_id': boot, 'updated_monotonic': now, **event}))
                        tmp.replace(run/'status.json')
                        last_progress[0] = now
            result = stream_brake(reg, canceled=lambda: canceled[0], emit=emit)
        result.update(boot_id=boot, image_sha256=marker['sha256'],
                      incident_sha256=sha(incident),
                      final_faults=reg.read(8), final_lease=reg.read(16))
        (run/'result.json').write_text(json.dumps(result, indent=2))
        print('ID10_BRAKE_RESULT ' + json.dumps(result), flush=True)
    finally:
        reg.close()


if __name__ == '__main__':
    main()
