"""Latest real FOLLOW frame for the local UI; no device or motor access.

The consumer must use this board's monotonic clock to reject stale frames.
Only a single JSON snapshot is retained, atomically replaced after encoding.
"""
import base64
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import time
import uuid

from pose_sender import build_frame


POINT_NAMES = {
    'head': 'head', 'left_shoulder': 'leftShoulder',
    'right_shoulder': 'rightShoulder', 'left_elbow': 'leftElbow',
    'right_elbow': 'rightElbow', 'left_wrist': 'leftWrist',
    'right_wrist': 'rightWrist',
}


def validate_feed_options(camera, display, no_send, feed_file):
    """Validate before acquiring camera, DPU, HDMI or input sender resources."""
    if feed_file is None:
        return
    if camera != 'usb' or display != 'none' or not no_send:
        raise ValueError('--ui-feed-file requires --camera usb --display none --no-send')
    path = PurePosixPath(feed_file)
    if (not path.is_absolute() or '..' in path.parts or len(path.parts) < 3
            or path.parts[1] not in ('tmp', 'run') or path.suffix != '.json'):
        raise ValueError('--ui-feed-file must be a JSON file beneath /tmp or /run')


class UiFrameFeed:
    def __init__(self, path, *, _clock=time.monotonic, _allowed_roots=None):
        target = Path(path)
        # Resolve parent links but never follow an existing destination symlink.
        if target.is_symlink():
            raise ValueError('UI feed destination must not be a symlink')
        self.path = target.parent.resolve() / target.name
        roots = _allowed_roots if _allowed_roots is not None else ('/tmp', '/run')
        if not any(Path(root).resolve() in self.path.parents for root in roots):
            raise ValueError('UI feed must stay inside the volatile runtime directory')
        if self.path.suffix != '.json' or not self.path.parent.is_dir():
            raise ValueError('UI feed needs an existing runtime directory and .json filename')
        self.session_id = uuid.uuid4().hex
        self._clock = _clock
        self._last_sequence = None
        self._last_published = None
        self._closed = False

    def publish(self, frame, pose, sequence, captured_s, track_id):
        if self._closed:
            raise RuntimeError('UI frame feed is closed')
        metadata = build_frame(pose, sequence, captured_s, track_id, self.session_id)
        if self._last_sequence is not None and metadata['seq'] <= self._last_sequence:
            raise ValueError('UI frame sequence must strictly increase')
        now = self._clock()
        if not 0 <= now - metadata['captured_s'] <= .25:
            raise ValueError('Refusing stale or future UI frame')
        import cv2
        import numpy as np
        if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
            raise ValueError('Expected the current upright 1280x720 uint8 BGR frame')
        self._last_sequence = metadata['seq']
        if self._last_published is not None and now - self._last_published < .1:
            return False
        scaled = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        success, encoded = cv2.imencode('.jpg', scaled, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not success or encoded.nbytes > 512 * 1024:
            raise RuntimeError('UI JPEG encoding failed or exceeded size limit')
        payload = {
            'version': 1, 'session_id': self.session_id,
            'sequence': metadata['seq'], 'captured_s': metadata['captured_s'],
            'width': 640, 'height': 360,
            'pose': {POINT_NAMES[key]: [value['x'], value['y']]
                     for key, value in metadata['points'].items() if key in POINT_NAMES},
            'jpeg_base64': base64.b64encode(encoded.tobytes()).decode('ascii'),
        }
        data = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode('utf-8')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', dir=str(self.path.parent),
                                             prefix='.' + self.path.name + '.', delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
            os.replace(str(temporary), str(self.path))
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink()
        self._last_published = self._clock()
        return True

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            current = json.loads(self.path.read_text(encoding='utf-8'))
            if current.get('session_id') == self.session_id:
                self.path.unlink()
        except FileNotFoundError:
            pass
        except (ValueError, UnicodeError):
            # An unknown/replaced file does not belong to this publisher.
            pass
