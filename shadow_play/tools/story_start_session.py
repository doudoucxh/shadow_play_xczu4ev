"""Bounded Windows serial client for the reviewed story-start panel.

Connect only to the dedicated preinstalled service or an observed root prompt.
No passwords, motion initialization, automatic reconnect or uncertain retries.
"""
import base64
import json
from pathlib import Path
import re
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from attended_recovery_review import review

PREFIX = b'@@SP10START@@'
SERVICE = 'reviewed-story-start-v1'
BOARD_SCRIPT = '/tmp/piying-story-start-20261015/story_start_console.py'
BOARD_LIB = '/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration'

class BoardRejected(ValueError):
    pass


class StoryStartSession:
    def __init__(self, port_name, log_path):
        import serial
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.failed = False
        self.worker = None
        self.service_started = False
        self.log = Path(log_path).open('x', encoding='utf-8')
        self.port = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=.4)
        self.port.dtr = False; self.port.rts = False; self.port.port = port_name
        try:
            self.port.open()
            self.port.write(b'\r')
            kind = self._prompt(3)
            if kind == 'root':
                # Start only the installed reviewed service, not old commissioning tools.
                self.port.write(b'stty -echo\r')
                time.sleep(.1)
                self.port.read_all()
                command = ('PYTHONPATH='+BOARD_LIB+' python3 -u '+BOARD_SCRIPT+'; stty echo\r')
                self.port.write(command.encode('ascii'))
                self.service_started = True
                if self._prompt(4) != 'service':
                    raise RuntimeError('起势服务未安装或启动失败；不会自动安装/启动旧控制程序')
            self.service_started = True
            self._request('hello', {})
            self.worker = threading.Thread(target=self._heartbeat, daemon=True)
            self.worker.start()
        except BaseException:
            self.close()
            raise

    def _prompt(self, seconds):
        data = b''
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            data = (data+self.port.read(4096))[-16384:]
            for line in data.splitlines():
                index = line.find(PREFIX)
                if index >= 0:
                    try:
                        row = json.loads(line[index+len(PREFIX):])
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if row.get('ready') and row.get('state', {}).get('service') == SERVICE:
                        return 'service'
            if re.search(rb'shadowdpupetalinux:[^\r\n]*#\s*$', data):
                return 'root'
            if re.search(rb'(?:login|password)\s*:\s*$', data, re.I):
                raise RuntimeError('先在串口工具完成root登录，再关闭工具；面板不输入密码')
        raise RuntimeError('没有收到专用服务或root提示符；串口可能被占用')

    def _request(self, operation, payload):
        with self.lock:
            if self.failed:
                raise RuntimeError('串口连接已失效，禁止自动重试；请现场核查')
            req = dict(transport_id=uuid.uuid4().hex, operation=operation, payload=payload)
            wire = json.dumps(req, allow_nan=False).encode()+b'\n'
            if len(wire) > 4096:
                raise ValueError('Serial frame exceeds limit')
            try:
                self.log.write(json.dumps(dict(sent=req))+'\n'); self.log.flush()
                self.port.write(wire)
                until = time.monotonic()+.65
                while time.monotonic() < until:
                    line = self.port.readline(16385)
                    if len(line) > 16384:
                        raise RuntimeError('Oversized response')
                    pos = line.find(PREFIX)
                    if pos < 0:
                        continue
                    reply = json.loads(line[pos+len(PREFIX):])
                    if reply.get('transport_id') != req['transport_id']:
                        continue
                    self.log.write(json.dumps(dict(received=reply))+'\n'); self.log.flush()
                    if reply.get('ok') is not True:
                        raise BoardRejected(reply.get('error', '板端拒绝请求'))
                    state = reply['result']
                    if state.get('service') != SERVICE:
                        raise RuntimeError('Incorrect board service')
                    return state
                raise TimeoutError('串口应答未知，不重试；板端心跳超时会停止本次路线')
            except BoardRejected:
                raise
            except BaseException:
                self.failed = True
                self.closed.set()
                raise

    def _heartbeat(self):
        while not self.closed.wait(.2):
            try:
                self._request('heartbeat', {})
            except Exception:
                self.failed = True
                self.closed.set()
                return

    def status(self):
        return self._request('status', {})

    def load_plan(self, plan):
        result = review(plan)
        if result['reasons']:
            raise ValueError('路线未通过审核：'+', '.join(result['reasons']))
        if plan['route'].get('target_id') != 'story_start_v3':
            raise ValueError('面板只加载剧本起势路线，不加载全场或装配回中路线')
        data = json.dumps(plan, allow_nan=False).encode('utf-8')
        if len(data) > 300000:
            raise ValueError('Plan exceeds upload limit')
        self._request('upload_begin', {'bytes': len(data)})
        for offset in range(0, len(data), 1500):
            self._request('upload_chunk', {'offset': offset,
                'base64': base64.b64encode(data[offset:offset+1500]).decode('ascii')})
        return self._request('upload_end', {})

    def start(self):
        return self._request('start', {})

    def stop(self):
        return self._request('off', {})

    def close(self):
        self.closed.set()
        if self.worker is not None:
            self.worker.join(timeout=1)
        try:
            if self.port.is_open and self.service_started:
                if not self.failed:
                    try: self.stop()
                    except Exception: pass
                # Also interrupts the service if its protocol response was lost.
                try: self.port.write(b'\x03')
                except Exception: pass
        finally:
            if self.port.is_open:
                self.port.close()
            self.log.close()
