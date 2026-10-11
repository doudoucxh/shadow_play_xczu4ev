import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import recovery_center_once as recovery
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.locks = (root/'runtime-stop', root/'persistent-stop')
        for path in self.locks:
            path.write_text('incident; no ordinary motion', encoding='utf-8')
        self.cancel = root/'cancel'
        self.reg = FakeRegisters()
        self.reg.values[0x20] = 296
        self.reg.values[0x80] = 1537
        self.plan = dict(approval=recovery.APPROVAL, channel=1, expected_sequence=296,
                         expected_pulses_us=[1537]+[1500]*9, linkage_disconnected=True,
                         remaining_bracket_and_rod_clear=True, observer_ready=True)
        self.now = 0.0
        self.events = []

    def device(self):
        return recovery.RecoveryCenterDevice(self.reg, self.plan,
            motion_inhibit_paths=self.locks, cancel_path=self.cancel, clock=lambda:self.now)

    def advance(self, seconds):
        self.now += seconds

    def run_once(self, device, sleep=None):
        recovery.run_once(device, self.events.append, clock=lambda:self.now,
                          sleep=sleep or self.advance)

    def test_one_fixed_center_and_final_off_preserve_both_locks(self):
        before = [p.read_bytes() for p in self.locks]
        device = self.device()
        self.assertEqual(self.reg.writes, [])
        self.run_once(device)
        self.assertEqual(sum(address==0x18 for address,_ in self.reg.writes),2)
        self.assertEqual(self.events[-1]['state']['sequence'],298)
        self.assertTrue(self.events[-1]['normal_frame_stop'])
        self.assertEqual(self.events[0]['state']['enabled_mask'],1)
        self.assertEqual(self.events[0]['state']['pulse_us'],[1500]*10)
        self.assertEqual(self.events[-1]['state']['enabled_mask'],0)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertAlmostEqual(self.now,3.0)
        self.assertEqual([p.read_bytes() for p in self.locks],before)
        ordinary = PwmDevice(self.reg, motion_inhibit_paths=self.locks)
        with self.assertRaisesRegex(RuntimeError,'inhibited'):
            ordinary.commit([1500]*10,1,allow_arm=True)

    def test_alternate_angle_multiple_channels_or_second_commit_rejected(self):
        device = self.device()
        for pulses,mask in (([1600]+[1500]*9,1),([1500]*10,3),([1500]*10,2)):
            with self.assertRaises(RuntimeError): device.commit(pulses,mask,allow_arm=True)
        self.assertEqual(self.reg.writes,[])
        self.run_once(device)
        before = len(self.reg.writes)
        with self.assertRaises(RuntimeError): device.commit([1500]*10,1,allow_arm=True)
        self.assertEqual(len(self.reg.writes),before)

    def test_stale_registers_or_sequence_cannot_arm(self):
        for address,value in ((0x20,297),(0x80,1540),(0x10,1),(0x0c,1),(0x24,1),(8,2)):
            old = self.reg.read(address)
            self.reg.values[address] = value
            with self.assertRaisesRegex(RuntimeError,'OFF state changed'):
                self.device().commit([1500]*10,1,allow_arm=True)
            self.assertEqual(self.reg.writes,[])
            self.reg.values[address] = old

    def test_missing_confirmation_cannot_construct(self):
        for key in ('linkage_disconnected','remaining_bracket_and_rod_clear','observer_ready'):
            for value in (False,1,None):
                plan = copy.deepcopy(self.plan);plan[key]=value
                with self.assertRaises(ValueError): recovery.validate_plan(plan)
        for key,value in (('approval','continue'),('channel',True),('expected_sequence',-1)):
            plan = copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError): recovery.validate_plan(plan)
        self.assertEqual(self.reg.writes,[])

    def test_missing_lock_prevents_recovery(self):
        self.locks[1].unlink()
        with self.assertRaises(FileNotFoundError): self.device()
        self.assertEqual(self.reg.writes,[])

    def test_cancel_or_changed_lock_prevents_commit(self):
        device = self.device()
        self.cancel.write_text('stop')
        with self.assertRaises(RuntimeError): device.commit([1500]*10,1,allow_arm=True)
        self.cancel.unlink()
        self.locks[0].write_text('new stop')
        with self.assertRaises(RuntimeError): device.commit([1500]*10,1,allow_arm=True)
        self.assertEqual(self.reg.writes,[])

    def test_expired_permission_cannot_arm(self):
        device = self.device();self.now=15
        with self.assertRaises(RuntimeError): device.commit([1500]*10,1,allow_arm=True)
        self.assertEqual(self.reg.writes,[])

    def test_cancel_during_hold_stops_without_retry(self):
        def cancel(seconds):
            self.advance(seconds);self.cancel.write_text('stop')
        with self.assertRaises(RuntimeError): self.run_once(self.device(),cancel)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertEqual(sum(address==0x18 for address,_ in self.reg.writes),1)

    def test_keyboard_interrupt_stops_output(self):
        def interrupt(seconds): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.run_once(self.device(),interrupt)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_failed_commit_never_retries_and_stops(self):
        self.reg.apply=False
        device=self.device()
        with self.assertRaises(TimeoutError): self.run_once(device)
        self.assertTrue(device.used)
        self.assertEqual(sum(address==0x18 for address,_ in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_dry_run_does_not_open_registers(self):
        plan_path=Path(self.temp.name)/'plan.json'
        plan_path.write_text(json.dumps(self.plan),encoding='utf-8')
        with patch.object(sys,'argv',['recovery',str(plan_path)]), \
                patch.object(recovery,'Registers') as registers:
            recovery.main();registers.assert_not_called()

    def test_free_single_connection_requires_separate_scope_and_evidence(self):
        self.plan.update(approval=recovery.FREE_APPROVAL, channel=5,
                         linkage_disconnected=False, free_single_connection=True,
                         puppet_other_rods_disconnected=True)
        recovery.validate_plan(self.plan)
        d=self.device();self.run_once(d)
        self.assertEqual(self.events[0]['state']['enabled_mask'],16)
        self.assertFalse(self.events[-1]['state']['armed'])
        for key,value in [('channel',7),('approval',recovery.APPROVAL),
                          ('free_single_connection',False),('puppet_other_rods_disconnected',False),
                          ('linkage_disconnected',True)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):recovery.validate_plan(plan)


if __name__=='__main__': unittest.main()
