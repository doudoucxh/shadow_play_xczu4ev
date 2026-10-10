"""Validate boot installation refusals and rollback preservation on plain files."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import install_usb_boot_overlay as usb


class BootOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.boot = Path(self.temp.name)
        self.source = {'BOOT.BIN': b'reviewed-usb-fsbl', 'image.ub': b'original-system',
                       'uEnv.txt': b'original-sd-fix'}
        for name, data in self.source.items(): (self.boot/name).write_bytes(data)
        self.env = (ROOT/'hardware/usb/uEnv.usb.txt').read_bytes()
        self.overlay = (ROOT/'hardware/usb/release/boot.dtbo').read_bytes()
        for key, name in [('BOOT_SHA','BOOT.BIN'),('IMAGE_SHA','image.ub'),('OLD_ENV_SHA','uEnv.txt')]:
            mock = patch.object(usb, key, usb.sha(self.source[name]))
            mock.start()
            self.addCleanup(mock.stop)

    def install(self, apply=True):
        return usb.install(self.boot, self.overlay, self.env, apply)

    def test_preflight_does_not_write(self):
        self.assertEqual(self.install(False), 'PREFLIGHT_OK')
        self.assertEqual({p.name:p.read_bytes() for p in self.boot.iterdir()}, self.source)

    def test_uenv_entry_is_short_for_vendor_unquoted_test(self):
        fields = dict(line.split('=', 1) for line in self.env.decode().splitlines()
                      if line and not line.startswith('#'))
        self.assertEqual(fields['uenvcmd'], 'run piying_usb_boot; run piying_sd_boot')
        self.assertLess(len(fields['uenvcmd'].split()), 8)
        self.assertIn('fdt apply 0x0f000000', fields['piying_usb_boot'])
        self.assertIn('fdt set /axi/mmc@ff170000 disable-wp', fields['piying_sd_boot'])

    def test_backup_preserved_and_repeat_is_idempotent(self):
        self.assertEqual(self.install(), 'INSTALLED_REBOOT_REQUIRED')
        self.assertEqual((self.boot/'uEnv-before-usb-20261010.txt').read_bytes(), self.source['uEnv.txt'])
        for name in ('BOOT.BIN','image.ub'):
            self.assertEqual((self.boot/name).read_bytes(), self.source[name])
        self.assertEqual(self.install(), 'ALREADY_INSTALLED')

    def test_changed_active_files_refused_without_writes(self):
        for name in self.source:
            (self.boot/name).write_bytes(b'changed')
            before = {p.name:p.read_bytes() for p in self.boot.iterdir()}
            with self.assertRaises(ValueError): self.install()
            self.assertEqual({p.name:p.read_bytes() for p in self.boot.iterdir()}, before)
            (self.boot/name).write_bytes(self.source[name])

    def test_changed_payload_refused(self):
        with self.assertRaisesRegex(ValueError,'overlay'):
            usb.install(self.boot, self.overlay+b'changed', self.env, True)
        with self.assertRaisesRegex(ValueError,'environment'):
            usb.install(self.boot, self.overlay, self.env+b'changed', True)

    def test_conflicting_backup_is_never_overwritten(self):
        (self.boot/'uEnv-before-usb-20261010.txt').write_bytes(b'other-backup')
        with self.assertRaisesRegex(ValueError, 'Existing file differs'): self.install()
        self.assertEqual((self.boot/'uEnv.txt').read_bytes(), self.source['uEnv.txt'])

    def test_incomplete_installed_state_is_rejected(self):
        self.install()
        (self.boot/usb.OVERLAY_NAME).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'incomplete'): self.install()


if __name__ == '__main__': unittest.main()
