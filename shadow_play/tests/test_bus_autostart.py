import gzip
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from shadow_play.boot_bus import launch
from shadow_play.tools import install_bus_autostart as boot
from shadow_play.tests.test_ui_autostart import unpack

SOURCE = Path(__file__).resolve().parents[1]/'boot_bus'


class BusStartupTests(unittest.TestCase):
    def test_default_validates_files_without_hardware(self):
        with patch('sys.argv', ['launch.py']), patch.object(launch, 'verify_installation'), \
             patch.object(launch.os, 'open', side_effect=AssertionError('hardware')), \
             patch.object(launch.subprocess, 'run', side_effect=AssertionError('execution')):
            launch.main()

    def test_rejects_any_prior_load_or_consumed_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launch.cold_guard(root, 30)
            for name in launch.MARKERS:
                marker = root/name
                marker.touch()
                with self.assertRaises(RuntimeError):
                    launch.cold_guard(root, 30)
                marker.unlink()
            for uptime in (-1, 240, 1000):
                with self.assertRaises(RuntimeError):
                    launch.cold_guard(root, uptime)

    def test_reset_only_reads_identity_and_fixed_state_no_fifo(self):
        expected = {0: 0x42533130, 4: 1, 8: 0, 16: 0, 0x18: 100000000,
                    0x1c: 115200, 0x100: 0, 0x200: 0}
        seen = []
        def read(offset):
            seen.append(offset)
            return expected[offset]
        launch.reset_state(read)
        self.assertEqual(set(seen), set(expected))
        for offset in expected:
            changed = dict(expected)
            changed[offset] ^= 1
            with self.assertRaises(RuntimeError):
                launch.reset_state(changed.__getitem__)

    def test_checks_content_and_rejects_manifest_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'code.py').write_bytes(b'pass\n')
            sha = hashlib.sha256(b'pass\n').hexdigest()
            launch.verify_files(root, {'code.py': sha})
            for files in ({'code.py': '0'*64}, {'../escape': sha}):
                with self.assertRaises(RuntimeError):
                    launch.verify_files(root, files)

    def test_boot_overlay_integrity_and_no_restart(self):
        first = boot.overlay(SOURCE)
        self.assertEqual(first, boot.overlay(SOURCE))
        entries = unpack(gzip.decompress(first))
        code = entries['usr/local/lib/shadow-theatre-bootstrap.py'][1]
        compile(code, 'bootstrap', 'exec')
        self.assertIn(boot.digest(SOURCE/'launch.py').encode(), code)
        self.assertIn(b'--execute-cold-boot', code)
        self.assertNotIn(b'power-off-confirmed', code)
        service = entries['etc/systemd/system/shadow-theatre-boot.service'][1]
        self.assertIn(b'Restart=no', service)
        for name in launch.LEGACY:
            self.assertEqual(entries['etc/systemd/system/'+name+'.service'][1], b'/dev/null')

    def test_only_active_fit_filename_changes(self):
        original = b'# usb unchanged\npiying_load= fatload mmc 0:1 0x10000000 image-ui-20261018.ub && bootm start 0x10000000\nuenvcmd=run piying_usb_boot; run piying_sd_boot\n'
        result = boot.new_environment(original)
        self.assertEqual(result.replace(boot.NAME.encode(), b'image-ui-20261018.ub'), original)
        for bad in (b'', original+original, original.replace(b'image-ui-20261018.ub', b'image.ub')):
            with self.assertRaises(ValueError):
                boot.new_environment(bad)

    def test_archive_does_not_remove_on_bad_copy_or_active_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bootpart = root/'boot'
            work = root/'work'
            bootpart.mkdir()
            work.mkdir()
            old = bootpart/boot.OLD_BACKUP
            old.write_bytes(b'old')
            env = bootpart/'uEnv.txt'
            env.write_bytes(boot.OLD_BACKUP.encode())
            with patch.object(boot, 'BOOT', bootpart), patch.object(boot, 'WORK', work), \
                 patch.object(boot, 'OLD_BACKUP_SHA', boot.digest(old)):
                with self.assertRaises(RuntimeError):
                    boot.archive_inactive_backup()
                env.write_bytes(b'other')
                with patch.object(boot, 'copy_new', side_effect=RuntimeError('copy failed')):
                    with self.assertRaises(RuntimeError):
                        boot.archive_inactive_backup()
            self.assertEqual(old.read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
