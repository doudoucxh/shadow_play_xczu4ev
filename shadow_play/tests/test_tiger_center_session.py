import copy
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import tiger_center_session as tiger
from test_servo_commissioning import FakeRegisters


class Host:
    action=None
    def check(self):pass


class TigerCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lock=self.root/'incident';self.lock.write_text('preserved')
        self.reg=FakeRegisters();self.host=Host();self.now=0;self.events=[]
        values=[1537,1212,1537,1514,1508,1740,1500,1426,1500,1500]
        for i,v in enumerate(values):self.reg.values[0x80+4*i]=v
        self.plan=dict(approval=tiger.APPROVAL,session_id='test',expected_sequence=0,
            expected_pulses_us=values,observer_ready=True,loaded_centering_explicitly_authorized=True,
            dual_view_clearance_reviewed=True,reviewed_at_unix_ms=1000000,duration_seconds=120)
        self.d=tiger.TigerCenterSession(self.reg,self.plan,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)

    def sleep(self,dt):self.now+=dt

    def test_sequential_centers_only_tiger_and_retains_locks(self):
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('probe_1',self.d.sequence)
            elif row['event']=='probe_complete':
                self.host.action=('probe_'+str(row['axis']+1) if row['axis']<4 else 'finish',self.d.sequence)
        tiger.run_session(self.d,emit,sleep=self.sleep)
        states=[r['state'] for r in self.events if r['event']=='axis_centered']
        self.assertEqual([s['enabled_mask'] for s in states],[64,192,448,960])
        self.assertTrue(all(s['pulse_us'][:6]==self.plan['expected_pulses_us'][:6] for s in states))
        self.assertEqual(states[-1]['pulse_us'][6:],[1500]*4)
        self.assertEqual(self.events[-1]['state']['enabled_mask'],0)
        self.assertTrue(self.events[-1]['normal_frame_stop']);self.assertEqual(self.lock.read_text(),'preserved')
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)

    def test_skip_repeat_or_generic_commit_rejected(self):
        with self.assertRaises(RuntimeError):self.d.center(2,self.events.append,self.sleep)
        self.assertEqual(self.reg.writes,[])
        self.d.center(1,self.events.append,self.sleep)
        with self.assertRaises(RuntimeError):self.d.center(1,self.events.append,self.sleep)
        with self.assertRaises(RuntimeError):self.d.commit([1500]*10,1023)

    def test_stale_state_or_changed_lock_cannot_arm(self):
        self.reg.values[0x20]=1
        with self.assertRaises(RuntimeError):self.d.center(1,self.events.append,self.sleep)
        self.reg.values[0x20]=0;self.lock.write_text('changed')
        with self.assertRaises(RuntimeError):self.d.center(1,self.events.append,self.sleep)
        self.assertEqual(self.reg.writes,[])

    def test_video_loss_stops_without_centering_another_axis(self):
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('probe_1',self.d.sequence)
        def check():
            if self.now>1:raise tiger.ObservationLost('video lost')
        self.host.check=check
        with self.assertRaises(tiger.ObservationLost):tiger.run_session(self.d,emit,sleep=self.sleep)
        self.assertEqual(len([r for r in self.events if r['event']=='axis_centered']),1)
        self.assertFalse(self.events[-1]['state']['armed']);self.assertTrue(self.events[-1]['normal_frame_stop'])

    def test_plan_needs_explicit_authorization_and_fresh_review(self):
        for k,v in [('loaded_centering_explicitly_authorized',False),('observer_ready',False),
                    ('reviewed_at_unix_ms',879999),('expected_sequence',True)]:
            p=copy.deepcopy(self.plan);p[k]=v
            with self.assertRaises(ValueError):tiger.validate_plan(p,wall=lambda:1000)


if __name__=='__main__':unittest.main()
