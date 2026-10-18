import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]/'hdmi_ui/runtime'))
from browser_display import Bidi, HEADER, PIXEL_BYTES, PacketReader, publish, read_packet, viewport_point, decode_frame


class DisplayTests(unittest.TestCase):
    def test_repeat_poll_reads_only_header_but_still_expires(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'frame.bin'
            pixels = b'BGRA'+bytes([12,34,56,255])*(PIXEL_BYTES//4)
            publish(path, pixels, 100)
            reader = PacketReader(path)
            self.assertEqual(reader.read(100.5), (100, pixels))
            original_open = Path.open
            reads = []
            class Measured:
                def __init__(self, handle): self.handle = handle
                def __enter__(self): return self
                def __exit__(self, *args): self.handle.close()
                def fileno(self): return self.handle.fileno()
                def read(self, size):
                    data = self.handle.read(size)
                    reads.append(len(data))
                    return data
            def measured_open(path, *args, **kwargs):
                return Measured(original_open(path, *args, **kwargs))
            with mock.patch.object(Path, 'open', measured_open):
                for _ in range(20):
                    self.assertEqual(reader.read(100.6), (100, None))
            self.assertEqual(reads, [HEADER.size]*20)
            with self.assertRaises(ValueError): reader.read(102.1)
            self.assertIsNone(reader.identity)

    def test_atomic_replacement_revalidates_same_timestamp_and_size(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'frame.bin'
            first, second = b'\xff\xd8AAAA\xff\xd9', b'\xff\xd8BBBB\xff\xd9'
            reader = PacketReader(path)
            publish(path, first, 100)
            self.assertEqual(reader.read(100.1)[1], first)
            publish(path, second, 100)
            self.assertEqual(reader.read(100.2)[1], second)
            path.write_bytes(HEADER.pack(100, len(second))+b'not jpeg')
            with self.assertRaises(ValueError): reader.read(100.3)
            publish(path, second, 101)
            self.assertEqual(reader.read(101.1)[1], second)
            path.write_bytes(HEADER.pack(101, 1)+b'xx')
            with self.assertRaises(ValueError): reader.read(101.2)

    def test_default_clock_is_sampled_after_packet_open(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'frame.bin'
            jpeg = b'\xff\xd8fixture\xff\xd9'
            publish(path, jpeg, 100)
            with mock.patch('browser_display.time.monotonic', return_value=100.1):
                self.assertEqual(read_packet(path), (100, jpeg))
                self.assertEqual(PacketReader(path).read(), (100, jpeg))
            with mock.patch('browser_display.time.monotonic', return_value=99):
                with self.assertRaises(ValueError): PacketReader(path).read()

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
