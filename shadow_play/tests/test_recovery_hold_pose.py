import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import recovery_hold_pose as hold
from test_servo_commissioning import FakeRegisters
from servo_pwm_device import PwmDevice


class HoldTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.locks=[self.root/'runtime',self.root/'persistent']
        for p in self.locks:p.write_text('incident')
        self.reg=FakeRegisters();self.now=0.;self.events=[]
        self.plan=dict(approval=hold.APPROVAL,session_id='test',channels=[1,2,3,4],
                       expected_sequence=0,expected_pulses_us=[1500]*10,duration_seconds=2,
                       start_poses_reviewed=True,observer_ready=True,assembly_clearance_reviewed=True)

    def device(self):
        return hold.PoseHoldDevice(self.reg,self.plan,motion_inhibit_paths=self.locks,
                                   cancel_root=self.root,clock=lambda:self.now)

    def advance(self,dt):self.now+=dt

    def run_hold(self,d,sleep=None):
        hold.run_hold(d,self.events.append,clock=lambda:self.now,sleep=sleep or self.advance)

    def test_static_hold_has_one_enable_then_frame_stop_and_keeps_locks(self):
        self.run_hold(self.device())
        self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),2)
        self.assertEqual(self.events[-1]['state']['sequence'],2)
        self.assertTrue(self.events[-1]['normal_frame_stop'])
        self.assertEqual(self.events[0]['state']['enabled_mask'],15)
        self.assertEqual(self.events[0]['state']['pulse_us'],[1500]*10)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertAlmostEqual(self.now,2.)
        self.assertTrue(all(p.read_text()=='incident' for p in self.locks))
        with self.assertRaises(RuntimeError):PwmDevice(self.reg,motion_inhibit_paths=self.locks).commit([1500]*10,15,True)

    def test_changed_pulses_wrong_mask_and_duplicate_rejected(self):
        d=self.device()
        for pulses,mask in [([1501]+[1500]*9,15),([1500]*10,1023)]:
            with self.assertRaises(RuntimeError):d.commit(pulses,mask,True)
        self.assertEqual(self.reg.writes,[])
        self.run_hold(d)
        with self.assertRaises(RuntimeError):d.commit([1500]*10,15,True)

    def test_invalid_scope_or_confirmation(self):
        for key,value in [('channels',list(range(1,11))),('duration_seconds',301),('observer_ready',False),
                          ('session_id','../bad'),('start_poses_reviewed',1),('expected_sequence',-1)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):hold.validate_plan(plan)

    def test_stale_state_prevents_output(self):
        self.reg.values[0x20]=1
        with self.assertRaises(RuntimeError):self.device().commit([1500]*10,15,True)
        self.assertEqual(self.reg.writes,[])

    def test_cancel_stops_without_rearm(self):
        d=self.device()
        def cancel(dt):self.advance(dt);d.cancel_path.write_text('stop')
        with self.assertRaises(RuntimeError):self.run_hold(d,cancel)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),1)

    def test_external_stop_stops(self):
        d=self.device()
        def stop(dt):self.advance(dt);self.reg.write(0x0c,0)
        with self.assertRaises(RuntimeError):self.run_hold(d,stop)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),1)

    def test_interrupt_stops(self):
        d=self.device()
        def interrupt(dt):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_hold(d,interrupt)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_changed_lock_stops(self):
        d=self.device()
        def change(dt):self.advance(dt);self.locks[0].write_text('changed')
        with self.assertRaises(RuntimeError):self.run_hold(d,change)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_failed_commit_never_retries(self):
        self.reg.apply=False;d=self.device()
        with self.assertRaises(TimeoutError):self.run_hold(d)
        with self.assertRaises(RuntimeError):d.commit([1500]*10,15,True)
        self.assertEqual(sum(a==0x18 for a,_ in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_dry_run_has_no_register_access(self):
        p=self.root/'plan.json';p.write_text(json.dumps(self.plan))
        with patch.object(sys,'argv',['hold',str(p)]),patch.object(hold,'Registers') as r:
            hold.main();r.assert_not_called()


if __name__=='__main__':unittest.main()
