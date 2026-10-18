"""UVC/V4L2 input isolated from PL capture and from blocking camera drivers.

Frames are letterboxed to the existing FOLLOW 1280x720 coordinate system.
The timestamp is host dequeue time, not the sensor's exposure timestamp.
"""
import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import struct
import time

import cv2
import numpy as np

SHAPE = (720, 1280, 3)


def capture_capability(data):
    caps, device_caps = struct.unpack_from('=II', data, 84)
    if caps & 0x80000000:  # V4L2_CAP_DEVICE_CAPS
        caps = device_caps
    return bool(caps & (1 | 0x1000)) and bool(caps & 0x04000000)


def usb_devices():
    """Exclude metadata nodes and non-USB capture devices; never pick index 0 blindly."""
    import fcntl
    found = []
    for entry in sorted(Path('/sys/class/video4linux').glob('video*')):
        if not any(part.startswith('usb') for part in (entry / 'device').resolve().parts):
            continue
        node = '/dev/' + entry.name
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            try:
                data = bytearray(104)
                fcntl.ioctl(fd, 0x80685600, data, True)  # VIDIOC_QUERYCAP
            finally:
                os.close(fd)
            if capture_capability(data):
                found.append(dict(device=node, name=data[16:48].split(b'\0')[0].decode(errors='replace'),
                                  bus=data[48:80].split(b'\0')[0].decode(errors='replace')))
        except OSError as exc:
            raise RuntimeError('Cannot query {}: {}'.format(node, exc)) from exc
    return found


def select_device(requested='auto', devices=None):
    devices = usb_devices() if devices is None else devices
    if requested == 'auto':
        if len(devices) != 1:
            raise RuntimeError('Expected one USB capture device; found {}. Use --usb-device. '
                               'No nodes: check USB host/device tree and UVC driver.'.format(devices))
        return devices[0]['device']
    selected = str(Path(requested).resolve())
    if selected not in [x['device'] for x in devices]:
        raise RuntimeError('Not an enumerated USB video capture node: ' + requested)
    return selected


def normalize_frame(frame, rotation=0, mirror=False):
    if frame is None or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('USB camera must return uint8 BGR frames')
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Rotation must be 0, 90, 180 or 270')
    if rotation:
        frame = np.rot90(frame, -(rotation // 90))
    if mirror:
        frame = frame[:, ::-1]
    height, width = frame.shape[:2]
    if not height or not width:
        raise ValueError('Empty camera image')
    scale = min(1280 / width, 720 / height)
    w, h = max(1, round(width * scale)), max(1, round(height * scale))
    result = np.full(SHAPE, 114, dtype=np.uint8)
    x, y = (1280 - w) // 2, (720 - h) // 2
    result[y:y+h, x:x+w] = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
    return result


def _worker(options, pixels, sequence, timestamp, mutex, stop, info):
    camera = None
    try:
        cv2.setNumThreads(1)
        camera = cv2.VideoCapture(options['device'], cv2.CAP_V4L2)
        if not camera.isOpened():
            raise RuntimeError('V4L2 could not open ' + options['device'])
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*options['fourcc']))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, options['width'])
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, options['height'])
        camera.set(cv2.CAP_PROP_FPS, options['fps'])
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        shared = np.frombuffer(pixels, np.uint8).reshape(SHAPE)
        first = True
        while not stop.is_set():
            ok, raw = camera.read()
            captured = time.monotonic()
            if not ok:
                raise RuntimeError('USB frame read failed/disconnected')
            frame = normalize_frame(raw, options['rotation'], options['mirror'])
            if first:
                code = int(camera.get(cv2.CAP_PROP_FOURCC))
                info.send(('ready', dict(device=options['device'], width=raw.shape[1], height=raw.shape[0],
                          fps=camera.get(cv2.CAP_PROP_FPS), fourcc=''.join(chr((code >> (8*i)) & 255) for i in range(4)),
                          rotation=options['rotation'], mirror=options['mirror'], output_shape=SHAPE,
                          timestamp='host_after_read')))
                first = False
            with mutex:
                np.copyto(shared, frame)
                timestamp.value = captured
                sequence.value += 1
    except BaseException as exc:
        info.send(('error', '{}: {}'.format(type(exc).__name__, exc)))
    finally:
        if camera is not None:
            camera.release()
        info.close()


