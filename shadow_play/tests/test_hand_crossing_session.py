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
          clock=lambda:self.now,wall=lambda:1000,read=lambda p:self.raw,boot_id_path=self.boot,image_marker=self.marker)

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

    def test_restore_uses_observed_reference_not_reset_registers_and_keeps_tiger_off(self):
        d=self.device();state=d.adopt([1500]*10)
        self.assertEqual(state['pulse_us'],h.BASE);self.assertEqual(state['enabled_mask'],63)
        self.assertEqual(state['pulse_us'][6:],[1500]*4)
        self.assertEqual(self.lock.read_text(),'incident')

    def test_fixed_paths_preserve_unrelated_axes_keep_tiger_off_and_return(self):
        for profile in h.ROUTES:
            self.now=0;self.r=FakeRegisters()
            for i in range(10):self.r.values[0x80+4*i]=1500
            self.p['profile']=profile;d=self.device();d.adopt([1500]*10);events=[]
            for n in range(1,7):d.advance(n,events.append,self.sleep)
            prior=h.BASE
            for e in events:
                if e['event']!='probe_step':continue
                s=e['state'];self.assertEqual(s['enabled_mask'],63)
                if profile.startswith('person-script-'):
                    self.assertEqual(s['pulse_us'][6:],h.BASE[6:])
                    for i in (0,2,4):self.assertEqual(s['pulse_us'][i],h.BASE[i])
                    if profile=='person-script-hand-b-strike-probe':
                        self.assertEqual(s['pulse_us'][1],h.BASE[1])
                else:self.assertEqual(s['pulse_us'][4:],h.BASE[4:])
                self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,s['pulse_us'])),3)
                prior=s['pulse_us']
            self.assertEqual(d.pulses,h.BASE)

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
