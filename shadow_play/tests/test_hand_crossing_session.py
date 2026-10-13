import hashlib,json
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

    def test_restore_uses_observed_reference_not_reset_registers_and_keeps_tiger_off(self):
        d=self.device();state=d.adopt([1500]*10)
        self.assertEqual(state['pulse_us'],h.BASE);self.assertEqual(state['enabled_mask'],63)
        self.assertEqual(state['pulse_us'][6:],[1500]*4)
        self.assertEqual(self.lock.read_text(),'incident')

    def test_both_direction_paths_keep_other_hand_and_tiger_static_and_return(self):
        for profile in h.ROUTES:
            self.now=0;self.r=FakeRegisters()
            for i in range(10):self.r.values[0x80+4*i]=1500
            self.p['profile']=profile;d=self.device();d.adopt([1500]*10);events=[]
            for n in range(1,7):d.advance(n,events.append,self.sleep)
            prior=h.BASE
            for e in events:
                if e['event']!='probe_step':continue
                s=e['state'];self.assertEqual(s['enabled_mask'],63)
                self.assertEqual(s['pulse_us'][4:],h.BASE[4:])
                self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,s['pulse_us'])),3)
                prior=s['pulse_us']
            self.assertEqual(d.pulses,h.BASE)

    def test_source_tamper_and_boot_change_reject_before_arm(self):
        self.raw+=b' '
        with self.assertRaises(ValueError):self.device()
        self.raw=self.raw[:-1];d=self.device();self.boot.write_text('different-boot')
        with self.assertRaises(RuntimeError):d.adopt([1500]*10)
        self.assertEqual(self.r.writes,[])

if __name__=='__main__':unittest.main()
