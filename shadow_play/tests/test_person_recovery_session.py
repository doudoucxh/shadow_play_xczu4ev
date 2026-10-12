import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_recovery_session as recovery
from test_servo_commissioning import FakeRegisters


class Host:
    def __init__(self):self.action=None
    def check(self):pass


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lock=self.root/'incident';self.lock.write_text('preserved')
        self.reg=FakeRegisters();self.host=Host();self.now=0.;self.events=[]
        self.plan=dict(approval=recovery.APPROVAL,session_id='unit-test',expected_sequence=0,
            expected_pulses_us=[1500]*10,axes_1_to_4_released=True,
            axes_5_6_single_free_connection=True,clearance_reviewed=True,observer_ready=True,duration_seconds=120)
        self.d=recovery.RecoverySession(self.reg,self.plan,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now)

    def sleep(self,dt):self.now+=dt
    def emit(self,row):
        self.events.append(row)
        if row['event']=='reference_held':self.host.action=('finish',self.d.sequence)

    def initialize(self):
        for axis in range(1,7):
            p=self.d.pulses[:];p[axis-1]=1500;self.d.adopt(p,(1<<axis)-1);self.sleep(3)
        self.d.phase='reference'
        for i,target in enumerate(recovery.REFERENCE):
            while self.d.pulses[i]!=target:
                self.sleep(.125);p=self.d.pulses[:];p[i]+=1 if target>p[i] else -1;self.d.adopt(p,63)
        self.d.phase='holding'

    def test_centers_accumulate_without_off_until_reference_and_finish(self):
        recovery.run_session(self.d,self.emit,sleep=self.sleep)
        self.assertEqual([e['state']['enabled_mask'] for e in self.events if e['event']=='axis_centered'],[1,3,7,15,31,63])
        held=next(e['state'] for e in self.events if e['event']=='reference_held')
        self.assertEqual(held['pulse_us'][:6],recovery.REFERENCE)
        self.assertEqual(held['pulse_us'][6:],[1500]*4)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)
        self.assertEqual([i for i,(a,v) in enumerate(self.reg.writes) if a==0x0c],[len(self.reg.writes)-1])
        self.assertFalse(self.events[-1]['state']['armed']);self.assertTrue(self.events[-1]['normal_frame_stop'])
        self.assertEqual(self.lock.read_text(),'preserved')
        self.assertTrue(all(e['state']['enabled_mask']&~63==0 for e in self.events))

    def test_no_skipped_axis_or_tiger_change_or_static_target_change(self):
        with self.assertRaises(RuntimeError):self.d.adopt([1500]*10,3)
        self.assertEqual(self.reg.writes,[])
        self.initialize();p=self.d.pulses[:];p[6]+=1
        with self.assertRaises(RuntimeError):self.d.adopt(p,63)
        p=self.d.pulses[:];p[0]+=1
        with self.assertRaises(RuntimeError):self.d.adopt(p,63)
        with self.assertRaises(RuntimeError):self.d.adopt(self.d.pulses,127)

    def test_probe_returns_to_held_reference_without_off(self):
        self.initialize();writes=len(self.reg.writes)
        self.d.probe(2,self.events.append,self.sleep)
        states=[e['state'] for e in self.events if e['event']=='probe_step']
        self.assertEqual(len(states),64)
        self.assertEqual(min(s['pulse_us'][1] for s in states),recovery.REFERENCE[1]-12)
        for old,new in zip(states,states[1:]):self.assertLessEqual(abs(new['pulse_us'][1]-old['pulse_us'][1]),1)
        self.assertTrue(all(s['enabled_mask']==63 and s['armed'] for s in states))
        self.assertEqual(self.d.pulses[:6],recovery.REFERENCE);self.assertEqual(self.d.probed,{2})
        self.assertFalse(any(a in (0x0c,0x10) for a,v in self.reg.writes[writes:]))

    def test_stale_start_never_arms(self):
        self.reg.values[0x20]=1
        with self.assertRaises(RuntimeError):recovery.run_session(self.d,self.events.append,sleep=self.sleep)
        self.assertFalse(any(a==0x10 for a,v in self.reg.writes))

    def test_video_loss_disables_at_frame_boundary_without_return(self):
        def check():
            if self.now>3.3:raise recovery.ObservationLost('stale video')
        self.host.check=check
        with self.assertRaises(recovery.ObservationLost):recovery.run_session(self.d,self.events.append,sleep=self.sleep)
        self.assertTrue(self.events[-1]['normal_frame_stop'])
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertEqual(self.events[-1]['state']['sequence'],self.events[-2]['state']['sequence']+1)

    def test_fault_or_cancel_wins_over_video_stop(self):
        for fault in ('hardware','cancel'):
            self.setUp()
            def sleep(dt):
                self.now+=dt
                if self.now>3.3:
                    if fault=='hardware':self.reg.values[0x0c]=1
                    else:(self.root/'cancel').touch()
            def check():
                if self.now>3.3:raise recovery.ObservationLost('stale video')
            self.host.check=check
            with self.assertRaises(RuntimeError) as raised:recovery.run_session(self.d,self.events.append,sleep=sleep)
            self.assertNotIsInstance(raised.exception,recovery.ObservationLost)
            self.assertFalse(self.events[-1]['normal_frame_stop'])

    def test_unreviewed_demo_and_unconnected_probe_stop_without_motion(self):
        for action in ('demo','probe_1','review_1'):
            self.setUp()
            def emit(row):
                self.events.append(row)
                if row['event']=='reference_held':self.host.action=(action,self.d.sequence)
            with self.assertRaises(RuntimeError):recovery.run_session(self.d,emit,sleep=self.sleep)
            self.assertFalse(any(e['event']=='probe_step' for e in self.events))
            self.assertFalse(self.events[-1]['state']['armed'])

    def test_old_action_sequence_stops(self):
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('reconnected',0)
        with self.assertRaisesRegex(RuntimeError,'Stale action'):recovery.run_session(self.d,emit,sleep=self.sleep)

    def test_reviewed_new_paths_demo_and_return_keep_continuous_hold(self):
        self.d.deadline=240
        remaining=list(recovery.DEMO_AXES)
        def action(name):self.host.action=(name,self.d.sequence)
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':action('reconnected')
            elif row['event']=='reconnection_recorded':action('probe_'+str(remaining.pop(0)))
            elif row['event']=='probe_complete' and not self.d.demo_used:action('review_'+str(row['axis']))
            elif row['event']=='path_reviewed':
                action('probe_'+str(remaining.pop(0)) if remaining else 'demo')
            elif row['event']=='demo_complete':action('finish')
        recovery.run_session(self.d,emit,sleep=self.sleep)
        completed=next(e['state'] for e in self.events if e['event']=='demo_complete')
        self.assertEqual(completed['pulse_us'][:6],recovery.REFERENCE)
        self.assertTrue(completed['armed']);self.assertEqual(completed['enabled_mask'],63)
        self.assertEqual(self.d.reviewed,set(recovery.DEMO_AXES))
        self.assertTrue(self.d.demo_used)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)
        self.assertEqual(sum(a==0x0c for a,v in self.reg.writes),1)
        self.assertTrue(all(e['state']['pulse_us'][6:]==[1500]*4 for e in self.events if 'state' in e))
        self.assertEqual(self.lock.read_text(),'preserved')

    def test_plan_requires_physical_release_and_presence(self):
        for key,value in [('axes_1_to_4_released',False),('observer_ready',False),('duration_seconds',901),('expected_sequence',True)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):recovery.validate_plan(plan)

    def test_host_protocol_is_exact_and_has_expiring_lease(self):
        h=recovery.HostControl(99,clock=lambda:self.now)
        with patch.object(recovery.select,'select',return_value=([99],[],[])),patch.object(recovery.os,'read',return_value=b': # PERSON_RECOVERY_LEASE\n: # PERSON_RECOVERY_ACTION probe_1 965\n'):
            h.check()
        self.assertTrue(h.received);self.assertEqual(h.action,('probe_1',965));self.now=2
        with patch.object(recovery.select,'select',return_value=([],[],[])):
            with self.assertRaises(recovery.ObservationLost):h.check()
        for line,error in [(b': # PERSON_RECOVERY_VIDEO_STOP\n',recovery.ObservationLost),
                (b': # PERSON_RECOVERY_ACTION probe_7 0\n',RuntimeError),
                (b': # PERSON_RECOVERY_ACTION demo 0\n: # PERSON_RECOVERY_ACTION demo 0\n',RuntimeError)]:
            h=recovery.HostControl(99,clock=lambda:self.now)
            with patch.object(recovery.select,'select',return_value=([99],[],[])),patch.object(recovery.os,'read',return_value=line):
                with self.assertRaises(error):h.check()


if __name__=='__main__':unittest.main()
