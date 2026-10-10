"""Native MMIO primitive tests against RAM, without opening /dev/mem."""
import mmap
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from mmio32 import WordAccess


class WordAccessTests(unittest.TestCase):
    def setUp(self):
        self.memory = mmap.mmap(-1, 4096)
        self.memory[:] = b'\xa5' * 4096
        self.access = WordAccess(self.memory)

    def tearDown(self):
        self.access.close()
        self.memory.close()

    def test_values_and_adjacent_words(self):
        for value in (0, 1500, 0x41524d31, 0x434f4d54, 0xffffffff):
            self.access.write(12, value)
            self.assertEqual(self.access.read(12), value)
            self.assertEqual(self.memory[:12], b'\xa5' * 12)
            self.assertEqual(self.memory[16:], b'\xa5' * (4096-16))

    def test_reject_invalid_address_without_access(self):
        for offset in (-4, 1, 4096, True, 4.0):
            with self.assertRaises(ValueError): self.access.write(offset, 0)
            with self.assertRaises(ValueError): self.access.read(offset)
        self.assertEqual(self.memory[:], b'\xa5' * 4096)

    def test_reject_invalid_value_without_access(self):
        for value in (-1, 2**32, True, 1500.0):
            with self.assertRaises(ValueError): self.access.write(12, value)
        self.assertEqual(self.memory[:], b'\xa5' * 4096)

    def test_closed_access(self):
        self.access.close()
        with self.assertRaises(RuntimeError): self.access.write(12, 0)
        with self.assertRaises(RuntimeError): self.access.read(12)


if __name__ == '__main__': unittest.main()
