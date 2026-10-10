"""Boot delta integrity tests; no device or firmware access."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from usb_boot_candidate import make_candidate, partitions, sha


def image(fsbl, shift=0):
    data = bytearray(2048 + shift)
    data[0x20:0x28] = bytes.fromhex('665599aa584e4c58')
    struct.pack_into('<I', data, 0x38, 16)
    struct.pack_into('<I', data, 0x9C, 256)
    struct.pack_into('<I', data, 0x48,
                     (0xFFFFFFFF-sum(struct.unpack_from('<10I', data, 0x20))) & 0xFFFFFFFF)
    for i in range(5):
        offset = 1024 + shift + 128*i
        payload = b'P'*16 + bytes([fsbl])*112 if i == 0 else bytes([i])*128
        data[offset:offset+128] = payload
        words = [32, 32, 32, (256+(i+1)*64)//4 if i<4 else 0,
                 0, 0, 4096*i, 0, offset//4, 0x116, 0, 0, 0, 0, 0]
        words.append((0xFFFFFFFF-sum(words)) & 0xFFFFFFFF)
        struct.pack_into('<16I', data, 256+i*64, *words)
    return bytes(data)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.source = image(2)
        full = image(3, 64)
        self.full = full
        template = bytearray(full)
        for p in partitions(full)[1:]:
            template[p['offset']:p['offset']+p['length']] = bytes(p['length'])
        self.template = bytes(template)
        self.manifest = dict(source_sha256=sha(self.source), template_sha256=sha(self.template),
                             format='zynqmp-fsbl-delta-v1',
                             source_partition_sha256=[p['sha256'] for p in partitions(self.source)],
                             new_fsbl_pmu_sha256=partitions(full)[0]['sha256'])

    def test_relocation_preserves_original_partitions_and_pmu(self):
        self.assertEqual(make_candidate(self.source, self.template, self.manifest), self.full)

    def test_changed_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Source'):
            make_candidate(self.source[:-1]+b'X', self.template, self.manifest)

    def test_changed_template_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'template hash'):
            make_candidate(self.source, self.template[:-1]+b'X', self.manifest)

    def test_different_pmu_refused_even_with_template_manifest_updated(self):
        template = bytearray(self.template)
        template[partitions(template)[0]['offset']] ^= 1
        m = copy.deepcopy(self.manifest); m['template_sha256'] = sha(template)
        with self.assertRaisesRegex(ValueError, 'PMU firmware changed'):
            make_candidate(self.source, bytes(template), m)

    def test_invalid_header_checksum_refused(self):
        bad = bytearray(self.source); bad[256] ^= 1
        with self.assertRaisesRegex(ValueError, 'partition header checksum'):
            partitions(bad)

    def test_unexpected_preserved_slot_content_refused(self):
        template = bytearray(self.template)
        template[partitions(template)[1]['offset']] = 99
        m = copy.deepcopy(self.manifest); m['template_sha256'] = sha(template)
        with self.assertRaisesRegex(ValueError, 'empty preserved-partition'):
            make_candidate(self.source, bytes(template), m)

    def test_original_firmware_is_refused_before_overlay(self):
        import enable_p4_usb_host as usb
        from unittest.mock import patch
        with patch.object(usb.platform, 'release', return_value='5.15.36-xilinx-v2022.2'), \
                patch.object(usb, 'query', return_value='Reset status: 1'):
            with self.assertRaisesRegex(RuntimeError, 'still in reset'):
                usb.check_fsbl()

    def test_gpio_instead_of_ulpi_is_refused(self):
        import enable_p4_usb_host as usb
        from unittest.mock import patch
        def query(command):
            return 'Reset status: 0' if 'reset' in command else 'Current set function for the pin: 7'
        with patch.object(usb.platform, 'release', return_value='5.15.36-xilinx-v2022.2'), \
                patch.object(usb, 'query', side_effect=query):
            with self.assertRaisesRegex(RuntimeError, 'ULPI pins'):
                usb.check_fsbl()

    def test_idle_core_reset_allowed_before_wrapper_but_not_after(self):
        import enable_p4_usb_host as usb
        from unittest.mock import patch
        def query(command):
            if 'reset' in command:
                return 'Reset status: 1' if command.endswith('1059') else 'Reset status: 0'
            return 'Current set function for the pin: '+('7' if command.endswith(' 24') else '43')
        with patch.object(usb.platform, 'release', return_value='5.15.36-xilinx-v2022.2'), \
                patch.object(usb, 'query', side_effect=query):
            usb.check_fsbl()
            with self.assertRaisesRegex(RuntimeError, 'still in reset'):
                usb.check_fsbl(wrapper_ready=True)

    def test_wrong_non_gpio_pin_function_is_refused(self):
        import enable_p4_usb_host as usb
        from unittest.mock import patch
        def query(command):
            if 'reset' in command: return 'Reset status: 0'
            return 'Current set function for the pin: '+('7' if command.endswith(' 24') else '42')
        with patch.object(usb.platform, 'release', return_value='5.15.36-xilinx-v2022.2'), \
                patch.object(usb, 'query', side_effect=query):
            with self.assertRaisesRegex(RuntimeError, 'ULPI pins'):
                usb.check_fsbl()


if __name__ == '__main__':
    unittest.main()