class LatestUsbCamera:
    """One shared latest frame; a hung OpenCV read can be terminated on shutdown."""
    def __init__(self, device='auto', width=1280, height=720, fps=30, fourcc='MJPG',
                 rotation=0, mirror=False, timeout=3.0, max_age=.25):
        if not (16 <= width <= 4096 and 16 <= height <= 2160 and 1 <= fps <= 120):
            raise ValueError('Invalid USB capture dimensions/fps')
        if fourcc not in ('MJPG', 'YUYV') or rotation not in (0, 90, 180, 270):
            raise ValueError('Unsupported USB format/rotation')
        options = dict(device=select_device(device), width=width, height=height, fps=fps,
                       fourcc=fourcc, rotation=rotation, mirror=mirror)
        self.timeout, self.max_age = timeout, max_age
        self.published = self.dropped = self.rejected = self.last_sequence = 0
        self.metadata = None
        self.closed = False
        ctx = mp.get_context('spawn')
        self.pixels = ctx.RawArray('B', int(np.prod(SHAPE)))
        self.sequence, self.timestamp = ctx.RawValue('Q', 0), ctx.RawValue('d', 0.)
        self.mutex, self.stop = ctx.Lock(), ctx.Event()
        self.info, child_info = ctx.Pipe(duplex=False)
        self.process = ctx.Process(target=_worker,
                                  args=(options, self.pixels, self.sequence, self.timestamp,
                                        self.mutex, self.stop, child_info), daemon=True)
        self.process.start()
        child_info.close()

    def _check(self):
        while self.info.poll():
            try:
                kind, value = self.info.recv()
            except EOFError:
                raise RuntimeError('USB capture process exited')
            if kind == 'error':
                raise RuntimeError(value)
            self.metadata = value
        if not self.process.is_alive():
            raise RuntimeError('USB capture process exited: {}'.format(self.process.exitcode))

    def read(self, timeout=None):
        if self.closed:
            raise RuntimeError('USB camera is closed')
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            self._check()
            if self.mutex.acquire(timeout=.05):
                try:
                    sequence, captured = self.sequence.value, self.timestamp.value
                    if sequence > self.last_sequence:
                        frame = np.frombuffer(self.pixels, np.uint8).reshape(SHAPE).copy()
                    else:
                        frame = None
                finally:
                    self.mutex.release()
                if frame is not None:
                    if time.monotonic() - captured > self.max_age:
                        self.rejected += 1
                        raise RuntimeError('Refusing stale USB frame')
                    self.dropped += max(0, sequence - self.last_sequence - 1)
                    self.published = self.last_sequence = sequence
                    self._check()
                    return frame, sequence, captured
            time.sleep(.002)
        raise RuntimeError('No fresh USB frame within {} seconds'.format(self.timeout))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop.set()
        self.process.join(.5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(1)
        self.info.close()
        if self.process.is_alive():
            raise RuntimeError('USB capture process failed to stop')


def add_usb_arguments(parser):
    parser.add_argument('--usb-device', default='auto')
    parser.add_argument('--usb-width', type=int, default=1280)
    parser.add_argument('--usb-height', type=int, default=720)
    parser.add_argument('--usb-fps', type=int, default=30)
    parser.add_argument('--usb-format', choices=('MJPG', 'YUYV'), default='MJPG')
    parser.add_argument('--usb-rotation', type=int, choices=(0, 90, 180, 270), default=0)
    parser.add_argument('--usb-mirror', action='store_true')


def open_usb(args):
    return LatestUsbCamera(args.usb_device, args.usb_width, args.usb_height, args.usb_fps,
                           args.usb_format, args.usb_rotation, args.usb_mirror)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--frames', type=int, default=60)
    add_usb_arguments(parser)
    args = parser.parse_args()
    if args.list:
        devices = usb_devices()
        print(json.dumps(devices, indent=2))
        return 0 if devices else 2
    if not 1 <= args.frames <= 100000:
        parser.error('--frames must be 1..100000')
    camera = open_usb(args)
    start = time.monotonic()
    try:
        for _ in range(args.frames):
            frame, sequence, captured = camera.read()
        print(json.dumps(dict(result='USB_CAPTURE_PASS', frames=args.frames, metadata=camera.metadata,
                              seconds=time.monotonic()-start, last_sequence=sequence,
                              mean_pixel=float(frame.mean()), age_ms=(time.monotonic()-captured)*1000)))
    finally:
        camera.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
