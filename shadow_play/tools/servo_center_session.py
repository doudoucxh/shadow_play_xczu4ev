"""Windows serial transport for the dedicated single-servo centering window."""
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/calibration'))
from serial_gateway import SerialLink

SERVICE = 'unloaded-center-v1'
BOARD_DIR = '/run/media/mmcblk0p2/piying/servo-capture-20261008-r4'
DEBUG_SERVICES = frozenset(('unloaded-center-v1', 'unloaded-manual-v2',
    'attended-midpoint-v1', 'attended-angle-v1', 'attended-initial-pose-v1'))


class MotionInhibitedError(RuntimeError):
    """Explicit board rejection; transport and read-only operations still work."""


def all_off(state):
    return (state.get('armed') is False and state.get('enabled_mask') == 0
            and state.get('pending') is False)


def clean_idle_debug_state(state):
    pulses = state.get('pulse_us')
    return (state.get('service') in DEBUG_SERVICES and state.get('identity') == 'SP10'
            and state.get('period_us') == 20000 and state.get('clock_hz') == 100000000
            and all_off(state) and type(state.get('enabled_mask')) is int
            and type(state.get('faults')) is int and state['faults'] == 0
            and type(state.get('sequence')) is int and 0 <= state['sequence'] <= 0xffffffff
            and isinstance(pulses, list) and len(pulses) == 10
            and all(type(x) is int and 500 <= x <= 2500 for x in pulses)
            and not state.get('output_lost')
            and state.get('manual_diagnostics_available', True) is True)


def wait_for_root_after_idle_exit(port, timeout):
    observed = b''
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        observed += port.read(4096)
        if re.search(rb'shadowdpupetalinux:[^\r\n]*#\s*$', observed):
            return 'root'
        if re.search(rb'(?:password|login)\s*:\s*$', observed, re.I):
            raise RuntimeError('旧服务已退出，但板端需要重新登录；未发送新服务启动命令。')
    raise RuntimeError('未确认旧服务退出到 root；未启动新服务，也未发送动作。')


def await_prompt(port, timeout=4, service=SERVICE, allow_idle_switch=False):
    observed = b''
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        observed += port.read(4096)
        for line in observed.splitlines():
            prefix = line.find(b'@@SP10@@')
            if prefix >= 0:
                try:
                    result = json.loads(line[prefix+8:])
                except (ValueError, UnicodeDecodeError):
                    continue
                if result.get('ready') is True:
                    state = result.get('state', {})
                    if state.get('service') != service:
                        if (not allow_idle_switch or service not in DEBUG_SERVICES
                                or not clean_idle_debug_state(state)):
                            raise RuntimeError('板端是其他服务且不能自动切换；请先停止输出、关闭旧窗口并检查状态。')
                        # Only stop a recognized, fault-free, already-OFF debug service.
                        # Never send a target, ARM, or shell command before seeing root.
                        port.write(b'\x03\r')
                        return wait_for_root_after_idle_exit(port, max(.1, deadline-time.monotonic()))
                    if not all_off(state):
                        raise RuntimeError('板端输出未关闭；请先停止输出。')
                    return 'service'
        if re.search(rb'shadowdpupetalinux:[^\r\n]*#\s*$', observed):
            return 'root'
        if re.search(rb'(?:password|login)\s*:\s*$', observed, re.I):
            raise RuntimeError('请先在串口工具中登录板端并执行 sudo -s，再关闭串口工具重连。')
    raise RuntimeError('未收到回中服务或 root 提示符。确认 COM 口、板子供电和登录状态。')


class CenterSession:
    service = SERVICE
    board_dir = BOARD_DIR
    board_script = 'center_console.py'
    expected_hold_seconds = 5

    def __init__(self, port_name, log_path):
        import serial
        self.link = None
        self.log = None
        self.port = serial.Serial(port=None, baudrate=115200, timeout=.10, write_timeout=.5)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port_name
        self.started = False
        try:
            self.log = Path(log_path).open('x', encoding='utf-8')
            self.port.open()
            # User explicitly connects after logging in; never type a password.
            self.port.write(b'\r')
            prompt = await_prompt(self.port, service=self.service, allow_idle_switch=True)
            if prompt == 'root':
                self.port.write(b'stty -echo\r')
                time.sleep(.15)
                self.port.read_all()
                self.port.write(('python3 -u ' + self.board_dir
                                 + '/integrations/calibration/' + self.board_script + '; stty echo\r').encode('ascii'))
                self.started = True
                if await_prompt(self.port, 6, service=self.service) != 'service':
                    raise RuntimeError('回中服务未启动。板子重启后需要先加载十路 PWM 镜像。')
            self.started = True
            self.link = SerialLink(self.port, self.log)
            state = self.status()
            if not self.valid_service(state) or not all_off(state):
                raise RuntimeError('板端不是已验证的单舵机回中服务。')
        except BaseException:
            self.close()
            raise

    def valid_service(self, state):
        return (state.get('service') == self.service and
                state.get('center_hold_seconds') == self.expected_hold_seconds)

    def _request(self, operation, payload):
        ack = self.link.exchange(operation, payload)
        if ack.get('ok') is not True:
            message = ack.get('error', '板端拒绝请求')
            if str(message).startswith('PWM motion inhibited by '):
                raise MotionInhibitedError(message)
            raise RuntimeError(message)
        return ack['result']

    def status(self):
        return self._request('status', {})

    def center(self, channel, unloaded_confirmed):
        if type(channel) is not int or not 1 <= channel <= 10 or unloaded_confirmed is not True:
            raise ValueError('请选定 1–10 号，并确认已解除机构约束。')
        state = self.status()
        if not all_off(state):
            raise RuntimeError('当前仍有输出，请先停止。')
        state = self._request('center', {'channel': channel, 'unloaded_confirmed': True})
        if (state.get('enabled_mask') != 1 << (channel-1) or state.get('armed') is not True
                or state.get('pending') or state.get('faults') or state['pulse_us'][channel-1] != 1500):
            self.stop()
            raise RuntimeError('回中输出状态不符合预期，已请求关闭。')
        return state

    def stop(self):
        state = self._request('off', {})
        if not all_off(state):
            raise RuntimeError('停止输出未得到确认，请关闭舵机电源。')
        return state

    def close(self):
        # Heartbeat must end even when cleanup itself encounters an exception.
        try:
            if self.link is not None:
                self.link.close()
            elif self.port.is_open:
                if self.started:
                    self.port.write(b'\x03')
                self.port.close()
        finally:
            if self.port.is_open:
                self.port.close()
            if self.log is not None:
                self.log.close()
