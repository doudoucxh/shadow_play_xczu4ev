"""PC PS-console transport; no password storage, retry, or reconnect movement."""
import json
import re
import time

from .service import PREFIX


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
            ready = self._receive(time.monotonic() + 6)
            if ready.get('ready') is not True or ready.get('service') != 'bus-teach-v1':
                raise RuntimeError('板端总线服务未准备好。')
            self.started = True
        except BaseException:
            self.port.close()
            raise

    def _receive(self, deadline):
        while time.monotonic() < deadline:
            self.buffer += self.port.read(4096)
            if len(self.buffer) > 32768:
                raise RuntimeError('板端输出过长。')
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line.startswith(PREFIX.encode()):
                    return json.loads(line[len(PREFIX):])
        raise TimeoutError('板端回执超时；不重发命令，FPGA租约将请求卸力。')

    def request(self, op, payload=None):
        if self.failed:
            raise RuntimeError('本次通信已经失效；不再向可能返回登录终端的串口发送请求。')
        self.sequence += 1
        request = {'seq': self.sequence, 'op': op, 'payload': payload or {}}
        try:
            self.port.write((json.dumps(request, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii'))
            reply = self._receive(time.monotonic() + .9)
            if reply.get('seq') != self.sequence or reply.get('ok') is not True:
                raise RuntimeError(reply.get('error', '回执序号不匹配；不重发。'))
            return reply['result']
        except BaseException:
            self.failed = True
            raise

    @staticmethod
    def _samples(rows):
        return {int(n): row for n, row in rows.items()}

    def connect(self):
        result = self.request('hello')
        if (result.get('service') != 'bus-teach-v1' or result.get('profile') != self.profile.fingerprint
                or result.get('simulation') is not False):
            raise RuntimeError('板端与电脑端的ID/角度/限位配置不同。')
        self.motion_allowed = result.get('motion_allowed') is True
        return self._samples(result['positions'])

    def read(self, numbers):
        return self._samples(self.request('read', {'numbers': numbers}))

    def move(self, targets, milliseconds):
        return self.request('move', {'targets': targets, 'duration_ms': milliseconds, 'attended': True})

    def release(self, numbers):
        return self.request('release', {'numbers': numbers, 'attended': True})

    def stop(self):
        return self.request('stop')

    def close(self):
        try:
            if self.started and not self.failed and self.port.is_open:
                self.request('quit')
        finally:
            self.port.close()
