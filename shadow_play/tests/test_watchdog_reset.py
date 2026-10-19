import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/calibration'))
sys.path.insert(0, str(ROOT/'tests'))
from test_servo_commissioning import FakeRegisters
from servo_pwm_device import PwmDevice
from watchdog_reset import reset_disabled_watchdog
from v20_first_direction import IMAGE


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name); self.lock = self.path/'lock'; self.lock.write_text('locked')
        self.reg = FakeRegisters(); self.reg.values.update({0xc: 2, 0x20: 10395})
        self.device = PwmDevice(self.reg, motion_inhibit_paths=[self.lock])
        self.args = dict(expected_state=self.device.status(), boot_id='current',
                         marker=dict(boot_id='current', sha256=IMAGE), onsite_inspected=True,
                         used_path=self.path/'used')

    def reset(self):
        return reset_disabled_watchdog(self.device, **self.args)

    def test_only_off_arm_off_and_no_mask_or_pulse_or_commit_writes(self):
        result = self.reset()
        self.assertEqual(self.reg.writes, [(0xc, 0), (0x10, 0x41524d31), (0xc, 0)])
        self.assertEqual(result['after'], dict(self.args['expected_state'], faults=0))
        self.assertEqual(result['during']['enabled_mask'], 0)
        self.assertEqual(self.lock.read_text(), 'locked')

    def test_changed_or_active_pending_and_other_faults_reject_without_writes(self):
        for address, value in [(8,1),(0x10,1),(0x24,1),(0xc,0),(0xc,1),(0xc,6),(0x20,10396),(0x80,1501)]:
            with self.subTest(address=address,value=value):
                original = copy.deepcopy(self.reg.values); self.reg.values[address] = value
                with self.assertRaises(RuntimeError):self.reset()
                self.assertEqual(self.reg.writes, []); self.reg.values = original

    def test_missing_inspection_or_changed_image_reject(self):
        for key,value in [('onsite_inspected',False),('boot_id','other'),('marker',dict(boot_id='current',sha256='bad'))]:
            args=dict(self.args); args[key]=value
            with self.assertRaises(ValueError):reset_disabled_watchdog(self.device,**args)
        self.assertEqual(self.reg.writes,[])

    def test_one_use_and_missing_lock_reject_without_writes(self):
        self.args['used_path'].write_text('used')
        with self.assertRaises(FileExistsError):self.reset()
        self.lock.unlink()
        with self.assertRaises(FileNotFoundError):self.reset()
        self.assertEqual(self.reg.writes,[])

    def test_failed_arm_still_forces_off_and_never_retries(self):
        original=self.reg.write
        def fail(address,value):
            original(address,value)
            if address==0x10:raise OSError('uncertain ARM acknowledgement')
        self.reg.write=fail
        with self.assertRaises(OSError):self.reset()
        self.assertFalse(self.device.status()['armed'])
        self.assertEqual(self.reg.writes,[(0xc,0),(0x10,0x41524d31),(0xc,0)])


if __name__=='__main__':unittest.main()
