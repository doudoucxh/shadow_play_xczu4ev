import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_hip_inside_lift_probe as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device

class InsideTests(unittest.TestCase):
    def setUp(self):
        rows=[dict(event='reference_held'),dict(event='outputs_off',normal_frame_stop=False,
                 state=dict(sequence=43384,pulse_us=s.START,enabled_mask=0,armed=False,faults=0,pending=False))]
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        sha=hashlib.sha256(self.raw).hexdigest();p=patch.object(s,'SOURCE_SHA',sha);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=43384,
            expected_pulses_us=s.START,source_sha256=sha,route_sha256=s.ROUTE_SHA,boot_id=s.BOOT,
            duration_seconds=240,observer_ready=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000)
    def test_exact_start_and_no_jump(self):
        s.validate(self.plan,self.raw,lambda:1)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw+b' ')
        with self.assertRaises(ValueError):s.validate(dict(self.plan,expected_sequence=43383),self.raw)
        r=FakeRegisters();r.values[0x20]=43384
        for i,v in enumerate(s.START):r.values[0x80+i*4]=v
        with patch.object(s.OpeningProbe,'lock_hashes',return_value=('lock',)):
            d=s.OpeningProbe(r,self.plan,Mock(),source_raw=self.raw,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.TARGETS[1])
            self.assertEqual(r.writes,[]);self.assertEqual(d.adopt(s.START)['enabled_mask'],63);d.off()
    def test_only_hand_pair_changes(self):
        for q in s.FRAMES:self.assertEqual(q[2:],s.START[2:])
        self.assertLessEqual(max(abs(x-y) for a,b in zip(s.FRAMES,s.FRAMES[1:]) for x,y in zip(a,b)),1)
    def test_finish_first_does_not_execute_second(self):
        d=Device('full');d.pulses=s.START[:];events=[]
        with patch.object(s.m,'await_action'),patch.object(s,'reviewed_or_finish',return_value='finish'):s.run(d,events.append)
        self.assertEqual(d.pulses,s.TARGETS[1]);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(len([r for r in events if r['event']=='probe_step']),100)
    def test_inward_before_upward(self):
        d=Device('full');d.pulses=s.START[:];gates=[]
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)),patch.object(s,'reviewed_or_finish',side_effect=['review_1','review_2','review_3','finish']):s.run(d,lambda e:None)
        self.assertEqual(gates,['probe_'+str(i) for i in range(1,5)]);self.assertEqual(d.pulses,s.TARGETS[-1])
    def test_no_lift_before_inward_and_reject_prior_motion(self):
        self.assertEqual([q[1] for q in s.TARGETS[:3]],[1212]*3)
        self.assertEqual([q[0] for q in s.TARGETS[2:]],[1570]*3)
        rows=[json.loads(x) for x in self.raw.splitlines()];rows.insert(1,dict(event='probe_step'))
        raw='\n'.join(json.dumps(x) for x in rows).encode();sha=hashlib.sha256(raw).hexdigest()
        with patch.object(s,'SOURCE_SHA',sha),self.assertRaises(ValueError):s.validate(dict(self.plan,source_sha256=sha),raw)
if __name__=='__main__':unittest.main()
