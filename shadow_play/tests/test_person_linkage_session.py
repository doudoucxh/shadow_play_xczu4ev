import copy
import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_frame_pacing_does_not_add_a_second_frame_after_readback(self):
        p=copy.deepcopy(self.plan)
        p.update(bilateral_hand_diagnostic=True,head_support_reference_offset_us=-60,
                 supported_martial_diagnostic=True,tempo_step_us=8,peak_hold_ms=100,
                 motion_interval_ms=20,stages=[[20,-80,20,0,40,120]],demo_stages=[1])
        pulses=p['expected_pulses_us'][:];pulses[3]-=60
        p['expected_pulses_us']=pulses[:]
        for key in ('previous_held_state','previous_off_state'):p[key]['pulse_us']=pulses[:]
        self.reg.values[0x8c]=pulses[3]
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();original=linkage.PwmDevice.commit;starts=[]
        def commit(device,*args,**kwargs):
            starts.append(self.now);state=original(device,*args,**kwargs)
            self.now+=.019;return state
        started=self.now
        with patch.object(linkage.PwmDevice,'commit',commit):self.d.probe(1,self.emit,self.sleep)
        self.assertTrue(all(b-a >= .02-1e-9 for a,b in zip(starts,starts[1:])))
        self.assertLess(self.now-started,1.3)
        previous=pulses
        for row in self.events:
            if row['event']=='probe_step':
                values=row['state']['pulse_us']
                self.assertLessEqual(max(abs(a-b) for a,b in zip(values,previous)),8)
                self.assertEqual(values[3],1514);self.assertEqual(values[6:],pulses[6:])
                previous=values
        self.assertEqual(self.d.pulses,pulses)

    def test_fast_console_is_throttled_but_local_motion_log_is_complete(self):
        log=io.StringIO();sent=[];now=[0.]
        emit=linkage.motion_emitter(log,sent.append,clock=lambda:now[0])
        for i in range(25):
            now[0]=i*.02;emit(dict(event='probe_step',sequence=i))
        emit(dict(event='probe_complete',sequence=24))
        rows=[json.loads(x) for x in log.getvalue().splitlines()]
        self.assertEqual(len(rows),26)
        self.assertEqual(sum(r['event']=='probe_step' for r in sent),3)
        self.assertEqual(sent[-1]['event'],'probe_complete')

    def test_low_hand_geometry_is_separate_single_pitch_diagnostic(self):
        p=copy.deepcopy(self.plan)
        p.update(bilateral_hand_diagnostic=True,head_support_reference_offset_us=-60,
                 supported_martial_diagnostic=True,tempo_step_us=3,peak_hold_ms=400,
                 motion_interval_ms=20,lower_hands_diagnostic=True,
                 stages=[[0,-140,0,0,0,0],[0,0,0,0,0,240]],demo_stages=[1,2])
        pulses=p['expected_pulses_us'][:];pulses[3]-=60;p['expected_pulses_us']=pulses[:]
        for key in ('previous_held_state','previous_off_state'):p[key]['pulse_us']=pulses[:]
        linkage.validate_plan(p)
        for vector in ([0,-141,0,0,0,0],[0,0,0,0,0,241],[0,-140,0,0,0,240],[1,-140,0,0,0,0]):
            q=copy.deepcopy(p);q['stages']=[vector];q['demo_stages']=[1]
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        for key,value in (('tempo_step_us',8),('motion_interval_ms',10),('lower_hands_diagnostic',False)):
            q=copy.deepcopy(p);q[key]=value
            with self.assertRaises(ValueError):linkage.validate_plan(q)
    def test_combined_lowering_requires_explicit_slow_mode_and_preserves_body(self):
        p=copy.deepcopy(self.plan)
        p.update(bilateral_hand_diagnostic=True,head_support_reference_offset_us=-60,
                 supported_martial_diagnostic=True,tempo_step_us=3,peak_hold_ms=400,
                 motion_interval_ms=20,lower_hands_diagnostic=True,
                 combined_lower_hands_diagnostic=True,
                 stages=[[0,-140,0,0,0,240]],demo_stages=[1])
        pulses=p['expected_pulses_us'][:];pulses[3]-=60;p['expected_pulses_us']=pulses[:]
        for key in ('previous_held_state','previous_off_state'):p[key]['pulse_us']=pulses[:]
        self.reg.values[0x8c]=pulses[3]
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();self.d.probe(1,self.emit,self.sleep)
        previous=pulses
        for row in self.events:
            if row['event']!='probe_step':continue
            values=row['state']['pulse_us']
            self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,values)),3)
            for i in (0,2,3,4,6,7,8,9):self.assertEqual(values[i],pulses[i])
            previous=values
        self.assertEqual(self.d.pulses,pulses)
        for extra in ({'tempo_step_us':8},{'combined_lower_hands_diagnostic':False},
                      {'stages':[[0,-140,0,0,0,0]]},{'stages':[[1,-140,0,0,0,240]]}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        q=copy.deepcopy(p);q.pop('lower_hands_diagnostic')
        with self.assertRaises(ValueError):linkage.validate_plan(q)

    def low_guard_plan(self, continued=False):
        p=copy.deepcopy(self.plan)
        p.update(bilateral_hand_diagnostic=True,head_support_reference_offset_us=-60,
                 supported_martial_diagnostic=True,tempo_step_us=3,peak_hold_ms=400,
                 motion_interval_ms=20,low_guard_diagnostic=True,
                 combined_lowering_receipt_sha256=linkage.COMBINED_LOWERING_RECEIPT,
                 stages=[[0,140,0,0,0,0],[0,0,0,0,0,-240],[0,140,0,0,0,-240]],
                 demo_stages=[1,2,3])
        pulses=p['expected_pulses_us'][:];pulses[3]-=60
        if continued:
            p['lowered_hands_reference_offset_us']=list(linkage.LOW_GUARD)
            for i,delta in enumerate(linkage.LOW_GUARD):pulses[i]+=delta
        p['expected_pulses_us']=pulses[:]
        for key in ('previous_held_state','previous_off_state'):p[key]['pulse_us']=pulses[:]
        for i,v in enumerate(pulses):self.reg.values[0x80+4*i]=v
        return p

    def test_guard_returns_to_low_hands_and_stops_without_high_reset(self):
        p=self.low_guard_plan()
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        def emit(row):
            self.events.append(row)
            if row['event']=='support_established':self.host.action=('probe_3',self.d.sequence)
            elif row['event']=='probe_complete':self.host.action=('review_3',self.d.sequence)
            elif row['event']=='path_reviewed':self.host.action=('finish',self.d.sequence)
        linkage.run_session(self.d,emit,sleep=self.sleep)
        low=p['expected_pulses_us'][:]
        for i,delta in enumerate(linkage.LOW_GUARD):low[i]+=delta
        self.assertEqual(self.events[-1]['state']['pulse_us'],low)
        self.assertTrue(self.events[-1]['normal_frame_stop'])
        self.assertFalse(self.events[-1]['state']['armed'])
        previous=p['expected_pulses_us']
        for r in self.events:
            if r['event'] not in ('support_step','probe_step'):continue
            values=r['state']['pulse_us'];self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,values)),3)
            self.assertEqual(values[3],1514);self.assertEqual(values[6:],low[6:]);previous=values
        self.assertEqual(self.lock.read_text(),'retain')

    def test_guard_reference_requires_exact_low_pose_and_disallows_general_probe(self):
        p=self.low_guard_plan(continued=True);linkage.validate_plan(p)
        d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.assertEqual(d.support_base,p['expected_pulses_us'])
        from person_visible_motion_session import VisibleSession
        with self.assertRaises(RuntimeError):VisibleSession.probe(d,2,40,self.emit,self.sleep)
        for extra in ({'combined_lowering_receipt_sha256':'0'*64},{'tempo_step_us':8},
                      {'stages':[[1,140,0,0,0,0]]},{'stages':[[0,141,0,0,0,0]]},
                      {'stages':[[0,0,0,0,0,-241]]},{'lowered_hands_reference_offset_us':[0,-139,0,0,0,240]}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)
        q=copy.deepcopy(p);q['previous_off_state']['pulse_us'][1]+=1
        with self.assertRaises(ValueError):linkage.validate_plan(q)

    def test_fast_guard_uses_only_reviewed_paths_and_finishes_low(self):
        p=self.low_guard_plan(continued=True)
        p.update(low_guard_performance=True,tempo_step_us=8,peak_hold_ms=100,
                 low_guard_geometry_receipt_sha256=linkage.LOW_GUARD_GEOMETRY_RECEIPT)
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();before=self.now;self.d.probe(3,self.emit,self.sleep)
        self.assertLess(self.now-before,2.4)
        previous=p['expected_pulses_us']
        for r in self.events:
            if r['event']!='probe_step':continue
            values=r['state']['pulse_us'];self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,values)),8)
            self.assertTrue(1212<=values[1]<=1352 and 1500<=values[5]<=1740)
            for i in (0,2,3,4,6,7,8,9):self.assertEqual(values[i],p['expected_pulses_us'][i])
            previous=values
        self.assertEqual(self.d.pulses,p['expected_pulses_us'])
        for extra in ({'low_guard_geometry_receipt_sha256':'0'*64},
                      {'low_guard_performance':False},{'tempo_step_us':3},
                      {'stages':[[0,100,0,0,0,0]]}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)

    def test_low_hand_head_lift_is_exclusive_and_returns_to_inspected_pose(self):
        p=self.low_guard_plan(continued=True)
        for key in ('low_guard_diagnostic','supported_martial_diagnostic','bilateral_hand_diagnostic'):p.pop(key)
        p.update(head_support_diagnostic=True,lowered_head_support_diagnostic=True,
                 stages=[[0,0,0,-80,0,0]],demo_stages=[1])
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();self.d.probe(1,self.emit,self.sleep)
        previous=p['expected_pulses_us']
        states=[r['state']['pulse_us'] for r in self.events if r['event']=='probe_step']
        self.assertEqual(min(r[3] for r in states),1434)
        for values in states:
            self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,values)),3)
            for i in (0,1,2,4,5,6,7,8,9):self.assertEqual(values[i],p['expected_pulses_us'][i])
            previous=values
        self.assertEqual(self.d.pulses,p['expected_pulses_us'])
        for extra in ({'tempo_step_us':8},{'lowered_head_support_diagnostic':False},
                      {'stages':[[0,0,0,-81,0,0]]},{'stages':[[0,1,0,-20,0,0]]}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)

    def test_low_guard_head_follow_commits_rods_together_and_returns_low(self):
        p=self.low_guard_plan(continued=True)
        p.update(low_guard_head_follow=True,head_follow_receipt_sha256=linkage.LOW_HEAD_FOLLOW_RECEIPT,
                 stages=[list(v) for v in linkage.LOW_HEAD_FOLLOW_PATHS],demo_stages=[1,2,3,4])
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();self.d.probe(4,self.emit,self.sleep)
        previous=p['expected_pulses_us'];simultaneous=False
        for r in self.events:
            if r['event']!='probe_step':continue
            values=r['state']['pulse_us'];self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,values)),3)
            simultaneous |= all(values[i]!=previous[i] for i in (1,3,5))
            self.assertTrue(1474<=values[3]<=1514)
            for i in (0,2,4,6,7,8,9):self.assertEqual(values[i],p['expected_pulses_us'][i])
            previous=values
        self.assertTrue(simultaneous);self.assertEqual(self.d.pulses,p['expected_pulses_us'])
        for extra in ({'tempo_step_us':8},{'low_guard_head_follow':False},
                      {'head_follow_receipt_sha256':'0'*64},
                      {'stages':[[0,140,0,-41,0,-240]]},{'stages':[[0,100,0,-40,0,-240]]}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)

    def test_fast_head_follow_needs_combined_geometry_and_retains_static_axes(self):
        p=self.low_guard_plan(continued=True)
        p.update(low_guard_head_follow=True,head_follow_receipt_sha256=linkage.LOW_HEAD_FOLLOW_RECEIPT,
                 low_guard_head_follow_performance=True,head_follow_geometry_receipt_sha256=linkage.HEAD_FOLLOW_GEOMETRY_RECEIPT,
                 tempo_step_us=8,peak_hold_ms=400,stages=[list(v) for v in linkage.LOW_HEAD_FOLLOW_PATHS],demo_stages=[2,3,4])
        self.d=linkage.LinkageSession(self.reg,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        self.resume();self.d.probe(4,self.emit,self.sleep)
        previous=p['expected_pulses_us']
        for r in self.events:
            if r['event']!='probe_step':continue
            values=r['state']['pulse_us'];self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,values)),8)
            for i in (0,2,4,6,7,8,9):self.assertEqual(values[i],p['expected_pulses_us'][i])
            previous=values
        self.assertEqual(self.d.pulses,p['expected_pulses_us'])
        for extra in ({'head_follow_geometry_receipt_sha256':'0'*64},{'peak_hold_ms':100},
                      {'low_guard_head_follow_performance':False},{'stages':[[0,140,0,-60,0,-240]]}):
            q=copy.deepcopy(p);q.update(extra)
            with self.assertRaises(ValueError):linkage.validate_plan(q)

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
