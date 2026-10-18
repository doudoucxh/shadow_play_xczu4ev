"""Private ordinary-user Xvfb screen; no network listener or motor devices."""
import mmap
import os
from pathlib import Path
import secrets
import struct
import subprocess
import time


class X11Pointer:
    """Send panel events directly to our authenticated display, without BiDi round trips."""
    def __init__(self, display, authority):
        import ctypes
        self.x = ctypes.CDLL('/usr/lib/libX11.so.6')
        self.t = ctypes.CDLL('/usr/lib/libXtst.so.6')
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XFlush.argtypes = self.x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
        self.t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
        previous = os.environ.get('XAUTHORITY')
        try:
            os.environ['XAUTHORITY'] = str(authority)
            self.handle = self.x.XOpenDisplay(display.encode('ascii'))
        finally:
            if previous is None: os.environ.pop('XAUTHORITY', None)
            else: os.environ['XAUTHORITY'] = previous
        if not self.handle: raise RuntimeError('Cannot open private display for panel input')

    def send(self, actions):
        # Preserve every stroke point and every down/up edge in original order.
        for action, point in actions:
            if action not in ('move','down','up','cancel'): raise ValueError('Invalid pointer action')
            if point is not None:
                px, py = point
                if not (0 <= px < 1024 and 0 <= py < 600): raise ValueError('Invalid pointer coordinate')
                self.t.XTestFakeMotionEvent(self.handle,0,px,py,0)
            if action in ('down','up','cancel'):
                self.t.XTestFakeButtonEvent(self.handle,1,int(action=='down'),0)
        if actions: self.x.XFlush(self.handle)

    def close(self):
        if self.handle:
            self.send([('cancel',None)])
            self.x.XCloseDisplay(self.handle)
            self.handle = None


def xwd_layout(header, file_size):
    if len(header) != 100:
        raise ValueError('Incomplete XWD header')
    values = struct.unpack('!25I', header)
    size, version, form, depth, width, height = values[:6]
    colors = values[19]
    offset = size + colors * 12
    if (not 100 <= size <= 4096 or version != 7 or form != 2 or depth != 24 or
            (width, height) != (1024, 600) or values[6] != 0 or values[7] != 0 or
            values[11] != 32 or values[12] != width*4 or
            values[14:17] != (0xff0000, 0xff00, 0xff) or colors > 256 or
            file_size != offset+width*height*4):
        raise ValueError('Unexpected Xvfb pixel layout')
    return offset, width, height


class VirtualScreen:
    def __init__(self, binary, work):
        self.binary, self.work = Path(binary), Path(work)
        self.process = self.mapping = self.file = None
        self.display = ':91'
        self.authority = self.work/'Xauthority'

    def start(self):
        if os.geteuid() == 0:
            raise RuntimeError('Virtual screen must run as an ordinary user')
        if Path('/tmp/.X91-lock').exists() or Path('/tmp/.X11-unix/X91').exists():
            raise RuntimeError('Private display 91 is already in use')
        folder = self.work/'framebuffer'
        folder.mkdir(mode=0o700, exist_ok=True)
        # A private MIT cookie, even though TCP is disabled. Never use -ac.
        def field(data): return struct.pack('!H', len(data))+data
        record = struct.pack('!H', 65535)+field(b'')+field(b'91')+field(b'MIT-MAGIC-COOKIE-1')+field(secrets.token_bytes(16))
        self.authority.write_bytes(record)
        self.authority.chmod(0o600)
        environment = os.environ.copy()
        environment['LD_LIBRARY_PATH'] = str(self.binary.parent.parent/'lib')
        environment['XKB_BINDIR'] = str(self.binary.parent)
        self.process = subprocess.Popen([str(self.binary), self.display, '-screen', '0', '1024x600x24',
            '-fbdir', str(folder), '-nolisten', 'tcp', '-noreset', '-auth', str(self.authority),
            '-fp', 'built-ins', '-xkbdir', str(self.binary.parent.parent/'share/X11/xkb')], env=environment)
        path = folder/'Xvfb_screen0'
        for _ in range(100):
            if self.process.poll() is not None:
                raise RuntimeError('Virtual display stopped during startup')
            if path.exists() and path.stat().st_size > 1024*600*4:
                self.file = path.open('rb')
                self.mapping = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
                self.offset, self.width, self.height = xwd_layout(self.mapping[:100], len(self.mapping))
                return
            time.sleep(.05)
        raise TimeoutError('Virtual display did not create its framebuffer')

    def jpeg(self):
        import cv2
        import numpy as np
        if self.process.poll() is not None:
            raise RuntimeError('Virtual display exited')
        pixels = np.frombuffer(self.mapping[self.offset:], np.uint8).reshape(self.height, self.width, 4)
        frame = cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR)
        ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok: raise RuntimeError('Framebuffer encoding failed')
        return data.tobytes()

    def pixels(self):
        if self.process.poll() is not None:
            raise RuntimeError('Virtual display exited')
        # Local tmpfs transport: avoid compressing and decoding every frame.
        return b'BGRA'+self.mapping[self.offset:]

    def close(self):
        if self.mapping: self.mapping.close(); self.mapping = None
        if self.file: self.file.close(); self.file = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        self.authority.unlink(missing_ok=True)
