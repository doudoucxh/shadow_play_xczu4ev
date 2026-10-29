"""Startup failure diagnosis against existing bundles; no physical serial I/O."""
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.transport import RemoteDevice

ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def connect_with(self, replies, layout='tiger-four-port'):
        class Port:
            def __init__(self, **kwargs):
                self.responses = iter([b'shadowdpupetalinux:~# ', *replies])
                self.writes = []
                self.is_open = False
                self.reads = 0
            def open(self): self.is_open = True
            def close(self): self.is_open = False
            def write(self, data): self.writes.append(data)
            def read_all(self): return b''
            def read(self, count):
                self.reads += 1
                if self.reads > 30:
                    raise AssertionError('Startup error was swallowed instead of diagnosed')
                return next(self.responses, b'')
        self.port = Port()
        name = 'bus_servo_tiger_four.json' if layout == 'tiger-four-port' else 'bus_servo.json'
        profile = Profile.load(ROOT/'config'/name)
        with patch.dict('sys.modules', {'serial': types.SimpleNamespace(Serial=lambda **kw: self.port)}), \
                patch('shadow_play.bus_servo.transport.time.sleep'):
            return RemoteDevice(profile, 'mock-only')

    def assert_startup_only(self):
        self.assertFalse(self.port.is_open)
        self.assertEqual(len(self.port.writes), 3)  # prompt, echo setting, single launch
        self.assertFalse(any(b'"op"' in w for w in self.port.writes))

    def test_missing_dual_bundle_explains_required_deployment(self):
        with self.assertRaisesRegex(RuntimeError, '缺少双总线控制入口') as error:
            self.connect_with([b"-sh: cd: /run/media/mmcblk0p2/piying/bus-servo-dual-console-v1: No such file or directory\r\n"], 'dual')
        self.assertIn('人物ID1～6共接原9口', str(error.exception))
        self.assertIn('老虎ID7～10共接原10口', str(error.exception))
        self.assertIn('BS10', str(error.exception))
        self.assertIn('修改电脑入口不会更新板子', str(error.exception))
        self.assert_startup_only()

    def test_electrical_rejection_across_serial_chunks(self):
        with self.assertRaisesRegex(RuntimeError, '电气兼容性'):
            self.connect_with([b'usage: service.py ...\r\nservice.py: error: Verify bus electrical ',
                               b'compatibility before transmitting even read-only queries\r\n'])
        self.assert_startup_only()

    def test_confirmed_dual_profile_reports_sync_instead_of_retest(self):
        with self.assertRaisesRegex(RuntimeError, '板端配置尚未同步') as error:
            self.connect_with([b'error: Verify bus electrical compatibility before transmitting even read-only queries\n'], 'dual')
        self.assertIn('无需重复', str(error.exception))
        self.assert_startup_only()

    def test_missing_tiger_launcher_is_not_reported_as_dual(self):
        with self.assertRaisesRegex(RuntimeError, '缺少老虎四口'):
            self.connect_with([b'sh: cannot open start_console.sh: No such file\n'])
        self.assert_startup_only()

    def test_reboot_missing_marker_explains_reload(self):
        with self.assertRaisesRegex(RuntimeError, '重新加载'):
            self.connect_with([b'File "/run/media/mmcblk0p2/piying/bus-servo-tiger-four-v1/shadow_play/bus_servo/device.py"\n',
                               b"FileNotFoundError: No such file or directory: '/run/shadow-bus-servo-loaded.json'\n"])
        self.assert_startup_only()

    def test_unrecognized_startup_exit_stops_at_shell_prompt(self):
        with self.assertRaisesRegex(RuntimeError, '已返回登录终端'):
            self.connect_with([b'Unexpected startup failure\r\nshadowdpupetalinux:~# '])
        self.assert_startup_only()

    def test_ready_frame_survives_fragmentation_and_benign_output(self):
        d = self.connect_with([b'Welcome\r\n@@BUS10@@{"rea', b'dy":true,"service":"bus-teach-v1"}\n'])
        self.assertTrue(d.started)
        self.assertEqual(len(self.port.writes), 3)
        d.failed = True
        d.close()

    def test_startup_timeout_does_not_claim_motion_lease(self):
        d = RemoteDevice.__new__(RemoteDevice)
        d.buffer = b''
        with self.assertRaisesRegex(TimeoutError, '服务启动超时') as error:
            d._receive(time.monotonic() - 1, startup=True)
        self.assertNotIn('卸力', str(error.exception))

    def test_runtime_timeout_still_latches_failure_without_retry(self):
        d = self.connect_with([b'@@BUS10@@{"ready":true,"service":"bus-teach-v1"}\n'])
        with patch.object(d, '_receive', side_effect=TimeoutError('lost reply')):
            with self.assertRaises(TimeoutError): d.request('read', {'numbers': [7]})
            with self.assertRaises(RuntimeError): d.request('read', {'numbers': [7]})
        self.assertEqual(len(self.port.writes), 4)
        d.close()
        self.assertFalse(self.port.is_open)


if __name__ == '__main__':
    unittest.main()
