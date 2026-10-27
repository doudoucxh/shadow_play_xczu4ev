"""PC PS-console transport; no password storage, retry, or reconnect movement."""
import json
import re
import time

from .service import PREFIX, BOARD_ONLY
from .protocol import ServoUnavailable


class RemoteDevice:
    simulation = False

    def __init__(self, profile, port_name):
        import serial
        self.profile = profile
        self.sequence = 0
        self.buffer = b''
        self.started = False
        self.failed = False
        self.port = serial.Serial(port=None, baudrate=115200, timeout=.02, write_timeout=.3)
        self.port.dtr = self.port.rts = False
        self.port.port = port_name
        try:
            self.port.open()
            # Launch only from an observed login shell. An unrecognized existing
            # service is never interrupted or switched automatically.
            self.port.write(b'\r')
            deadline = time.monotonic() + 3
            observed = b''
            while time.monotonic() < deadline:
                observed += self.port.read(4096)
                if re.search(rb'shadowdpupetalinux:[^\r\n]*#\s*$', observed):
                    self.port.write(b'stty -echo\r')
                    time.sleep(.1)
                    self.port.read_all()
                    # Directory comes from the fixed layout registry, never user shell text.
                    directory = profile.layout.board_directory
                    self.port.write(f'cd /run/media/mmcblk0p2/piying/{directory} && sh start_console.sh; stty echo\r'.encode('ascii'))
                    break
                if re.search(rb'(?:password|login)\s*:\s*$', observed, re.I):
                    raise RuntimeError('请先用串口工具登录板端 root，关闭串口工具后再连接。')
                if PREFIX.encode() in observed or b'@@SP10@@' in observed:
                    raise RuntimeError('串口已有服务，请先在原窗口停止并退出。')
            else:
                raise TimeoutError('没有识别到板端登录提示符；未发送启动或运动命令。')
            ready = self._receive(time.monotonic() + 6, startup=True)
            if ready.get('ready') is not True or ready.get('service') != 'bus-teach-v1':
                raise RuntimeError('板端总线服务未准备好。')
            self.started = True
            self.capabilities = ready.get('capabilities', [])
            self.motion_active = False
        except BaseException:
            self.port.close()
            raise

    def _startup_error(self, output):
        # Startup failures are plain shell/argparse text in existing SD bundles.
        # Recognize them without changing the bundle or sending another command.
        lower = output.lower()
        if b'verify bus electrical compatibility before transmitting' in lower:
            return ('板端拒绝查询：尚未核实总线信号与3.3V FPGA的电气兼容性。'
                    '加载FPGA不代表已完成验证；请先完成电气核实，勿直接修改就绪标记。')
        for line in output.splitlines():
            missing = any(s in line.lower() for s in (b'no such file', b"can't cd", b'cannot cd', b"can't open"))
            if not missing:
                continue
            if b'/run/shadow-bus-servo-loaded.json' in line:
                return '当前启动没有总线FPGA加载标记；若板子已重启，需按断电加载流程重新加载对应镜像。'
            # Match the error line, not unrelated paths earlier in a traceback.
            if self.profile.layout.board_directory.encode() in line or b'start_console.sh' in line:
                if self.profile.layout.name == 'dual':
                    return ('板端未安装当前十轴双总线程序。老虎ID7～10临时接原1～4口时，'
                            '请关闭此窗口，打开“老虎四舵机临时调试.cmd”。')
                return '板端缺少老虎四口程序或启动脚本，请检查SD卡安装目录 bus-servo-tiger-four-v1。'
        if any(s in output for s in (b'different FPGA wiring layout', b'different wiring layout',
                                     b'no matching bus candidate', b'Bus identity/clock/baud mismatch')):
            return '当前FPGA镜像与上位机接线配置不匹配；请核对四口BT04或双总线BS10，不能使用旧PWM镜像。'
        return None

    def _receive(self, deadline, *, startup=False):
        startup_output = b''
        while time.monotonic() < deadline:
            chunk = self.port.read(4096)
            self.buffer += chunk
            if startup:
                startup_output += chunk
            if max(len(self.buffer), len(startup_output)) > 32768:
                raise RuntimeError('板端输出过长。')
            if startup:
                error = self._startup_error(startup_output)
                if error:
                    raise RuntimeError(error)
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line.startswith(PREFIX.encode()):
                    return json.loads(line[len(PREFIX):])
            if startup and re.search(rb'shadowdpupetalinux:[^\r\n]*#\s*$', self.buffer):
                raise RuntimeError('板端总线服务启动失败，已返回登录终端；未建立舵机连接。请检查板端程序和镜像配置。')
        if startup:
            raise TimeoutError('等待板端总线服务启动超时；未建立舵机连接，不自动重试。')
        raise TimeoutError('板端回执超时；不重发命令，FPGA租约将请求卸力。')

    def request(self, op, payload=None):
        if self.failed:
            raise RuntimeError('本次通信已经失效；不再向可能返回登录终端的串口发送请求。')
        self.sequence += 1
        request = {'seq': self.sequence, 'op': op, 'payload': payload or {}}
        try:
            self.port.write((json.dumps(request, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii'))
            reply = self._receive(time.monotonic() + .9)
            if reply.get('seq') != self.sequence:
                raise RuntimeError('回执序号不匹配；不重发。')
            if reply.get('ok') is False and reply.get('servo_unavailable') is True and not self.motion_active:
                raise ServoUnavailable(reply.get('error', '舵机反馈不可用，板子连接保留。'))
            if reply.get('ok') is not True:
                raise RuntimeError(reply.get('error', '回执序号不匹配；不重发。'))
            return reply['result']
        except ServoUnavailable:
            raise
        except BaseException:
            self.failed = True
            raise

    @staticmethod
    def _samples(rows):
        return {int(n): row for n, row in rows.items()}

    def connect(self):
        if BOARD_ONLY not in self.capabilities:
            raise RuntimeError('板端程序尚不支持断电连接，请先更新板端服务；未发送舵机查询。')
        result = self.request('hello')
        if (result.get('service') != 'bus-teach-v1' or result.get('profile') != self.profile.fingerprint
                or result.get('simulation') is not False):
            raise RuntimeError('板端与电脑端的ID/角度/限位配置不同。')
        self.motion_allowed = result.get('motion_allowed') is True
        return self._samples(result['positions'])

    def board_status(self):
        return self.request('status')

    def probe(self, numbers):
        return self._samples(self.request('probe', {'numbers': numbers}))

    def read(self, numbers):
        return self._samples(self.request('read', {'numbers': numbers}))

    def move(self, targets, milliseconds):
        self.motion_active = True
        return self.request('move', {'targets': targets, 'duration_ms': milliseconds, 'attended': True})

    def release(self, numbers):
        self.motion_active = True
        return self.request('release', {'numbers': numbers, 'attended': True})

    def stop(self):
        if not self.motion_active:
            return {'state': 'no_motion_lease', 'physical_stop_verified': False}
        result = self.request('stop')
        self.motion_active = False
        return result

    def close(self):
        try:
            if self.started and not self.failed and self.port.is_open:
                self.request('quit')
        finally:
            self.port.close()
