import gzip
import hashlib
import importlib.util
from pathlib import Path
import stat
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ui_boot', ROOT/'tools/install_ui_autostart.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


def unpack(data):
    entries = {}
    offset = 0
    while data[offset:offset+6] == b'070701':
        fields = [int(data[offset+6+i*8:offset+14+i*8], 16) for i in range(13)]
        name = data[offset+110:offset+110+fields[11]-1].decode()
        offset = (offset+110+fields[11]+3)//4*4
        payload = data[offset:offset+fields[6]]
        offset = (offset+fields[6]+3)//4*4
        if name == 'TRAILER!!!':
            return entries
        entries[name] = (fields[1], payload)
    raise ValueError('Missing archive trailer')


class StartupTests(unittest.TestCase):
    def test_overlay_has_boot_unit_and_disables_conflicting_services(self):
        entries = unpack(gzip.decompress(boot.overlay(ROOT/'boot_ui')))
        for name in ('shadow-video', 'shadow-yolo-follow', 'shadow-yolo-pose', 'shadow-arm-chain', 'shadow-hw-init'):
            mode, target = entries['etc/systemd/system/'+name+'.service']
            self.assertTrue(stat.S_ISLNK(mode))
            self.assertEqual(target, b'/dev/null')
        self.assertEqual(entries['etc/systemd/system/multi-user.target.wants/shadow-theatre-boot.service'][1],
                         b'../shadow-theatre-boot.service')
        code = entries['usr/local/lib/shadow-theatre-bootstrap.py'][1]
        compile(code, 'bootstrap', 'exec')
        sha = hashlib.sha256((ROOT/'boot_ui/launch.py').read_bytes()).hexdigest()
        self.assertIn(sha.encode(), code)

    def test_environment_only_changes_the_fit_filename(self):
        original = b'# preserve usb\npiying_load= fatload mmc 0:1 0x10000000 image.ub && bootm start 0x10000000\nuenvcmd=run piying_usb_boot; run piying_sd_boot\n'
        updated = boot.new_environment(original)
        self.assertEqual(updated.replace(boot.NAME.encode(), b'image.ub'), original)
        for bad in (b'', original+original):
            with self.assertRaises(ValueError):
                boot.new_environment(bad)

    def test_cpio_roundtrip_and_rejects_escape(self):
        entries = [('directory', stat.S_IFDIR | 0o755, b''),
                   ('directory/script.py', stat.S_IFREG | 0o644, b'abcdefg')]
        self.assertEqual(unpack(boot.cpio(entries)), {n: (m, p) for n, m, p in entries})
        for name in ('/absolute', '../escape', 'x/../escape', 'x\\y'):
            with self.assertRaises(ValueError):
                boot.cpio([(name, stat.S_IFREG | 0o644, b'')])

    def test_overlay_is_repeatable(self):
        self.assertEqual(boot.overlay(ROOT/'boot_ui'), boot.overlay(ROOT/'boot_ui'))


if __name__ == '__main__':
    unittest.main()
