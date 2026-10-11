import copy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_local_probe as probe
from test_servo_commissioning import FakeRegisters
from servo_pwm_device import PwmDevice


class PersonProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.locks=[self.root/'runtime',self.root/'persistent']
        for p in self.locks:p.write_text('incident')
        self.reg=FakeRegisters();self.now=0.;self.events=[]
        self.plan=dict(approval=probe.APPROVAL,reference_session='reviewed-test',channel=6,
                       target_us=1508,expected_sequence=0,expected_pulses_us=[1500]*10,
                       rods_connected_without_moving_axes=True,observer_ready=True,views_reviewed=True)

    def device(self):
        return probe.PersonProbeDevice(self.reg,self.plan,motion_inhibit_paths=self.locks,
                                        cancel_path=self.root/'cancel',clock=lambda:self.now)
    def sleep(self,dt):self.now+=dt
    def run_probe(self,d,sleep=None):probe.run_once(d,self.events.append,clock=lambda:self.now,sleep=sleep or self.sleep)

    def test_six_person_axes_one_delta_return_then_frame_stop(self):
        self.run_probe(self.device())
        states=[e['state'] for e in self.events[:-1]]
        self.assertEqual([s['pulse_us'][5] for s in states],[1500,1508,1500])
        self.assertTrue(all(s['enabled_mask']==63 for s in states))
        self.assertTrue(all(s['pulse_us'][:5]+s['pulse_us'][6:]==[1500]*9 for s in states))
        self.assertEqual(self.events[-1]['state']['sequence'],4)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertAlmostEqual(self.now,3.2)
        self.assertTrue(all(p.read_text()=='incident' for p in self.locks))
        with self.assertRaises(RuntimeError):PwmDevice(self.reg,motion_inhibit_paths=self.locks).commit([1500]*10,63,True)

    def test_scope_and_missing_reference_rejected(self):
        for key,value in [('channel',7),('target_us',1525),('reference_session',''),
                          ('views_reviewed',False),('rods_connected_without_moving_axes',False)]:
            p=copy.deepcopy(self.plan);p[key]=value
            with self.assertRaises(ValueError):probe.validate_plan(p)
        self.assertEqual(self.reg.writes,[])

    def test_stale_start_never_arms(self):
        self.reg.values[0x20]=1
        with self.assertRaises(RuntimeError):self.run_probe(self.device())
        self.assertFalse(any(a==0x10 for a,v in self.reg.writes))

    def test_cancel_does_not_return_or_rearm(self):
        d=self.device()
        def cancel(dt):self.sleep(dt);d.cancel.write_text('stop')
        with self.assertRaises(RuntimeError):self.run_probe(d,cancel)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_unknown_commit_no_retry(self):
        self.reg.apply=False;d=self.device()
        with self.assertRaises(TimeoutError):self.run_probe(d)
        with self.assertRaises(RuntimeError):d.commit([1500]*10,63,True)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)

    def test_wrong_target_and_rate_rejected(self):
        d=self.device()
        with self.assertRaises(RuntimeError):d.commit([1500]*9+[1501],63,True)
        d.commit([1500]*10,63,True)
        with self.assertRaises(RuntimeError):d.commit(d.path[1],63,False)

    def test_larger_probe_ramps_both_ways_without_changing_other_axes(self):
        self.plan['target_us']=1476
        self.run_probe(self.device())
        states=[e['state'] for e in self.events[:-1]]
        self.assertEqual([s['pulse_us'][5] for s in states],[1500,1492,1484,1476,1484,1492,1500])
        self.assertTrue(all(s['pulse_us'][:5]+s['pulse_us'][6:]==[1500]*9 for s in states))
        self.assertTrue(all(s['enabled_mask']==63 for s in states))
        self.assertAlmostEqual(self.now,7.2)
        self.assertEqual(self.events[-1]['state']['sequence'],8)


if __name__=='__main__':unittest.main()
