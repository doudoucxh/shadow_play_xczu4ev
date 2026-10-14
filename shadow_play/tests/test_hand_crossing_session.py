import copy,hashlib,json
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import hand_crossing_session as h
from test_servo_commissioning import FakeRegisters

class Host:
    action=None
    def check(self):pass

class CrossingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.lock=root/'lock';self.lock.write_text('incident')
        self.boot=root/'boot';self.boot_id='11111111-2222-3333-4444-555555555555';self.boot.write_text(self.boot_id)
        self.marker=root/'image';self.marker.write_text(json.dumps({'sha256':h.IMAGE_SHA}))
        self.now=0;self.host=Host();self.r=FakeRegisters()
        for i in range(10):self.r.values[0x80+4*i]=1500
        off=dict(sequence=31666,pulse_us=h.BASE,enabled_mask=0,armed=False,pending=False,faults=0)
        source=[dict(event='reference_held',profile='person-tiger-duet',route_sha256=h.DUET_SHA)]
        source += [dict(event='path_reviewed',axis=i) for i in range(1,7)]
        source += [dict(event='route_cycle_complete',cycle=i) for i in range(1,4)]
        source += [dict(event='outputs_off',normal_frame_stop=True,state=off)]
        self.raw='\n'.join(json.dumps(r) for r in source).encode()
        self.p=dict(approval=h.c.APPROVAL,session_id='cross-test',profile='person-overhead-map-positive',
         expected_sequence=0,expected_pulses_us=[1500]*10,observer_ready=True,operator_hardware_unmoved=True,
         dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000000,duration_seconds=120,tempo_step_us=3,
         repetitions=1,boot_id=self.boot_id,restore_after_power_cycle=True,
         baseline_source=dict(path='/tmp/puppet-choreography-prior.jsonl',sha256=hashlib.sha256(self.raw).hexdigest()))

    def device(self):
        return h.CrossingSession(self.r,self.p,self.host,motion_inhibit_paths=[self.lock],cancel_path=self.lock.with_name('cancel'),
          clock=lambda:self.now,wall=lambda:1000,read=getattr(self,'reader',lambda p:self.raw),boot_id_path=self.boot,image_marker=self.marker)

    def sleep(self,t):self.now+=t

    def prepare_fast(self,profile='person-script-double-hit-probe'):
        off=dict(sequence=100,pulse_us=h.BASE,enabled_mask=0,armed=False,pending=False,faults=0)
        rows=[dict(event='reference_held',profile=profile,route_sha256=h.digest(profile),tempo_step_us=3)]
        for i in range(1,7):
            rows.extend((dict(event='probe_complete',axis=i),dict(event='path_reviewed',axis=i)))
        rows.append(dict(event='outputs_off',normal_frame_stop=True,state=off))
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        spec=dict(path='/tmp/puppet-choreography-slow-gesture.jsonl',sha256=hashlib.sha256(self.raw).hexdigest())
        self.p.update(profile=profile,restore_after_power_cycle=False,tempo_step_us=8,
                      expected_sequence=100,expected_pulses_us=h.BASE[:],baseline_source=spec,
                      prior_slow_route_log=copy.deepcopy(spec))
        self.p.pop('prior_high_route_log',None);self.reader=lambda path:self.raw
        if profile in h.OVERHEAD_WIDER_PROFILES:
            high=copy.deepcopy(rows);high[0].update(profile='person-overhead-high280-yaw80-probe',
                                                 route_sha256=h.digest('person-overhead-high280-yaw80-probe'))
            high_raw='\n'.join(json.dumps(r) for r in high).encode();high_path='/tmp/puppet-choreography-prior-high.jsonl'
            self.p['prior_high_route_log']=dict(path=high_path,sha256=hashlib.sha256(high_raw).hexdigest())
            self.reader=lambda path:high_raw if path==high_path else self.raw
        self.p.pop('execution_mode',None)
        if profile in h.OPERATOR_ARC_PROFILES:
            self.p['execution_mode']='operator-attended-one-arc-trial';self.p.pop('prior_slow_route_log',None)
        self.r.values[0x20]=100
        for i,v in enumerate(h.BASE):self.r.values[0x80+4*i]=v

    def test_fast_gesture_requires_same_slow_route_and_no_power_cycle(self):
        self.prepare_fast();original=copy.deepcopy(self.p)
        for change in ({'restore_after_power_cycle':True}, {'profile':'person-overhead-map-positive'},
                       {'profile':'person-script-hand-b-strike-probe'}, {'tempo_step_us':9},
                       {'prior_slow_route_log':dict(original['prior_slow_route_log'],sha256='0'*64)}):
            self.p=copy.deepcopy(original);self.p.update(change)
            with self.assertRaises(ValueError):self.device()
            self.assertEqual(self.r.writes,[])
        self.p=copy.deepcopy(original);del self.p['prior_slow_route_log']
        with self.assertRaises(ValueError):self.device()
        self.assertEqual(self.r.writes,[])

    def test_incomplete_or_unclosed_slow_gesture_cannot_enable_fast_motion(self):
        self.prepare_fast();original_raw=self.raw;original=copy.deepcopy(self.p)
        for mutation in ('missing_review','wrong_route','wrong_tempo','not_off','missing_edge'):
            rows=[json.loads(r) for r in original_raw.splitlines()]
            if mutation=='missing_review':rows=[r for r in rows if not (r['event']=='path_reviewed' and r['axis']==6)]
            elif mutation=='wrong_route':rows[0]['route_sha256']='0'*64
            elif mutation=='wrong_tempo':rows[0]['tempo_step_us']=8
            elif mutation=='not_off':rows[-1]['state']['enabled_mask']=63
            else:rows=[r for r in rows if not (r['event']=='probe_complete' and r['axis']==6)]
            self.raw='\n'.join(json.dumps(r) for r in rows).encode();self.p=copy.deepcopy(original)
            for key in ('baseline_source','prior_slow_route_log'):
                self.p[key]['sha256']=hashlib.sha256(self.raw).hexdigest()
            with self.assertRaises(ValueError):self.device()
            self.assertEqual(self.r.writes,[])

    def test_fast_same_gestures_preserve_axes_and_never_catch_up(self):
        for profile in sorted(h.FAST_GESTURE_PROFILES):
            self.now=0;self.r=FakeRegisters();self.prepare_fast(profile);d=self.device()
            d.adopt(h.BASE[:]);events=[]
            def emit(e):events.append(dict(e,time=self.now))
            for n in range(1,7):d.advance(n,emit,self.sleep)
            prior=h.BASE[:];last=0
            for e in events:
                if e['event']!='probe_step':continue
                s=e['state'];self.assertEqual(s['enabled_mask'],63)
                for i in (0,2,4,6,7,8,9):self.assertEqual(s['pulse_us'][i],h.BASE[i])
                self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,s['pulse_us'])),8)
                self.assertGreaterEqual(e['time']-last,.02-1e-9)
                prior=s['pulse_us'];last=e['time']
            self.assertEqual(d.pulses,h.BASE)
            self.assertEqual(self.lock.read_text(),'incident')
            d.demo_used=True
            with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):d.check()

    def test_new_drop_geometry_cannot_use_old_double_route_receipt(self):
        self.prepare_fast();self.p['profile']='person-script-double-drop-sync-probe'
        with self.assertRaisesRegex(ValueError,'same complete slow gesture'):self.device()
        self.assertEqual(self.r.writes,[])
        old=h.ROUTES['person-script-double-hit-probe'];new=h.ROUTES[self.p['profile']]
        for vector in new:
            for axis,value in enumerate(vector):
                self.assertGreaterEqual(value,min(v[axis] for v in old))
                self.assertLessEqual(value,max(v[axis] for v in old))

    def test_restore_uses_observed_reference_not_reset_registers_and_keeps_tiger_off(self):
        d=self.device();state=d.adopt([1500]*10)
        self.assertEqual(state['pulse_us'],h.BASE);self.assertEqual(state['enabled_mask'],63)
        self.assertEqual(state['pulse_us'][6:],[1500]*4)
        self.assertEqual(self.lock.read_text(),'incident')

    def test_fixed_paths_preserve_unrelated_axes_keep_tiger_off_and_return(self):
        for profile in h.ROUTES:
            if profile in h.OPERATOR_ARC_PROFILES:continue
            self.now=0;self.r=FakeRegisters()
            for i in range(10):self.r.values[0x80+4*i]=1500
            if profile in (h.SLOW_DIAGNOSTIC_PROFILES|h.CONTINUOUS_PRESENTATION_PROFILES):
                self.prepare_fast(profile);self.p['tempo_step_us']=3;del self.p['prior_slow_route_log']
                d=self.device();d.adopt(h.BASE[:])
            else:
                self.p.update(profile=profile,restore_after_power_cycle=True,tempo_step_us=3,
                              expected_sequence=0,expected_pulses_us=[1500]*10)
                # Restore the completed original-duet fixture after a continuation.
                self.set_restore_source();d=self.device();d.adopt([1500]*10)
            events=[]
            for n in range(1,7):d.advance(n,events.append,self.sleep)
            prior=h.BASE
            for e in events:
                if e['event']!='probe_step':continue
                s=e['state'];self.assertEqual(s['enabled_mask'],63)
                if profile.startswith('person-script-') or profile in h.CONTINUOUS_PRESENTATION_PROFILES:
                    self.assertEqual(s['pulse_us'][6:],h.BASE[6:])
                    fixed=((1,2,4,5) if profile in h.HAND_A_YAW_PROFILES else
                           (0,1,2,5) if profile in h.SLOW_YAW_PROFILES else
                           ((0,1,2) if profile in h.SLOW_DIAGNOSTIC_PROFILES else (0,2,4)))
                    for i in fixed:self.assertEqual(s['pulse_us'][i],h.BASE[i])
                    if profile=='person-script-hand-b-strike-probe':
                        self.assertEqual(s['pulse_us'][1],h.BASE[1])
                else:self.assertEqual(s['pulse_us'][4:],h.BASE[4:])
                self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,s['pulse_us'])),3)
                prior=s['pulse_us']
            self.assertEqual(d.pulses,h.BASE)

    def set_restore_source(self):
        self.p.pop('prior_high_route_log',None)
        off=dict(sequence=31666,pulse_us=h.BASE,enabled_mask=0,armed=False,pending=False,faults=0)
        rows=[dict(event='reference_held',profile='person-tiger-duet',route_sha256=h.DUET_SHA)]
        rows += [dict(event='path_reviewed',axis=i) for i in range(1,7)]
        rows += [dict(event='route_cycle_complete',cycle=i) for i in range(1,4)]
        rows += [dict(event='outputs_off',normal_frame_stop=True,state=off)]
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        self.p['baseline_source']=dict(path='/tmp/puppet-choreography-prior.jsonl',sha256=hashlib.sha256(self.raw).hexdigest())

    def test_local_hand_b_yaw_has_no_fast_or_power_cycle_mode(self):
        for profile in h.SLOW_DIAGNOSTIC_PROFILES:
            self.prepare_fast(profile)
            with self.assertRaises(ValueError):self.device()
            self.p['tempo_step_us']=3;del self.p['prior_slow_route_log']
            self.p['restore_after_power_cycle']=True
            with self.assertRaises(ValueError):self.device()
            self.assertEqual(self.r.writes,[])

    def test_second_inward_level_requires_local_yaw_evidence(self):
        self.prepare_fast('person-script-hand-b-strike-probe')
        self.p.update(profile='person-script-hand-b-inward-80-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed local hand-B yaw review'):self.device()
        self.assertEqual(self.r.writes,[])

    def test_combined_fold_requires_local_yaw_evidence(self):
        self.prepare_fast('person-script-hand-b-strike-probe')
        self.p.update(profile='person-script-hand-b-inward-fold-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed local hand-B yaw review'):self.device()
        self.assertEqual(self.r.writes,[])

    def test_other_hand_receipt_does_not_satisfy_hand_b_specific_progression(self):
        for profile in ('person-script-hand-b-inward-80-probe','person-script-hand-b-inward-fold-probe'):
            self.prepare_fast('person-script-hand-a-local-yaw-probe')
            self.p.update(profile=profile,tempo_step_us=3)
            del self.p['prior_slow_route_log']
            with self.assertRaisesRegex(ValueError,'completed local hand-B yaw review'):self.device()
            self.assertEqual(self.r.writes,[])

    def test_hand_a_second_level_cannot_use_hand_b_motion_receipt(self):
        self.prepare_fast('person-script-hand-b-local-yaw-probe')
        self.p.update(profile='person-script-hand-a-inward-80-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed local hand-A yaw review'):self.device()
        self.assertEqual(self.r.writes,[])

    def test_reference_presentation_has_fixed_yaw_and_explicit_phase_order(self):
        route=h.ROUTES['person-reference-guard-counter-probe']
        self.assertEqual(route[1],(0,0,0,-40,0,0))
        self.assertEqual(route[2],(0,70,0,-40,0,0))
        self.assertEqual(route[3],(0,140,0,-40,0,-240))
        self.assertEqual(route[4],(0,0,0,-40,0,-120))
        self.assertTrue(all(v[0]==v[2]==v[4]==0 for v in route))
        self.prepare_fast('person-reference-guard-counter-probe')
        self.p.update(tempo_step_us=3,restore_after_power_cycle=True)
        del self.p['prior_slow_route_log']
        with self.assertRaises(ValueError):self.device()
        self.assertEqual(self.r.writes,[])

    def test_additional_lift_needs_its_own_prior_lift_and_cannot_replay(self):
        self.prepare_fast('person-reference-guard-counter-probe')
        self.p.update(profile='person-overhead-lift-280-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed 210-us lift review'):self.device()
        self.assertEqual(self.r.writes,[])
        self.prepare_fast('person-overhead-lift-clearance')
        self.p.update(profile='person-overhead-lift-280-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        d=self.device();d.adopt(h.BASE[:]);events=[]
        for stage in range(1,7):d.advance(stage,events.append,self.sleep)
        self.assertEqual(d.pulses,h.BASE)
        self.assertEqual(self.lock.read_text(),'incident')
        self.assertEqual(max(r['state']['pulse_us'][1] for r in events),h.BASE[1]+280)
        d.completed=d.reviewed=set(range(1,7));d.demo_used=True
        with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):d.check()

    def test_body_clearance_cannot_start_from_unreviewed_lift(self):
        self.prepare_fast('person-overhead-lift-clearance')
        self.p.update(profile='person-overhead-body-clearance-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed 280-us lift review'):self.device()
        self.assertEqual(self.r.writes,[])
        route=h.ROUTES['person-overhead-body-clearance-probe']
        self.assertEqual(route[2][1],route[3][1])
        self.assertEqual(route[3][3],0)
        self.assertTrue(all(v[0]==v[2]==v[4]==v[5]==0 for v in route))

    def test_high_lateral_approach_requires_body_review_and_keeps_other_supports_fixed(self):
        self.prepare_fast('person-overhead-lift-280-probe')
        self.p.update(profile='person-overhead-high280-yaw80-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed overhead body review'):self.device()
        self.assertEqual(self.r.writes,[])
        self.prepare_fast('person-overhead-body-clearance-probe')
        self.p.update(profile='person-overhead-high280-yaw80-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        d=self.device();d.adopt(h.BASE[:]);events=[]
        for stage in range(1,7):d.advance(stage,events.append,self.sleep)
        for event in events:
            if event['event']=='probe_step':self.assertEqual(event['state']['pulse_us'][2:],h.BASE[2:])
        self.assertEqual(d.pulses,h.BASE)
        d.completed=d.reviewed=set(range(1,7));d.demo_used=True
        with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):d.check()
        self.assertEqual(self.lock.read_text(),'incident')

    def test_wider_high_approach_needs_high_receipt_and_stays_diagnostic(self):
        self.prepare_fast('person-overhead-high280-yaw160-probe')
        self.p['tempo_step_us']=3;del self.p['prior_slow_route_log']
        receipt=self.p.pop('prior_high_route_log')
        with self.assertRaisesRegex(ValueError,'explicit prior high-route'):self.device()
        self.assertEqual(self.r.writes,[])
        self.p['prior_high_route_log']=dict(receipt,sha256='0'*64)
        with self.assertRaises(ValueError):self.device()
        self.assertEqual(self.r.writes,[])
        self.p['prior_high_route_log']=receipt
        d=self.device();d.adopt(h.BASE[:]);events=[]
        for stage in range(1,7):d.advance(stage,events.append,self.sleep)
        for event in events:
            if event['event']=='probe_step':self.assertEqual(event['state']['pulse_us'][2:],h.BASE[2:])
        self.assertEqual(d.pulses,h.BASE)
        d.completed=d.reviewed=set(range(1,7));d.demo_used=True
        with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):d.check()

    def test_arc_entry_requires_high160_and_changes_only_pitch_at_its_new_edge(self):
        self.prepare_fast('person-script-hand-a-local-yaw-probe')
        self.p.update(profile='person-overhead-arc-entry-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log']
        with self.assertRaisesRegex(ValueError,'completed high-160'):self.device()
        self.assertEqual(self.r.writes,[])
        route=h.ROUTES['person-overhead-arc-entry-probe']
        self.assertEqual(route[2][0],route[3][0]);self.assertEqual(route[2][1]-route[3][1],70)
        self.prepare_fast('person-overhead-arc-entry-probe');self.p['tempo_step_us']=3
        del self.p['prior_slow_route_log'];d=self.device();d.adopt(h.BASE[:]);events=[]
        for stage in range(1,7):d.advance(stage,events.append,self.sleep)
        for event in events:
            if event['event']=='probe_step':self.assertEqual(event['state']['pulse_us'][2:],h.BASE[2:])
        self.assertEqual(d.pulses,h.BASE)
        d.completed=d.reviewed=set(range(1,7));d.demo_used=True
        with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):d.check()

    def test_expired_session_final_review_can_only_bind_completed_original_reference(self):
        self.prepare_fast('person-overhead-high280-yaw160-probe')
        self.p.update(profile='person-overhead-arc-entry-probe',tempo_step_us=3)
        del self.p['prior_slow_route_log'];del self.p['prior_high_route_log']
        rows=[json.loads(r) for r in self.raw.splitlines()]
        rows=[r for r in rows if not (r['event']=='path_reviewed' and r['axis']==6)]
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        self.p['baseline_source']['sha256']=hashlib.sha256(self.raw).hexdigest()
        record=dict(event='post_stop_closure_review',reviewed_stage=6,source_log_sha256=self.p['baseline_source']['sha256'],
                    boot_id=self.boot_id,state=rows[-1]['state'],fresh_dual_view_reviewed=True,reviewed_at_unix_ms=1000000,
                    views={c:dict(frame_id=c+'-new',jpeg_sha256='a'*64) for c in ('front','top')})
        def bind(value):
            proof=json.dumps(value).encode();path='/tmp/puppet-choreography-closure.jsonl'
            self.p['post_stop_closure_review']=dict(path=path,sha256=hashlib.sha256(proof).hexdigest())
            self.reader=lambda p:proof if p==path else self.raw
        bind(record);self.device();self.assertEqual(self.r.writes,[])
        for key,value in (('reviewed_stage',5),('source_log_sha256','b'*64),('reviewed_at_unix_ms',800000),('fresh_dual_view_reviewed',False)):
            bad=copy.deepcopy(record);bad[key]=value;bind(bad)
            with self.assertRaises(ValueError):self.device()
            self.assertEqual(self.r.writes,[])

    def test_operator_trial_is_single_triggered_keeps_other_axes_and_never_fakes_review(self):
        self.prepare_fast('person-overhead-operator-arc-trial');d=self.device();events=[]
        def emit(row):
            events.append(row)
            if row['event']=='reference_held':self.host.action=('demo',row['state']['sequence'])
        h.run_operator_arc_trial(d,emit,self.sleep)
        self.assertEqual(sum(r['event']=='operator_trial_complete' for r in events),1)
        self.assertFalse(any(r['event']=='path_reviewed' for r in events))
        self.assertEqual([r['axis'] for r in events if r['event']=='probe_complete'],list(range(1,7)))
        for row in events:
            if row['event']=='probe_step':self.assertEqual(row['state']['pulse_us'][2:],h.BASE[2:])
        self.assertEqual(events[-1]['state']['enabled_mask'],0);self.assertEqual(events[-1]['state']['pulse_us'],h.BASE)
        self.assertEqual(self.lock.read_text(),'incident')
        self.prepare_fast('person-overhead-operator-arc-trial');self.p.pop('execution_mode')
        before=len(self.r.writes)
        with self.assertRaises(ValueError):self.device()
        self.assertEqual(len(self.r.writes),before)

    def test_focused_jump_trial_slows_pitch_edges_without_changing_geometry(self):
        self.prepare_fast('person-overhead-operator-jump-slow-trial');events=[]
        h.run_operator_arc_trial(self.device(),events.append,self.sleep)
        self.assertEqual(h.ROUTES[self.p['profile']],h.ROUTES['person-overhead-operator-balanced-arc-trial'])
        self.assertEqual([r['axis'] for r in events if r['event']=='focused_slow_stage_started'],[3,4,6])
        previous=h.BASE[:]
        for row in events:
            if row['event']!='probe_step':continue
            limit=1 if row['axis'] in (3,4,6) else 8
            self.assertLessEqual(max(abs(a-b) for a,b in zip(previous,row['state']['pulse_us'])),limit)
            self.assertEqual(row['state']['pulse_us'][2:],h.BASE[2:]);previous=row['state']['pulse_us']
        self.assertGreater(self.now,15)
        self.assertEqual(events[-1]['state']['enabled_mask'],0)
        self.assertEqual(self.lock.read_text(),'incident')

    def test_new_return_moves_outward_and_down_together_with_slow_steps(self):
        self.prepare_fast('person-overhead-operator-return-arc-trial');events=[]
        h.run_operator_arc_trial(self.device(),events.append,self.sleep)
        route=h.ROUTES[self.p['profile']]
        self.assertEqual(route[2][:2],(140,180));self.assertEqual(route[5][:2],(-80,80))
        diagonal=[r for r in events if r['event']=='probe_step' and r['axis']==5]
        self.assertTrue(any(r['state']['pulse_us'][0]<h.BASE[0] and r['state']['pulse_us'][1]<h.BASE[1]+160 for r in diagonal))
        prior=h.BASE[:]
        for row in events:
            if row['event']!='probe_step':continue
            self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,row['state']['pulse_us'])),1 if row['axis'] in (3,4,5,6) else 8)
            self.assertEqual(row['state']['pulse_us'][2:],h.BASE[2:]);prior=row['state']['pulse_us']
        self.assertEqual(events[-1]['state']['pulse_us'],h.BASE);self.assertEqual(events[-1]['state']['enabled_mask'],0)

    def test_reference_sequence_exception_only_accepts_an_unchanged_static_hold(self):
        self.prepare_fast('person-overhead-operator-arc-trial')
        rows=[json.loads(r) for r in self.raw.splitlines()]
        state=dict(rows[-1]['state'],sequence=101,enabled_mask=63,armed=True)
        holds=[dict(event='reference_held',profile='person-overhead-operator-arc-trial',
                    route_sha256=h.digest('person-overhead-operator-arc-trial'),state=state)]
        def bind(values):
            raw=json.dumps(values[0]).encode();path='/tmp/puppet-choreography-static-hold.jsonl'
            self.p['held_reference_log']=dict(path=path,sha256=hashlib.sha256(raw).hexdigest())
            return lambda p:raw if p==path else self.raw
        self.assertEqual(h.reference_sequence(self.p,rows,bind(holds)),101)
        bad=copy.deepcopy(holds);bad[0]['event']='probe_started'
        with self.assertRaises(ValueError):h.reference_sequence(self.p,rows,bind(bad))
        bad=copy.deepcopy(holds);bad[0]['state']['pulse_us'][0]+=8
        with self.assertRaises(ValueError):h.reference_sequence(self.p,rows,bind(bad))

    def test_closed_operator_trial_can_continue_lower_without_fabricating_reviews(self):
        self.prepare_fast('person-overhead-operator-arc-trial');events=[]
        h.run_operator_arc_trial(self.device(),events.append,self.sleep)
        self.assertTrue(h.closed_operator_reference(events))
        for defect in ('missing_stage','other_axis','fault'):
            bad=copy.deepcopy(events)
            if defect=='missing_stage':bad=[r for r in bad if not (r['event']=='probe_complete' and r['axis']==3)]
            elif defect=='other_axis':bad[2]['state']['pulse_us'][4]+=1
            else:bad[-1]['state']['faults']=2
            with self.assertRaises(ValueError):h.closed_operator_reference(bad)
        self.raw='\n'.join(json.dumps(r) for r in events).encode()
        self.p.update(profile='person-overhead-operator-low-arc-trial',expected_sequence=events[-1]['state']['sequence'])
        self.p['baseline_source']['sha256']=hashlib.sha256(self.raw).hexdigest()
        lower_events=[];h.run_operator_arc_trial(self.device(),lower_events.append,self.sleep)
        lower=h.ROUTES[self.p['profile']]
        self.assertEqual(max(v[1] for v in lower),180)
        self.assertEqual(max(v[0] for v in lower),320)
        self.assertFalse(any(r['event']=='path_reviewed' for r in lower_events))
        self.assertEqual(lower_events[-1]['state']['pulse_us'],h.BASE)
        self.assertEqual(lower_events[-1]['state']['enabled_mask'],0)

    def test_only_new_frontal_gesture_after_slow_and_fast_review_can_present_once(self):
        self.prepare_fast('person-reference-guard-counter-probe');d=self.device()
        d.adopt(h.BASE[:]);events=[]
        for stage in range(1,7):d.advance(stage,events.append,self.sleep)
        # Completed movement alone is insufficient; visual reviews are distinct.
        d.demo_used=True
        with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):d.check()
        self.now=0;self.r=FakeRegisters();self.prepare_fast('person-reference-guard-counter-probe')
        d=self.device();self.host.action=None;events=[]
        def emit(row):
            events.append(row)
            event=row['event'];seq=row['state']['sequence']
            if event=='reference_held':self.host.action=('probe_1',seq)
            elif event=='probe_complete' and not d.demo_used:self.host.action=('review_'+str(row['axis']),seq)
            elif event=='path_reviewed':
                self.host.action=(('probe_'+str(row['axis']+1)) if row['axis']<6 else 'demo',seq)
            elif event=='demo_complete':self.host.action=('finish',seq)
        h.c.run_session(d,emit,sleep=self.sleep)
        self.assertEqual(sum(e['event']=='demo_started' for e in events),1)
        self.assertEqual(sum(e['event']=='demo_complete' for e in events),1)
        self.assertEqual(events[-1]['event'],'outputs_off')
        self.assertEqual(events[-1]['state']['enabled_mask'],0)
        self.assertEqual(events[-1]['state']['pulse_us'],h.BASE)
        self.assertEqual(self.lock.read_text(),'incident')

    def test_occluded_support_prefix_resumes_only_that_current_pose_and_requires_review(self):
        profile='person-reference-guard-counter-probe';self.prepare_fast(profile)
        self.p['tempo_step_us']=3;del self.p['prior_slow_route_log'];baseline_raw=self.raw
        device=self.device();held=device.adopt(h.BASE[:])
        rows=[dict(event='reference_held',profile=profile,route_sha256=h.digest(profile),tempo_step_us=3,state=held)]
        device.advance(1,rows.append,self.sleep)
        rows.append(dict(event='outputs_off',normal_frame_stop=True,state=device.stop_after_frame()))
        prefix_raw='\n'.join(json.dumps(row) for row in rows).encode()
        prefix=dict(path='/tmp/puppet-choreography-support-prefix.jsonl',sha256=hashlib.sha256(prefix_raw).hexdigest())
        self.p.update(expected_sequence=rows[-1]['state']['sequence'],expected_pulses_us=rows[-1]['state']['pulse_us'],
                      resume_waypoint=1,resume_route_log=prefix)
        baseline_path=self.p['baseline_source']['path']
        self.reader=lambda path:baseline_raw if path==baseline_path else prefix_raw
        before=len(self.r.writes);resumed=self.device()
        self.assertEqual(len(self.r.writes),before)
        self.assertEqual(resumed.cursor,1);self.assertEqual(resumed.completed,{1});self.assertEqual(resumed.reviewed,set())
        resumed.adopt(self.p['expected_pulses_us'][:]);resumed.reviewed.add(1)
        for stage in range(2,7):resumed.advance(stage,lambda r:None,self.sleep)
        self.assertEqual(resumed.pulses,h.BASE);self.assertEqual(self.lock.read_text(),'incident')
        original=copy.deepcopy(self.p)
        for changes in ({'tempo_step_us':8},{'resume_waypoint':2},{'profile':'person-script-hand-a-local-yaw-probe'},
                        {'expected_sequence':original['expected_sequence']+1},{'expected_pulses_us':h.BASE[:]},
                        {'resume_route_log':dict(prefix,sha256='0'*64)}):
            self.p=copy.deepcopy(original);self.p.update(changes);before=len(self.r.writes)
            with self.assertRaises(ValueError):self.device()
            self.assertEqual(len(self.r.writes),before)

    def test_source_tamper_and_boot_change_reject_before_arm(self):
        self.raw+=b' '
        with self.assertRaises(ValueError):self.device()
        self.raw=self.raw[:-1];d=self.device();self.boot.write_text('different-boot')
        with self.assertRaises(RuntimeError):d.adopt([1500]*10)
        self.assertEqual(self.r.writes,[])

    def test_reviewed_mapping_cannot_be_replayed_as_a_validated_demonstration(self):
        d=self.device();d.completed=set(range(1,7));d.reviewed=d.completed.copy();d.cursor=6
        self.host.action=('demo',1);events=[]
        with self.assertRaisesRegex(RuntimeError,'diagnostic-only'):
            h.c.run_session(d,events.append,sleep=self.sleep)
        self.assertEqual(sum(offset==0x18 and value==0x434f4d54 for offset,value in self.r.writes),1)
        self.assertEqual(events[-1]['event'],'outputs_off')
        self.assertFalse(events[-1]['state']['armed'])
        self.assertEqual(events[-1]['state']['pulse_us'],h.BASE)

if __name__=='__main__':unittest.main()
