import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_linkage_session as linkage
from test_person_visible_motion_session import VisibleTests
from person_recovery_session import ObservationLost


class LinkageTests(unittest.TestCase):
    sleep = VisibleTests.sleep
    emit = VisibleTests.emit
    resume = VisibleTests.resume

    def setUp(self):
        VisibleTests.setUp(self)
        self.plan.update(approval=linkage.APPROVAL,
                         stages=[[0,0,20,0,40,0],[10,0,30,0,40,60]], demo_stages=[2,2])
        self.d=linkage.LinkageSession(self.reg,self.plan,self.host,
            motion_inhibit_paths=[self.lock],cancel_path=self.root/'cancel',
            clock=lambda:self.now,wall=lambda:1000)

    def test_vector_steps_commit_together_and_preserve_static_axes(self):
        self.resume();before=len(self.reg.writes)
        self.d.probe(2,self.emit,self.sleep)
        states=[r['state'] for r in self.events if r['event']=='probe_step']
        old=self.plan['expected_pulses_us']
        self.assertTrue(any(sum(a!=b for a,b in zip(old,s['pulse_us']))>1 for s in states))
        for row in states:
            p=row['pulse_us']
            self.assertLessEqual(max(abs(a-b) for a,b in zip(p,old)),1)
            for i in (1,3,6,7,8,9):self.assertEqual(p[i],self.plan['expected_pulses_us'][i])
            self.assertEqual(row['enabled_mask'],63);self.assertTrue(row['armed'])
            old=p
        self.assertEqual(self.d.pulses,self.plan['expected_pulses_us'])
        self.assertFalse(any(a in (0x0c,0x10) for a,v in self.reg.writes[before:]))

    def test_changed_head_pitch_negative_or_oversized_vectors_rejected(self):
        for vector in ([0,1,20,0,40,0],[0,0,20,1,40,0],[0,0,41,0,40,0],
                       [0,0,20,0,61,0],[-1,0,20,0,40,0],[True,0,20,0,40,0]):
            p=copy.deepcopy(self.plan);p['stages']=[vector];p['demo_stages']=[1]
            with self.assertRaises(ValueError):linkage.validate_plan(p)
        self.assertEqual(self.reg.writes,[])

    def test_bilateral_opposite_pitch_steps_are_synchronous_and_return(self):
        self.plan.update(bilateral_hand_diagnostic=True,
                         stages=[[0,-40,0,0,0,20]],demo_stages=[1])
        self.d=linkage.LinkageSession(self.reg,self.plan,self.host,
            motion_inhibit_paths=[self.lock],cancel_path=self.root/'cancel',
            clock=lambda:self.now,wall=lambda:1000)
        self.resume();self.d.probe(1,self.emit,self.sleep)
        states=[r['state'] for r in self.events if r['event']=='probe_step']
        base=self.plan['expected_pulses_us'];previous=base
        self.assertEqual(min(s['pulse_us'][1] for s in states),base[1]-40)
        self.assertEqual(max(s['pulse_us'][5] for s in states),base[5]+20)
        for s in states:
            p=s['pulse_us'];self.assertLessEqual(max(abs(a-b) for a,b in zip(p,previous)),1)
            for i in (0,2,3,4,6,7,8,9):self.assertEqual(p[i],base[i])
            self.assertLessEqual(abs((p[1]-base[1])+2*(p[5]-base[5])),1)
            previous=p
        self.assertEqual(self.d.pulses,base)

    def test_bilateral_requires_receipt_and_bounded_opposite_pitch(self):
        for flag,vector in [(False,[0,-10,0,0,0,20]),(True,[0,-81,0,0,0,20]),
                (True,[0,1,0,0,0,20]),(True,[0,-10,0,0,0,0]),
                (True,[0,-10,0,1,0,20]),(True,[0,-10,0,0,0,121])]:
            p=copy.deepcopy(self.plan);p.update(bilateral_hand_diagnostic=flag,
                stages=[vector],demo_stages=[1])
            with self.assertRaises(ValueError):linkage.validate_plan(p)
        self.assertEqual(self.reg.writes,[])

    def test_head_support_is_exclusive_bounded_and_preserves_hand_commands(self):
        p=copy.deepcopy(self.plan);p.update(head_support_diagnostic=True,
            stages=[[0,0,0,-80,0,0]],demo_stages=[1])
        d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.d=d;self.resume();d.probe(1,self.emit,self.sleep)
        states=[r['state']['pulse_us'] for r in self.events if r['event']=='probe_step']
        self.assertEqual(min(s[3] for s in states),p['expected_pulses_us'][3]-80)
        previous=p['expected_pulses_us']
        for s in states:
            for i in (0,1,2,4,5,6,7,8,9):self.assertEqual(s[i],p['expected_pulses_us'][i])
            self.assertLessEqual(abs(s[3]-previous[3]),1);previous=s
        self.assertEqual(d.pulses,p['expected_pulses_us'])
        for vector in ([1,0,0,-40,0,0],[0,0,0,-81,0,0],[0,0,0,1,0,0]):
            q=copy.deepcopy(p);q['stages']=[vector]
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        for extra in ({'bilateral_hand_diagnostic':True},{'head_support_diagnostic':False}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)

    def test_continued_support_requires_exact_normal_off_pose(self):
        p=copy.deepcopy(self.plan)
        p.update(bilateral_hand_diagnostic=True, head_support_reference_offset_us=-60,
                 stages=[[0,-80,0,0,0,120]],demo_stages=[1])
        pulses=p['expected_pulses_us'][:];pulses[3]-=60
        p['expected_pulses_us']=pulses[:]
        for key in ('previous_held_state','previous_off_state'):p[key]['pulse_us']=pulses[:]
        linkage.validate_plan(p)
        self.reg.values[0x8c]=pulses[3]
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();self.d.probe(1,self.emit,self.sleep)
        self.assertTrue(all(r['state']['pulse_us'][3]==1514 for r in self.events))
        self.assertEqual(self.d.pulses,pulses)
        for key in ('previous_held_state','previous_off_state'):
            q=copy.deepcopy(p);q[key]['pulse_us'][3]+=1
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        for offset in (-40,-80,True):
            q=copy.deepcopy(p);q['head_support_reference_offset_us']=offset
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        q=copy.deepcopy(p);q['expected_pulses_us'][0]+=1
        with self.assertRaises(ValueError):linkage.validate_plan(q)
    def test_supported_hands_preserve_head_lift_until_explicit_finish(self):
        p=copy.deepcopy(self.plan);p.update(bilateral_hand_diagnostic=True,
            head_supported_bilateral_diagnostic=True,head_support_offset_us=-60,
            stages=[[0,-40,0,0,0,80]],demo_stages=[1,1])
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        def emit(row):
            self.events.append(row);action=None
            if row['event']=='hold_alive' and not self.d.completed:action='probe_1'
            elif row['event']=='probe_complete' and not self.d.demo_used:action='review_1'
            elif row['event']=='path_reviewed':action='demo'
            elif row['event']=='demo_complete':action='finish'
            if action:self.host.action=(action,self.d.sequence)
        linkage.run_session(self.d,emit,sleep=self.sleep)
        hand_states=[r['state']['pulse_us'] for r in self.events if r['event']=='probe_step']
        self.assertTrue(hand_states)
        self.assertTrue(all(s[3]==p['expected_pulses_us'][3]-60 for s in hand_states))
        self.assertEqual(self.events[-1]['state']['pulse_us'],p['expected_pulses_us'])
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)
        self.assertEqual(self.lock.read_text(),'retain')

    def test_alternating_paths_keep_support_with_explicit_bounded_tempo(self):
        p=copy.deepcopy(self.plan)
        p.update(bilateral_hand_diagnostic=True,head_support_reference_offset_us=-60,
                 supported_martial_diagnostic=True,tempo_step_us=3,peak_hold_ms=400,
                 stages=[[0,-80,0,0,0,0],[0,0,0,0,40,120]],demo_stages=[1,2,1,2])
        pulses=p['expected_pulses_us'][:];pulses[3]-=60
        p['expected_pulses_us']=pulses[:]
        for key in ('previous_held_state','previous_off_state'):p[key]['pulse_us']=pulses[:]
        self.reg.values[0x8c]=pulses[3]
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume()
        for stage in (1,2):self.d.probe(stage,self.emit,self.sleep)
        previous=pulses;larger=False
        for r in self.events:
            if r['event']!='probe_step':continue
            values=r['state']['pulse_us'];step=max(abs(a-b) for a,b in zip(values,previous))
            self.assertLessEqual(step,3);larger|=step>1
            self.assertEqual(values[3],1514);self.assertEqual(values[6:],pulses[6:])
            previous=values
        self.assertTrue(larger);self.assertEqual(self.d.pulses,pulses)
        for field,value in (('tempo_step_us',4),('tempo_step_us',True),('peak_hold_ms',0),
                            ('supported_martial_diagnostic',False),('head_support_reference_offset_us',-40)):
            q=copy.deepcopy(p);q[field]=value
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        q=copy.deepcopy(self.plan);q['tempo_step_us']=3
        with self.assertRaises(ValueError):linkage.validate_plan(q)

    def test_support_video_loss_does_not_restore_or_start_hand_motion(self):
        p=copy.deepcopy(self.plan);p.update(bilateral_hand_diagnostic=True,
            head_supported_bilateral_diagnostic=True,head_support_offset_us=-60,
            stages=[[0,-40,0,0,0,80]],demo_stages=[1])
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        def check():
            if self.now>4:raise ObservationLost('camera stale')
        self.host.check=check
        with self.assertRaises(ObservationLost):linkage.run_session(self.d,self.emit,sleep=self.sleep)
        self.assertFalse(any(r['event'] in ('reference_restored','probe_started') for r in self.events))
        self.assertFalse(self.events[-1]['state']['armed'])
    def test_manual_waypoint_and_fast_step_rejected_before_write(self):
        self.resume();self.d.phase='linkage';self.sleep(.05)
        p=self.d.pulses[:];p[4]+=1
        count=len(self.reg.writes)
        with self.assertRaises(RuntimeError):self.d.adopt(p,63)
        self.assertEqual(len(self.reg.writes),count)
        self.d.expected_waypoint=p[:];self.d.adopt(p,63)
        self.d.expected_waypoint=p[:]
        with self.assertRaises(RuntimeError):self.d.adopt(p,63)

    def test_reviewed_vector_demo_one_arm_keeps_lock(self):
        def emit(row):
            self.events.append(row);action=None
            if row['event']=='reference_held':action='probe_2'
            elif row['event']=='probe_complete' and not self.d.demo_used:action='review_2'
            elif row['event']=='path_reviewed':action='demo'
            elif row['event']=='demo_complete':action='finish'
            if action:self.host.action=(action,self.d.sequence)
        linkage.run_session(self.d,emit,sleep=self.sleep)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)
        self.assertEqual(sum(a==0x0c for a,v in self.reg.writes),1)
        self.assertEqual(self.lock.read_text(),'retain')
        self.assertEqual(self.events[-1]['state']['pulse_us'],self.plan['expected_pulses_us'])

    def test_unreviewed_demo_stops_without_rearm(self):
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('demo',self.d.sequence)
        with self.assertRaises(RuntimeError):linkage.run_session(self.d,emit,sleep=self.sleep)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_linkage_video_loss_no_automatic_return(self):
        def check():
            if self.now>4:raise ObservationLost('camera stale')
        self.host.check=check
        def emit(row):
            self.events.append(row)
            if row['event']=='reference_held':self.host.action=('probe_2',self.d.sequence)
        with self.assertRaises(ObservationLost):linkage.run_session(self.d,emit,sleep=self.sleep)
        self.assertNotEqual(self.d.pulses,self.plan['expected_pulses_us'])
        self.assertFalse(self.events[-1]['state']['armed'])


if __name__=='__main__':unittest.main()
