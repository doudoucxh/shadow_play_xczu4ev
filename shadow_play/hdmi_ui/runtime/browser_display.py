"""Render the real local page using Firefox BiDi; never opens motor devices.

Runs as an ordinary user. The separate HDMI sink validates fresh image packets.
Requires the bundled websocket-client; Firefox keeps its default sandbox.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time

VIEW = (1024, 600)
OUTPUT = (1280, 720)
MAX_JPEG = 3000000
HEADER = struct.Struct('!dI')
PIXEL_MAGIC = b'BGRA'
PIXEL_BYTES = VIEW[0]*VIEW[1]*4


def valid_image(data):
    if data.startswith(PIXEL_MAGIC):
        return len(data) == PIXEL_BYTES+len(PIXEL_MAGIC)
    return 0 < len(data) <= MAX_JPEG and data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')


def decode_frame(data):
    import cv2
    import numpy as np
    if not valid_image(data): raise ValueError('Invalid display image')
    if data.startswith(PIXEL_MAGIC):
        pixels = np.frombuffer(data, np.uint8, offset=4).reshape(VIEW[1],VIEW[0],4)
        return cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR)
    return cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)


def viewport_point(x, y):
    """Normalized physical screen -> contained 1024x600 page, or black margin."""
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        return None
    width = round(VIEW[0] * OUTPUT[1] / VIEW[1])
    left = (OUTPUT[0]-width)//2
    px, py = x*(OUTPUT[0]-1), y*(OUTPUT[1]-1)
    if not left <= px < left+width:
        return None
    return [min(VIEW[0]-1, round((px-left)*VIEW[0]/width)),
            min(VIEW[1]-1, round(py*VIEW[1]/OUTPUT[1]))]


def publish(path, jpeg, captured):
    if not valid_image(jpeg):
        raise ValueError('Invalid browser image')
    temporary = path.with_suffix('.tmp')
    with temporary.open('wb') as output:
        output.write(HEADER.pack(captured, len(jpeg)))
        output.write(jpeg)
    os.replace(temporary, path)


def read_packet(path, now):
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_JPEG+HEADER.size+1)
    if len(raw) < HEADER.size:
        raise ValueError('Incomplete browser packet')
    captured, length = HEADER.unpack(raw[:HEADER.size])
    jpeg = raw[HEADER.size:]
    if not 0 <= now-captured <= 2 or not 0 < length <= MAX_JPEG or length != len(jpeg):
        raise ValueError('Stale/invalid browser packet')
    if not valid_image(jpeg):
        raise ValueError('Invalid display image')
    return captured, jpeg


class Bidi:
    def __init__(self, connection):
        self.connection, self.sequence = connection, 0

    def call(self, method, params):
        self.sequence += 1
        self.connection.send(json.dumps(dict(id=self.sequence, method=method, params=params)))
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            message = json.loads(self.connection.recv())
            if message.get('id') != self.sequence:
                continue
            if message.get('type') == 'error' or 'error' in message:
                raise RuntimeError('%s: %s' % (method, message.get('message', message.get('error'))))
            return message['result']
        raise TimeoutError('Browser did not answer '+method)

    def pointer(self, context, action, point=None):
        if action == 'cancel':
            return self.call('input.releaseActions', dict(context=context))
        steps = []
        if point is not None:
            steps.append(dict(type='pointerMove', x=point[0], y=point[1], duration=0, origin='viewport'))
        if action in ('down', 'up'):
            steps.append(dict(type='pointerDown' if action == 'down' else 'pointerUp', button=0))
        if steps:
            return self.call('input.performActions', dict(context=context, actions=[
                dict(type='pointer', id='panel', parameters=dict(pointerType='mouse'), actions=steps)]))


class PanelInput:
    """Single contact ABS_X/Y panel or relative mouse. Never grabs the device."""
    EVENT = struct.Struct('@llHHi')

    def __init__(self, path, absolute):
        import fcntl
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.absolute = absolute
        self.x, self.y, self.down, self.sent_down = .5, .5, False, False
        self.dirty = False
        self.discard = False
        self.ranges = {}
        try:
            if absolute:
                keys = fcntl.ioctl(self.fd, 0x80604521, bytes(96))
                if not keys[330//8] & (1 << (330%8)):
                    raise ValueError('Not the touchscreen contact interface')
                for axis in (0, 1):
                    value, minimum, maximum, _, _, _ = struct.unpack('6i', fcntl.ioctl(self.fd, 0x80184540+axis, bytes(24)))
                    if maximum <= minimum:
                        raise ValueError('Invalid touchscreen axis range')
                    self.ranges[axis] = (minimum, maximum)
        except BaseException:
            os.close(self.fd)
            raise

    def poll(self):
        actions = []
        for _ in range(256):
            try:
                raw = os.read(self.fd, self.EVENT.size)
            except BlockingIOError:
                break
            if len(raw) != self.EVENT.size:
                raise OSError('Input device disconnected')
            _, _, kind, code, value = self.EVENT.unpack(raw)
            if kind == 0 and code == 3:  # SYN_DROPPED: release, wait for a fresh press.
                actions.append(('cancel', None))
                self.discard = True
                self.down = self.sent_down = False
                self.dirty = False
            elif self.discard:
                if kind == 1 and code in (330, 272) and value == 0:
                    self.discard = False
            elif kind == 3 and self.absolute and code in self.ranges:
                low, high = self.ranges[code]
                position = min(1., max(0., (value-low)/(high-low)))
                if code == 0: self.x = position
                else: self.y = position
                self.dirty = True
            elif kind == 2 and not self.absolute and code in (0, 1):
                if code == 0: self.x = min(1., max(0., self.x+value/OUTPUT[0]))
                else: self.y = min(1., max(0., self.y+value/OUTPUT[1]))
                self.dirty = True
            elif kind == 1 and code == (330 if self.absolute else 272) and value in (0, 1):
                self.down = bool(value)
                self.dirty = True
            elif kind == 0 and code == 0 and self.dirty:
                point = viewport_point(self.x, self.y)
                if self.sent_down and (not self.down or point is None):
                    actions.append(('up', point))
                elif self.down and not self.sent_down and point is not None:
                    actions.append(('down', point))
                elif point is not None:
                    actions.append(('move', point))
                self.sent_down = self.down and point is not None
                self.dirty = False
        return actions

    def close(self):
        os.close(self.fd)


def find_input():
    # Known physical panel first; a connected mouse remains a usable fallback.
    rows = []
    for event in Path('/sys/class/input').glob('event*'):
        try:
            name = (event/'device/name').read_text().strip()
            if name == 'OpenWare Multi-Touch-V5000': rows.insert(0, ('/dev/input/'+event.name, True))
            elif name.endswith('Mouse'): rows.append(('/dev/input/'+event.name, False))
        except OSError:
            pass
    for path, absolute in rows:
        try: return PanelInput(path, absolute), path
        except (OSError, ValueError): pass
    return None, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firefox', type=Path, required=True)
    parser.add_argument('--xvfb', type=Path, help='Private Xvfb binary for continuous framebuffer output')
    parser.add_argument('--work', type=Path, default=Path('/run/shadow-ui'))
    parser.add_argument('--fps', type=int, choices=range(1, 31), default=30)
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run renderer as an ordinary user; keep the browser sandbox')
    # The deployment bundles only this fixed pure-Python client dependency.
    sys.path.insert(0, str(Path(__file__).parent/'vendor'))
    import websocket
    import cv2
    cv2.setNumThreads(1)
    args.work.mkdir(parents=True, exist_ok=True)
    profile = args.work/'profile'
    profile.mkdir(exist_ok=True)
    # Avoid speculative spare processes on the 2 GB board. Keep the browser's
    # normal process sandbox and full-resolution screenshots.
    (profile/'user.js').write_text('\n'.join([
        'user_pref("remote.screenshot.use_readback", false);',
        'user_pref("dom.ipc.processCount", 2);',
        'user_pref("dom.ipc.processPrelaunch.enabled", false);',
    ])+'\n')
    packet = args.work/'frame.bin'
    stopping = False

    def stop(*unused):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    process = connection = panel = screen = pointer = None
    try:
        environment = os.environ.copy()
        environment['LD_LIBRARY_PATH'] = str(Path(__file__).parent/'vendor/lib')
        mode = '--headless'
        if args.xvfb:
            from virtual_screen import VirtualScreen, X11Pointer
            screen = VirtualScreen(args.xvfb, args.work)
            screen.start()
            pointer = X11Pointer(screen.display, screen.authority)
            environment.update(DISPLAY=screen.display, XAUTHORITY=str(screen.authority), MOZ_ENABLE_WAYLAND='0')
            mode = '--kiosk'
        process = subprocess.Popen([str(args.firefox), mode, '--no-remote', '--profile', str(profile),
                                    '--remote-debugging-port', '9222', '--width', '1024', '--height', '600', 'about:blank'], env=environment)
        for _ in range(100):
            if stopping or process.poll() is not None:
                raise RuntimeError('Browser stopped during startup')
            try:
                connection = websocket.create_connection('ws://127.0.0.1:9222/session', timeout=10,
                                                          suppress_origin=True, http_no_proxy=['127.0.0.1'],
                                                          skip_utf8_validation=True)  # recv() still uses strict native UTF-8 decode.
                break
            except (OSError, websocket.WebSocketException): time.sleep(.2)
        if connection is None: raise RuntimeError('Browser startup timed out')
        bidi = Bidi(connection)
        bidi.call('session.new', dict(capabilities={}))
        context = bidi.call('browsingContext.getTree', {})['contexts'][0]['context']
        bidi.call('browsingContext.setViewport', dict(context=context, viewport=dict(width=1024, height=600), devicePixelRatio=1))
        bidi.call('browsingContext.navigate', dict(context=context, url='http://127.0.0.1:8765/', wait='complete'))
        frames, report, scan, health = 0, time.monotonic(), 0, 0
        while not stopping:
            started = time.monotonic()
            if process.poll() is not None: raise RuntimeError('Browser exited')
            if panel is None and started >= scan:
                panel, name = find_input()
                if panel: print('INPUT_READY '+name, flush=True)
                scan = started+3
            if panel:
                try: actions = panel.poll()
                except OSError:
                    panel.close(); panel = None
                    actions = [('cancel', None)]
                if pointer: pointer.send(actions)
                else:
                    for action, point in actions: bidi.pointer(context, action, point)
            captured = time.monotonic()
            if screen:
                if captured >= health:
                    result = bidi.call('script.evaluate', dict(expression='document.readyState',
                        target=dict(context=context), awaitPromise=False))
                    if result.get('type') != 'success': raise RuntimeError('Browser page is unresponsive')
                    health = captured+1
                jpeg = screen.pixels()
            else:
                result = bidi.call('browsingContext.captureScreenshot', dict(context=context, origin='viewport',
                               format=dict(type='image/jpeg', quality=.88)))
                jpeg = base64.b64decode(result['data'], validate=True)
            publish(packet, jpeg, captured)
            frames += 1
            now = time.monotonic()
            if now-report >= 10:
                print(json.dumps(dict(event='browser_frames', fps=round(frames/(now-report), 2))), flush=True)
                frames, report = 0, now
            time.sleep(max(0, 1/args.fps-(time.monotonic()-started)))
    finally:
        if panel: panel.close()
        if pointer: pointer.close()
        if connection: connection.close()
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        if screen: screen.close()
        packet.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
