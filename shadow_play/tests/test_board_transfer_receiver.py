"""Exercise the actual PowerShell-generated receiver without serial hardware."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/board_transfer.ps1'


class ReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = random.Random(42).randbytes(4096)
        payload = base64.b64encode(gzip.compress(cls.data)).decode()
        chunks = [payload[i:i+1024] for i in range(0, len(payload), 1024)]
        cls.lines = [str(i)+':'+hashlib.sha256(s.encode()).hexdigest()+':'+s for i,s in enumerate(chunks)]
        # Only evaluate the two receiver construction assignments, never serial code.
        assignments = '\n'.join(line for line in SCRIPT.read_text().splitlines()
                                if line.startswith(('$receiveLoop =', '$python =')))
        command = "$chunks=%d; $hash='%s'; $Target='result.bin';\n" % (len(chunks), hashlib.sha256(cls.data).hexdigest())
        output = subprocess.check_output(['powershell', '-NoProfile', '-Command',
                                          command+assignments+'\nConvertTo-Json -Compress $python'], text=True)
        cls.receiver = json.loads(output)

    def run_receiver(self, lines):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-c', self.receiver],
                                    input='\n'.join(lines)+'\n', text=True,
                                    capture_output=True, cwd=directory, timeout=5)
            target = Path(directory)/'result.bin'
            data = target.read_bytes() if target.exists() else None
        return result, data

    def test_complete_chunks_acknowledged_and_original_file_verified(self):
        result, data = self.run_receiver(self.lines)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(data, self.data)
        for i in range(len(self.lines)):
            self.assertIn('CHUNK_OK '+str(i)+'\n', result.stdout)
        self.assertIn('TRANSFER_OK ', result.stdout)

    def test_corruption_is_rejected_before_writing_file(self):
        lines = self.lines.copy()
        lines[0] = lines[0][:-2]+'XX'
        result, data = self.run_receiver(lines)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(data)
        self.assertNotIn('CHUNK_OK 0', result.stdout)

    def test_reordered_chunk_is_rejected_before_writing_file(self):
        result, data = self.run_receiver(self.lines[1:]+self.lines[:1])
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(data)
        self.assertNotIn('TRANSFER_OK ', result.stdout)


if __name__ == '__main__':
    unittest.main()
