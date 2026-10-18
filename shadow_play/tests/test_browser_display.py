import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]/'hdmi_ui/runtime'))
from browser_display import Bidi, HEADER, PIXEL_BYTES, publish, read_packet, viewport_point, decode_frame


class DisplayTests(unittest.TestCase):
    def test_local_pixels_color_and_strict_size_and_freshness(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'frame.bin'
            pixels=b'BGRA'+bytes([12,34,56,255])*(PIXEL_BYTES//4)
            publish(path,pixels,100)
            frame=decode_frame(read_packet(path,100.5)[1])
            self.assertEqual(frame.shape,(600,1024,3))
            self.assertEqual(frame[20,30].tolist(),[12,34,56])
            for bad in (pixels[:-1],pixels+b'x',b'BGRA'):
                with self.assertRaises(ValueError):publish(path,bad,100)
            with self.assertRaises(ValueError):read_packet(path,103)

    def test_letterbox_input(self):
        self.assertIsNone(viewport_point(0, .5))
        self.assertIsNone(viewport_point(1, .5))
        self.assertEqual(viewport_point(.5, .5), [512, 300])
        self.assertIsNone(viewport_point(float('nan'), .5))

    def test_expired_or_malformed_frame_not_displayed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'frame.bin'
            jpeg = b'\xff\xd8fixture\xff\xd9'
            publish(path, jpeg, 100)
            self.assertEqual(read_packet(path, 100.5), (100, jpeg))
            for now in (99, 102.1, float('nan')):
                with self.assertRaises(ValueError): read_packet(path, now)
            path.write_bytes(HEADER.pack(100, 20)+jpeg)
            with self.assertRaises(ValueError): read_packet(path, 100.1)

    def test_bidi_events_and_errors(self):
        class Connection:
            def send(self, data): self.sent = json.loads(data)
            def recv(self): return self.rows.pop(0)
        connection = Connection()
        connection.rows = [json.dumps(dict(type='event')), json.dumps(dict(id=1, type='success', result=dict(context='test')))]
        bidi = Bidi(connection)
        self.assertEqual(bidi.call('browsingContext.create', {'type':'tab'}), dict(context='test'))
        connection.rows = [json.dumps(dict(id=2, type='error', message='unsupported'))]
        with self.assertRaises(RuntimeError): bidi.call('bad', {})


if __name__ == '__main__': unittest.main()
