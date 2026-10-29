"""Single serial owner for the pose-library window; never connects on startup."""
import queue
import threading

from .device import SimulationDevice
from .editing import PoseCaptureError, validate_pose
from .pose_library import ROOT, load_catalog, move_targets
from .protocol import ServoUnavailable
from .session import TeachingSession
from .transport import RemoteDevice


class PoseWorker(threading.Thread):
    def __init__(self, commands, events, stop_flag):
        super().__init__(daemon=True)
        self.commands, self.events, self.stop_flag = commands, events, stop_flag
        self.session = None
        self.numbers = list(range(1, 7))
        self.pending = None

    def emit(self, kind, value=None):
        self.events.put((kind, value))

    def close_session(self):
        self.pending = None
        if self.session:
            try:
                self.session.close()
            finally:
                self.session = None

    def handle(self, op, value):
        if op == 'connect':
            if self.session:
                raise ValueError('请先断开已有连接。')
            profile, simulation, port = value
            device = SimulationDevice(profile) if simulation else RemoteDevice(profile, port)
            try:
                self.session = TeachingSession(profile, device, ROOT / 'logs/bus_servo/pose_library')
                self.session.cancel_requested = self.stop_flag.is_set
            except BaseException:
                device.close()
                raise
            self.emit('connected', dict(simulation=simulation,
                motion_allowed=simulation or device.motion_allowed,
                release_allowed=simulation or device.release_allowed))
        elif op == 'disconnect':
            self.close_session()
            self.emit('disconnected')
        elif op == 'select':
            self.numbers = value
        elif self.session:
            s = self.session
            if self.pending:
                raise ValueError('请等待本次动作到位，或按停止。')
            if op == 'probe':
                rows = s.probe(value)
                self.emit('ready', sorted(s.ready_axes))
                self.emit('feedback', rows)
            elif op == 'capture':
                token, key = value
                numbers = load_catalog()[1][key]['axes']
                pose = s.capture_pose(numbers)
                if not self.stop_flag.is_set():
                    self.emit('captured', (token, key, pose))
            elif op in ('move', 'recall'):
                payload, seconds, attended = value
                if not s.device.simulation and (not attended or not s.device.motion_allowed):
                    raise ValueError('请确认现场条件及板端运动权限。')
                if op == 'recall':
                    key, pose = payload
                    validate_pose(pose, s.profile)
                    if pose['selected'] != load_catalog()[1][key]['axes']:
                        raise ValueError('角色轴集合不匹配。')
                    if not s.device.simulation and pose['source'] != 'servo_feedback':
                        raise ValueError('模拟姿势不能调用到实物。')
                    targets = pose['positions']
                else:
                    targets = payload
                duration = move_targets(s, targets, seconds)
                self.pending = (s.clock() + duration, targets)
                self.emit('moving', duration)
            elif op == 'release':
                numbers, attended = value
                if not s.device.simulation and (not attended or not s.device.release_allowed):
                    raise ValueError('请确认现场条件及板端卸力权限。')
                s.require_feedback(numbers)
                s.device.release(numbers)
                self.emit('message', '所选角色已回复卸力命令；扶稳机构后手摆，再读取保存。')
            elif op == 'drag':
                if not s.device.simulation:
                    raise ValueError('模拟手摆只用于离线模式。')
                s.device.drag(value)
        else:
            raise ValueError('请先连接并检测舵机。')

    def run(self):
        shutdown = False
        while True:
            try:
                if self.stop_flag.is_set():
                    self.stop_flag.clear()
                    shutdown = False
                    while True:
                        try:
                            op, _ = self.commands.get_nowait()
                            shutdown |= op == 'shutdown'
                        except queue.Empty:
                            break
                    self.pending = None
                    if self.session:
                        self.session.stop()
                    self.emit('stopped')
                    if shutdown:
                        self.close_session()
                        self.emit('closed')
                        return
                try:
                    op, value = self.commands.get(timeout=.02)
                except queue.Empty:
                    op = None
                if op == 'shutdown':
                    shutdown = True
                    self.close_session()
                    self.emit('closed')
                    return
                if op:
                    try:
                        self.handle(op, value)
                    except (ValueError, PoseCaptureError) as exc:
                        if self.session and getattr(self.session.device, 'failed', False):
                            raise RuntimeError(str(exc)) from exc
                        self.emit('rejected', str(exc))
                    self.emit('done')
                if self.session:
                    s = self.session
                    if self.pending and s.clock() >= self.pending[0]:
                        targets = self.pending[1]
                        rows = s.read([int(n) for n in targets])
                        if self.stop_flag.is_set():
                            continue
                        for key, p in targets.items():
                            a = s.profile.axes[int(key)]
                            if abs(a.degrees(rows[int(key)]['p']) - a.degrees(p)) > 2:
                                raise RuntimeError(f'{key}号未到目标位置，已停止本次动作。')
                        self.pending = None
                        self.emit('feedback', rows)
                        self.emit('arrived')
                    rows, _ = s.tick(self.numbers)
                    if rows:
                        self.emit('feedback', rows)
            except ServoUnavailable as exc:
                if self.pending:
                    self.fail(exc)
                else:
                    if self.session:
                        self.session.ready_axes.clear()
                        self.session.last_feedback.clear()
                    self.emit('unavailable', str(exc))
            except Exception as exc:
                self.fail(exc)
                if shutdown:
                    self.emit('closed')
                    return

    def fail(self, exc):
        self.pending = None
        try:
            if self.session:
                self.session.stop()
        except Exception:
            pass
        try:
            self.close_session()
        except Exception:
            pass
        self.emit('error', str(exc))
