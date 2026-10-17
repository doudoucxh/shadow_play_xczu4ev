import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('receiver', Path(__file__).parents[1]/'tools/board_file_receiver.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReceiverTest(unittest.TestCase):
    def test_chunked_reads_and_final_hash(self):
        data = bytes(range(256)) * 170
        wire = b''
        for i, off in enumerate(range(0, len(data), m.BLOCK)):
            block = data[off:off+m.BLOCK]
            wire += struct.pack('!II', i, len(block)) + hashlib.sha256(block).digest() + block
        source, replies = io.BytesIO(wire), []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'payload'
            m.receive(lambda n: source.read(min(n, 53)), replies.append, path, len(data), hashlib.sha256(data).hexdigest())
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(replies[:2], [b'ACK 0\n', b'ACK 1\n'])
            with self.assertRaises(FileExistsError):
                m.receive(source.read, replies.append, path, len(data), hashlib.sha256(data).hexdigest())

    def test_corrupt_or_truncated_data_never_publishes(self):
        for wire in [struct.pack('!II', 1, 3), struct.pack('!II', 0, 3)+b'x'*32+b'bad', b'']:
            with self.subTest(wire=wire), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'payload'
                with self.assertRaises((ValueError, EOFError)):
                    m.receive(io.BytesIO(wire).read, lambda data: None, path, 3, hashlib.sha256(b'abc').hexdigest())
                self.assertFalse(path.exists())

    def test_resume_checks_final_digest_of_prefix_and_suffix(self):
        data = b'a'*m.BLOCK+b'suffix'
        suffix = data[m.BLOCK:]
        wire = struct.pack('!II', 1, len(suffix))+hashlib.sha256(suffix).digest()+suffix
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'payload'
            partial = path.with_name('payload.partial')
            partial.write_bytes(data[:m.BLOCK])
            start, prefix = m.resume_info(path, len(data), True)
            self.assertEqual(start, m.BLOCK)
            self.assertEqual(prefix.hexdigest(), hashlib.sha256(data[:m.BLOCK]).hexdigest())
            m.receive(io.BytesIO(wire).read, lambda data: None, path, len(data), hashlib.sha256(data).hexdigest(), True)
            self.assertEqual(path.read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
