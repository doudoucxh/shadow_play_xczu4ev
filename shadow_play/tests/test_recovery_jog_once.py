import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import recovery_jog_once as recovery
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters


class JogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.locks = (root/'runtime', root/'persistent')
        for p in self.locks:
            p.write_text('incident')
        self.cancel = root/'cancel'
        self.reg = FakeRegisters()
        self.plan = dict(approval=recovery.APPROVAL, channel=2, expected_sequence=0,
                         expected_pulses_us=[1500]*10, target_us=1352,
                         linkage_disconnected=True, sweep_clear=True, observer_ready=True,
                         start_pose_reviewed=True)
        self.now = 0.
        self.events = []

    def device(self):
        return recovery.RecoveryJogDevice(self.reg, self.plan, motion_inhibit_paths=self.locks,
                                         cancel_path=self.cancel, clock=lambda:self.now)

    def advance(self, seconds):
        self.now += seconds

    def run_jog(self, device, sleep=None):
        recovery.run_once(device, self.events.append, clock=lambda:self.now,
                          sleep=sleep or self.advance)

    def test_finite_steps_rate_single_channel_and_final_off(self):
        before = [p.read_bytes() for p in self.locks]
        self.run_jog(self.device())
        states = [e['state'] for e in self.events if e['event']=='jog_step']
        values = [s['pulse_us'][1] for s in states]
        self.assertEqual((values[0], values[-1]), (1500, 1352))
        self.assertTrue(all(0 < a-b <= 8 for a,b in zip(values, values[1:])))
        self.assertTrue(all(s['enabled_mask']==2 for s in states))
        self.assertTrue(all(s['pulse_us'][:1]+s['pulse_us'][2:]==[1500]*9 for s in states))
        self.assertGreaterEqual(self.now, (len(values)-1)*.12+1.2-1e-8)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertEqual([p.read_bytes() for p in self.locks], before)
        with self.assertRaisesRegex(RuntimeError,'inhibited'):
            PwmDevice(self.reg, motion_inhibit_paths=self.locks).commit([1500]*10, 2, True)

    def test_wrong_scope_range_start_or_confirmation_rejected(self):
        for key,value in [('channel',5),('channel',True),('target_us',1701),('target_us',1300),
                          ('target_us',1500),('expected_sequence',-1),('approval','continue'),
                          ('start_pose_reviewed',False),('observer_ready',1),('sweep_clear',None)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):recovery.validate_plan(plan)
        self.assertEqual(self.reg.writes, [])

    def test_stale_state_prevents_arm(self):
        self.reg.values[0x20]=1
        with self.assertRaises(RuntimeError):self.device().commit([1500]*10, 2, True)
        self.assertEqual(self.reg.writes, [])

    def test_skip_step_other_axis_and_too_fast_rejected(self):
        d=self.device();d.commit([1500]*10, 2, True)
        next_pulses=[1500,1492]+[1500]*8
        with self.assertRaisesRegex(RuntimeError,'rate'):d.commit(next_pulses,2)
        self.advance(.12)
        for pulses,mask in [([1500,1400]+[1500]*8,2),(next_pulses,3),([1492,1492]+[1500]*8,2)]:
            with self.assertRaises(RuntimeError):d.commit(pulses,mask)
        d.commit(next_pulses,2)

    def test_cancel_or_lock_change_stops(self):
        for change in ('cancel','lock'):
            with self.subTest(change=change):
                self.setUp()
                def stop(seconds):
                    self.advance(seconds)
                    (self.cancel if change=='cancel' else self.locks[0]).write_text('changed')
                with self.assertRaises(RuntimeError):self.run_jog(self.device(),stop)
                self.assertFalse(self.events[-1]['state']['armed'])
                self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),1)

    def test_watchdog_or_external_off_cannot_rearm(self):
        def stop(seconds):
            self.advance(seconds);self.reg.write(0x0c,0)
        with self.assertRaises(RuntimeError):self.run_jog(self.device(),stop)
        self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_failed_commit_is_not_retried(self):
        self.reg.apply=False
        d=self.device()
        with self.assertRaises(TimeoutError):self.run_jog(d)
        with self.assertRaises(RuntimeError):d.commit([1500]*10,2,True)
        self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_interrupt_and_completed_session_cannot_restart(self):
        d=self.device()
        def interrupt(seconds):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_jog(d,interrupt)
        self.assertFalse(self.events[-1]['state']['armed'])
        with self.assertRaises(RuntimeError):d.commit([1500]*10,2,True)

    def test_expired_or_missing_lock_prevents_writes(self):
        d=self.device();self.now=15
        with self.assertRaises(RuntimeError):d.commit([1500]*10,2,True)
        self.locks[0].unlink()
        with self.assertRaises(FileNotFoundError):self.device()
        self.assertEqual(self.reg.writes,[])

    def test_dry_run_has_no_mmio(self):
        p=Path(self.temp.name)/'plan.json';p.write_text(json.dumps(self.plan))
        with patch.object(sys,'argv',['jog',str(p)]),patch.object(recovery,'Registers') as r:
            recovery.main();r.assert_not_called()

    def test_third_gimbal_needs_explicit_free_connection_conditions(self):
        self.plan.update(channel=5, target_us=1508, linkage_disconnected=False,
                         free_single_connection=True, puppet_other_rods_disconnected=True)
        self.run_jog(self.device())
        self.assertEqual(self.events[0]['state']['enabled_mask'],16)
        self.assertEqual(self.events[-1]['state']['pulse_us'][4],1508)
        self.assertFalse(self.events[-1]['state']['armed'])
        for key,value in [('channel',7),('free_single_connection',False),
                          ('puppet_other_rods_disconnected',False),('linkage_disconnected',True)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):recovery.validate_plan(plan)


if __name__=='__main__':unittest.main()
