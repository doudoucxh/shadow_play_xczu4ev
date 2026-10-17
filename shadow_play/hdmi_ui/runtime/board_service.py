"""Board-local camera/DPU bridge. No PWM, rail driver, or motion unlock entry.

The worker owns USB capture and publishes a single atomic RAM file. HTTP never
accepts a command line, register, file path, or a fabricated camera observation.
"""
import base64
import json
import math
import os
from pathlib import Path
import platform
import secrets
import subprocess
import tempfile
import threading
import time

MAX_FRAME_BYTES = 1500000
MAX_FRAME_AGE = 0.75
POINTS = ('head', 'leftShoulder', 'rightShoulder', 'leftElbow',
          'rightElbow', 'leftWrist', 'rightWrist')
MOTION_REASON = '丝杆驱动、回零和行程未核验；皮影坐标映射未验收，动作锁保留'


class Unavailable(RuntimeError):
    pass


def decode_live_frame(path, now, started):
    """Reject old/invalid packets, even if the capture process still exists."""
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_FRAME_BYTES + 1)
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError('frame exceeds limit')
    packet = json.loads(raw)
    if not isinstance(packet, dict) or type(packet.get('version')) is not int or packet['version'] != 1:
        raise ValueError('unsupported frame format')
    session = packet.get('session_id', '')
    if not isinstance(session, str) or len(session) != 32 or any(c not in '0123456789abcdef' for c in session):
        raise ValueError('invalid camera session')
    seq = packet.get('sequence')
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError('invalid camera sequence')
    captured = packet.get('captured_s')
    if isinstance(captured, bool) or not isinstance(captured, (float, int)) or not math.isfinite(captured):
        raise ValueError('invalid capture time')
    if captured < started or not 0 <= now - captured <= MAX_FRAME_AGE:
        raise ValueError('camera frame is stale')
    if packet.get('width') != 640 or packet.get('height') != 360:
        raise ValueError('unexpected preview dimensions')
    pose = packet.get('pose')
    if not isinstance(pose, dict) or not set(pose).issubset(POINTS):
        raise ValueError('invalid pose points')
    for xy in pose.values():
        if not isinstance(xy, list) or len(xy) != 2 or any(
                isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in xy):
            raise ValueError('invalid pose coordinates')
    jpeg = packet.get('jpeg_base64')
    if not isinstance(jpeg, str):
        raise ValueError('missing camera JPEG')
    data = base64.b64decode(jpeg, validate=True)
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('invalid JPEG envelope')
    return dict(version=1, session_id=session, sequence=seq, width=640, height=360,
                pose=pose, jpeg_base64=jpeg, captured_age_ms=round((now-captured)*1000, 1))


class BoardCamera:
    def __init__(self, runner):
        self.runner = Path(runner).resolve()
        self.lock = threading.RLock()
        self.folder = None
        self.process = None
        self.log = None
        self.started = self.last_request = 0.0
        self.session = None
        self.sequence = -1
        self.error = ''

    def configuration_error(self):
        if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
            return '当前不是 ARM64 板端；摄像头与 DPU 尚未连接'
        if not self.runner.is_file():
            return '缺少板端 USB/FOLLOW 启动器'
        if not Path('/opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel').is_file():
            return '板端 Pose9 模型不存在'
        if not list(Path('/dev').glob('video[0-9]*')):
            return '板端没有 USB 视频采集设备'
        return ''

    def start(self):
        with self.lock:
            self.last_request = time.monotonic()
            if self.process and self.process.poll() is None:
                return
            error = self.configuration_error()
            if error:
                raise Unavailable(error)
            # Never steal the existing camera or display; stop it separately only
            # after its actual identity and ownership have been reviewed.
            for unit in ('shadow-video.service', 'shadow-yolo-follow.service', 'shadow-usb-preview.service'):
                try:
                    active = subprocess.run(['systemctl', 'is-active', '--quiet', unit],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    raise Unavailable('无法核对现有视觉服务，请先检查板端进程')
                if active.returncode == 0:
                    raise Unavailable('相机被已有视觉服务占用：'+unit)
            self.stop()
            self.folder = Path(tempfile.mkdtemp(prefix='shadow-ui-live-'))
            os.chmod(str(self.folder), 0o700)
            self.log = (self.folder / 'worker.log').open('wb')
            self.started = self.last_request = time.monotonic()
            self.session, self.sequence, self.error = None, -1, ''
            try:
                self.process = subprocess.Popen([
                    '/bin/sh', str(self.runner), '--display', 'none', '--no-send',
                    '--ui-feed-file', str(self.folder / 'latest.json')],
                    stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                    start_new_session=True)
            except OSError:
                self.stop()
                raise Unavailable('无法启动板端识别进程')

    def frame(self, touch=True):
        with self.lock:
            if touch:
                self.last_request = time.monotonic()
            if not self.process or self.process.poll() is not None:
                if self.process:
                    self.error = '识别进程已退出，请检查板端 worker.log'
                raise Unavailable(self.error or '识别尚未启动')
            try:
                packet = decode_live_frame(self.folder / 'latest.json', time.monotonic(), self.started)
                if self.session is not None and packet['session_id'] != self.session:
                    raise ValueError('unexpected producer session')
                if packet['sequence'] < self.sequence:
                    raise ValueError('sequence went backwards')
                self.session, self.sequence = packet['session_id'], packet['sequence']
                return packet
            except (OSError, ValueError, TypeError, KeyError):
                raise Unavailable('等待新的相机画面与 DPU 识别结果')

    def status(self):
        with self.lock:
            running = bool(self.process and self.process.poll() is None)
            try:
                self.frame(touch=False)
                live = True
            except Unavailable:
                live = False
            return dict(configured=not bool(self.configuration_error()), running=running,
                        live=live, error=self.error or self.configuration_error())

    def expire(self):
        with self.lock:
            # No browser/viewer lease: release the owned camera, never replay input.
            if self.process and time.monotonic()-self.last_request > 10:
                self.stop()

    def stop(self):
        with self.lock:
            process, self.process = self.process, None
            if process and process.poll() is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # The worker starts a capture subprocess. Kill only this
                    # dedicated process group, never an unrelated service.
                    import signal
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=2)
            if self.log:
                self.log.close()
                self.log = None
            if self.folder:
                # Preserve the diagnostic text only; no camera frame persists.
                for path in list(self.folder.glob('latest.json*')) + list(self.folder.glob('.latest.json.*')):
                    if path.is_file():
                        path.unlink()
            self.session, self.sequence = None, -1


class BoardBridge:
    def __init__(self, camera, audio=None):
        self.camera = camera
        self.audio = audio
        self.token = secrets.token_urlsafe(32)
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()

    def watch(self):
        while not self.closed.wait(.5):
            self.camera.expire()
            if self.audio: self.audio.expire()

    def status(self):
        return dict(app='shadow-theatre-board', token=self.token, camera=self.camera.status(),
                    audio=self.audio.status() if self.audio else dict(configured=False),
                    motion=dict(ready=False, rails=False, puppet=False, classic=False,
                                reason=MOTION_REASON, actual_position_known=False))

    def control(self, request):
        # There is intentionally no arbitrary PWM/motion implementation: the
        # repository has no commissioned rail driver or validated pose inverse.
        raise Unavailable(MOTION_REASON)

    def close(self):
        self.closed.set()
        self.thread.join(timeout=1)
        self.camera.stop()
        if self.audio: self.audio.stop()
