"""Explicit playback of the fixed original soundtrack; no motion imports."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

TRACK_SHA = 'e001fb858ab32e4d0217bd7c5262667f8f077025e12be19fb21b82a1a8bd13e7'
PLAYER_SHA = '8684834abfc45f2823c4f3992ccd15b8c5bf3150b2757d7000b7a462cd59866d'
DURATION = 67.1056875


class BoardAudio:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.process = self.log = None
        self.lock = threading.RLock()
        self.started = self.last_request = 0.
        self.error = ''
        self.finished = False

    def output(self):
        matches = []
        for path in Path('/proc/asound').glob('card[0-9]*/pcm[0-9]*p/info'):
            text = path.read_text()
            if 'USB Audio' not in text:
                continue
            card = int(re.fullmatch('card([0-9]+)', path.parent.parent.name).group(1))
            device = int(re.fullmatch('pcm([0-9]+)p', path.parent.name).group(1))
            if 0 <= card <= 31 and 0 <= device <= 31:
                matches.append((card, device))
        if len(matches) != 1:
            raise RuntimeError('未找到唯一的 USB 播放声卡，请检查音响连接')
        return matches[0]

    def configuration_error(self):
        if not (self.folder/'usb_audio_play').is_file() or not (self.folder/'wusong.mp3').is_file():
            return '板端原声播放器尚未安装'
        try: self.output()
        except (OSError, ValueError, RuntimeError) as error: return str(error)
        return ''

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.last_request = time.monotonic()
                return
            error = self.configuration_error()
            if error: raise RuntimeError(error)
            for name, expected in [('usb_audio_play', PLAYER_SHA), ('wusong.mp3', TRACK_SHA)]:
                if hashlib.sha256((self.folder/name).read_bytes()).hexdigest() != expected:
                    raise RuntimeError('原声文件或播放器校验失败')
            card, device = self.output()
            self.stop()
            self.log = tempfile.TemporaryFile(mode='w+b')
            self.process = subprocess.Popen([str(self.folder/'usb_audio_play'), str(card), str(device),
                                             '0.60', str(self.folder/'wusong.mp3')],
                                            stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
            self.started = self.last_request = time.monotonic()
            self.finished = False
            self.error = ''

    def status(self, touch=False):
        with self.lock:
            if touch: self.last_request = time.monotonic()
            running = bool(self.process and self.process.poll() is None)
            output = b''
            if self.log:
                # pread leaves the child's shared output offset untouched.
                output = os.pread(self.log.fileno(), 16384, 0)
            if self.process and not running:
                self.finished = self.process.returncode == 0 and b'PLAY_COMPLETE' in output
                if not self.finished and not self.error:
                    self.error = '原声播放未正常完成，请检查音响'
            return dict(configured=not bool(self.configuration_error()), running=running,
                        playing=running and b'PLAY_START' in output, finished=self.finished,
                        duration_s=DURATION,
                        elapsed_s=min(DURATION, max(0., time.monotonic()-self.started)) if running else (DURATION if self.finished else 0),
                        timing='player process clock; acoustic latency not measured',
                        error=self.error or self.configuration_error())

    def expire(self):
        with self.lock:
            if self.process and self.process.poll() is None and (
                    time.monotonic()-self.last_request > 10 or time.monotonic()-self.started > DURATION+10):
                self.stop()

    def stop(self):
        with self.lock:
            process, self.process = self.process, None
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
            if self.log: self.log.close(); self.log = None
            self.finished = False
