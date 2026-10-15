"""Attended fixed-route console. Opening/reading never arms outputs.

Accepts only a pre-reviewed route bound to this boot and exact active sequence.
No force, initialize, arbitrary move, incident unlock or scene playback operation.
"""
import base64
import copy
import json
import os
from pathlib import Path
import re
import select
import signal
import sys
import time

from attended_recovery_executor import RecoveryDevice
from attended_recovery_review import review, STORY_START
from servo_pwm_device import PwmDevice, Registers

PREFIX = '@@SP10START@@'
SERVICE = 'reviewed-story-start-v1'
IMAGE = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'


class Controller:
    def __init__(self, registers, boot_id, emit, *, clock=time.monotonic,
                 motion_inhibit_paths=None, cancel_path='/run/shadow-pwm-recovery-cancel'):
        self.reg = registers
        self.device = PwmDevice(registers, motion_inhibit_paths=motion_inhibit_paths)
        self.boot_id, self.emit, self.clock = boot_id, emit, clock
        self.cancel_path = cancel_path
        self.plan = None
        self.runner = None
        self.running = False
        self.holding = False
        self.handoff_deadline = None
        self.used = False
        self.last_error = None
        self.last_lease = clock()
        self.next_frame = None
        self.hold_until = None
        self.upload = None
        self.cache = {}

    def reasons(self, state):
        reasons = []
        if self.plan is None:
            reasons.append('未加载已审核恢复路线；不会自动生成起点')
        else:
            reasons.extend(review(self.plan)['reasons'])
            if self.plan.get('board_boot_id') != self.boot_id:
                reasons.append('板子启动标识不符，路线已失效')
            if type(self.plan.get('expected_sequence')) is not int or self.plan['expected_sequence'] != state['sequence']:
                reasons.append('序号与审核起点不符，不能重试旧路线')
            if self.plan.get('start', {}).get('pulses_us') != state['pulse_us']:
                reasons.append('当前指令与审核起点不符')
        if not state['armed'] or state['enabled_mask'] != 1023:
            reasons.append('十路未持续保持；此入口不从未知角度启用输出')
        if state['faults'] or state['pending']:
            reasons.append('板端有故障或未完成指令')
        if self.used:
            reasons.append('本连接的恢复机会已使用；不自动重启')
        if Path(self.cancel_path).exists():
            reasons.append('恢复取消标记仍存在')
        if self.plan is not None:
            try:
                for p in self.device.motion_inhibit_paths:
                    Path(p).read_bytes()
            except OSError:
                reasons.append('事故锁记录不可读；不能进入例外恢复')
        return reasons

    def status(self):
        state = self.device.status()
        blocked = self.reasons(state)
        return dict(service=SERVICE, pwm_state=state, board_boot_id=self.boot_id,
                    target_us=list(STORY_START), plan_loaded=self.plan is not None,
                    running=self.running, reviewed_hold=self.holding,
                    ready=not blocked and not self.running,
                    blocked_reasons=blocked, last_error=self.last_error,
                    frame_index=self.runner.index if self.runner else None)

    def stop(self, reason='operator_stop', normal=False):
        self.running = False
        self.holding = False
        self.used = True
        state = self.device.stop_after_frame() if normal else self.device.off()
        self.emit(dict(event='outputs_off', reason=reason, state=state,
                       incident_locks_removed=False, actual_position_verified=False))

    def tick(self):
        if not self.running and not self.holding:
            return
        try:
            now = self.clock()
            if now-self.last_lease > .75:
                raise RuntimeError('主机心跳中断，停止输出')
            self.runner.check()
            if self.holding:
                if now >= self.handoff_deadline:
                    self.stop('reviewed_handoff_expired', normal=True)
                else:
                    self.runner.kick()
                return
            if self.hold_until is not None:
                if now >= self.hold_until:
                    self.stop('route_complete', normal=True)
                else:
                    self.runner.kick()
                return
            if now >= self.next_frame:
                if now-self.next_frame > .04:
                    raise RuntimeError('调度迟到，不跳帧追赶')
                state = self.runner.advance()
                self.emit(dict(event='route_frame', index=self.runner.index,
                               state=state, monotonic_time=self.clock()))
                self.next_frame = self.clock()+.02
                if self.runner.index == len(self.runner.frames)-1:
                    self.hold_until = self.clock()+1
            self.runner.kick()
        except BaseException as error:
            self.last_error = str(error)
            self.stop('route_failed')
            if not isinstance(error, Exception):
                raise

    def handle(self, request):
        ident = request.get('transport_id') if isinstance(request, dict) else None
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
            raise ValueError('Invalid request identifier')
        wire = json.dumps(request, sort_keys=True, allow_nan=False)
        if ident in self.cache:
            old, result = self.cache[ident]
            if wire != old:
                raise ValueError('Identifier reused with changed request')
            return copy.deepcopy(result)
        reply = dict(transport_id=ident, ok=False)
        op = request.get('operation')
        attempted_start = False
        try:
            if set(request) != {'transport_id', 'operation', 'payload'}:
                raise ValueError('Invalid request fields')
            payload = request['payload']
            if not isinstance(payload, dict):
                raise ValueError('Payload must be object')
            if op in ('hello', 'status', 'heartbeat', 'off'):
                if payload:
                    raise ValueError('Unexpected payload')
                if op == 'off':
                    self.stop()
                if op == 'heartbeat':
                    self.last_lease = self.clock()
            elif op == 'upload_begin':
                if self.running or self.holding or set(payload) != {'bytes'} or type(payload['bytes']) is not int or not 1 <= payload['bytes'] <= 300000:
                    raise ValueError('Bounded idle plan upload required')
                self.plan = None
                self.upload = (payload['bytes'], bytearray())
            elif op == 'upload_chunk':
                if self.running or self.upload is None or set(payload) != {'offset', 'base64'}:
                    raise ValueError('No idle upload')
                data = base64.b64decode(payload['base64'], validate=True)
                total, content = self.upload
                if payload['offset'] != len(content) or len(data) > 1500 or len(content)+len(data) > total:
                    raise ValueError('Upload ordering/size mismatch')
                content.extend(data)
            elif op == 'upload_end':
                if payload or self.upload is None or self.running:
                    raise ValueError('No idle upload')
                total, content = self.upload
                self.upload = None
                if len(content) != total:
                    raise ValueError('Incomplete upload')
                plan = json.loads(content)
                result = review(plan)
                if result['reasons']:
                    raise ValueError(', '.join(result['reasons']))
                if plan['route'].get('target_id') != 'story_start_v3':
                    raise ValueError('Panel only accepts story_start_v3 routes')
                self.plan = plan
                state = self.device.status()
                if not self.reasons(state):
                    # Maintain only the exact reviewed, already-active pose.
                    # No ARM or changed pulse is sent during this short handoff.
                    self.runner = RecoveryDevice(self.reg, self.plan, state['sequence'],
                        clock=self.clock, motion_inhibit_paths=self.device.motion_inhibit_paths,
                        cancel_path=self.cancel_path)
                    self.runner.check()
                    self.emit(dict(event='reviewed_handoff', state=state, seconds=15))
                    self.holding = True
                    self.last_lease = self.clock()
                    self.handoff_deadline = self.clock()+15
            elif op == 'start':
                if payload or self.running or self.used:
                    raise ValueError('Single idle route start required')
                state = self.device.status()
                blocked = self.reasons(state)
                if blocked:
                    raise ValueError('; '.join(blocked))
                self.used = True  # No repeat even if initialization is uncertain.
                attempted_start = True
                self.runner = RecoveryDevice(self.reg, self.plan, state['sequence'],
                    clock=self.clock, motion_inhibit_paths=self.device.motion_inhibit_paths,
                    cancel_path=self.cancel_path)
                self.runner.check()
                self.emit(dict(event='route_start', state=state, position_feedback=None))
                self.running = True
                self.holding = False
                self.last_lease = self.clock()
                self.next_frame = self.clock()+.02
            else:
                raise ValueError('Unsupported operation; no force/arm/unlock command exists')
            reply.update(ok=True, result=self.status())
        except Exception as error:
            reply['error'] = str(error)
            if attempted_start:
                self.stop('start_failed')
        if op not in ('status', 'heartbeat', 'hello'):
            if len(self.cache) >= 512:
                # Off is always allowed; exhausting upload cache cannot enable motion.
                self.used = True
            else:
                self.cache[ident] = (wire, copy.deepcopy(reply))
        return reply


def main():
    marker = json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    if marker.get('sha256') != IMAGE or Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() != 'operating':
        raise RuntimeError('Verified G13 image required before MMIO')
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    registers = Registers()
    controller = None
    # Every motion event is logged and flushed before the next frame.
    log_path = Path('/tmp')/('story-start-'+str(time.time_ns())+'.jsonl')
    try:
        with log_path.open('x') as log:
            def emit(row):
                log.write(json.dumps(row)+'\n'); log.flush()
            controller = Controller(registers, boot_id, emit)
            def respond(row):
                print(PREFIX+json.dumps(row), flush=True)
            respond(dict(ready=True, state=controller.status()))
            buf = b''
            while True:
                controller.tick()
                if not select.select([sys.stdin.fileno()], [], [], .005)[0]:
                    continue
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    if len(line) > 4096:
                        raise ValueError('Console frame too large')
                    if line.strip():
                        respond(controller.handle(json.loads(line)))
                    else:
                        respond(dict(ready=True, state=controller.status()))
                    controller.tick()
                if len(buf) > 4096:
                    raise ValueError('Partial frame too large')
    finally:
        if controller is not None and (controller.running or controller.holding):
            controller.device.off()
        registers.close()


if __name__ == '__main__':
    main()
