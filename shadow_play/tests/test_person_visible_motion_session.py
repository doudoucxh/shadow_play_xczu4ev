import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_visible_motion_session as visible
from person_recovery_session import ObservationLost
from test_servo_commissioning import FakeRegisters


class Host:
    def __init__(self):self.action=None
    def check(self):pass


class VisibleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lock=self.root/'incident';self.lock.write_text('retain')
        self.reg=FakeRegisters();self.now=0.;self.host=Host();self.events=[]
        pulses=visible.REFERENCE+[1500,1426,1500,1500]
        for i,v in enumerate(pulses):self.reg.values[0x80+i*4]=v
        self.reg.values[0x20]=1916
        state=dict(enabled_mask=0,armed=False,faults=0,pending=False,sequence=1916,pulse_us=pulses)
        held={**state,'enabled_mask':63,'armed':True,'sequence':1915}
        self.plan=dict(approval=visible.APPROVAL,session_id='test',expected_sequence=1916,
            expected_pulses_us=pulses,operator_unchanged_report='电源和机构都没动',observer_ready=True,
            dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000000,previous_held_state=held,
            previous_off_state=state,previous_normal_frame_stop=True,duration_seconds=900)
        self.d=visible.VisibleSession(self.reg,self.plan,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)

    def sleep(self,dt):self.now+=dt
    def emit(self,row):self.events.append(row)
    def resume(self):
        self.d.adopt(self.d.pulses[:],63);self.d.phase='holding'

    def test_missing_changed_or_expired_physical_report_never_authorizes(self):
        for key,value in [('operator_unchanged_report','手动转过'),('dual_view_pose_reviewed',False),
                          ('observer_ready',False),('previous_normal_frame_stop',False),
                          ('reviewed_at_unix_ms',800000),('expected_sequence',1915)]:
            p=copy.deepcopy(self.plan);p[key]=value
            with self.assertRaises(ValueError):visible.validate_plan(p,wall=lambda:1000)
        self.assertEqual(self.reg.writes,[])

    def test_drifted_registers_never_arm(self):
        self.reg.values[0x20]=1917
        with self.assertRaises(RuntimeError):visible.run_session(self.d,self.emit,sleep=self.sleep)
        self.assertFalse(any(a==0x10 for a,v in self.reg.writes))

    def test_stage_changes_only_selected_axis_and_returns_without_rearming(self):
        self.resume();before=len(self.reg.writes)
        self.d.probe(6,120,self.emit,self.sleep)
        states=[r['state'] for r in self.events if r['event']=='probe_step']
        self.assertEqual(max(s['pulse_us'][5] for s in states),1620)
        previous=self.plan['expected_pulses_us']
        for s in states:
            self.assertEqual(s['pulse_us'][:5],previous[:5])
            self.assertEqual(s['pulse_us'][6:],previous[6:])
            self.assertLessEqual(abs(s['pulse_us'][5]-previous[5]),1)
            self.assertEqual(s['enabled_mask'],63);self.assertTrue(s['armed'])
            previous=s['pulse_us']
        self.assertEqual(self.d.pulses,self.plan['expected_pulses_us'])
        self.assertFalse(any(a in (0x0c,0x10) for a,v in self.reg.writes[before:]))

    def test_unreviewed_next_stage_is_rejected(self):
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('probe_6',self.d.sequence)
            if row['event']=='probe_complete':self.host.action=('probe_6',self.d.sequence)
        with self.assertRaises(RuntimeError):visible.run_session(self.d,emit,sleep=self.sleep)
        self.assertEqual([r['offset_us'] for r in self.events if r['event']=='probe_started'],[40])
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_reviewed_stages_then_one_demo_keep_person_hold_and_incident_lock(self):
        def emit(row):
            self.events.append(row)
            action=None
            if row['event']=='reference_held':action='probe_6'
            elif row['event']=='probe_complete' and not self.d.demo_used:action='review_'+str(row['axis'])
            elif row['event']=='path_reviewed':
                if self.d.reviewed.get(6,0)<80:action='probe_6'
                elif self.d.reviewed.get(5,0)<80:action='probe_5'
                else:action='demo'
            elif row['event']=='demo_complete':action='finish'
            if action:self.host.action=(action,self.d.sequence)
        visible.run_session(self.d,emit,sleep=self.sleep)
        self.assertTrue(self.d.demo_used);self.assertEqual(self.d.reviewed,{6:80,5:80})
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)
        self.assertEqual(sum(a==0x0c for a,v in self.reg.writes),1)
        self.assertTrue(self.events[-1]['normal_frame_stop'])
        self.assertEqual(self.lock.read_text(),'retain')

    def test_camera_loss_mid_path_stops_without_command_return(self):
        def check():
            if self.now>4:raise ObservationLost('camera stale')
        self.host.check=check
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('probe_6',self.d.sequence)
        with self.assertRaises(ObservationLost):visible.run_session(self.d,emit,sleep=self.sleep)
        self.assertGreater(self.events[-1]['state']['pulse_us'][5],1500)
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertTrue(self.events[-1]['normal_frame_stop'])

    def test_tiger_other_axis_or_accelerated_step_is_rejected_before_write(self):
        self.resume();self.d.phase='motion';self.d.active_axis=6;self.d.active_offset=40
        self.sleep(.05)
        for index,delta in ((6,1),(0,1),(5,2),(5,-1)):
            p=self.d.pulses[:];p[index]+=delta;count=len(self.reg.writes)
            with self.assertRaises(RuntimeError):self.d.adopt(p,63)
            self.assertEqual(len(self.reg.writes),count)


if __name__=='__main__':unittest.main()
