import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_hip_support_probe as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device

class SupportTests(unittest.TestCase):
    def setUp(self):
        rows=[dict(event='probe_complete',axis=i) for i in [1,2]]
        rows += [dict(event='hip_arc_candidate_complete'),dict(event='outputs_off',normal_frame_stop=True,
                 state=dict(sequence=43181,pulse_us=s.START,enabled_mask=0,armed=False,faults=0,pending=False))]
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        sha=hashlib.sha256(self.raw).hexdigest();p=patch.object(s,'SOURCE_SHA',sha);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=43181,
            expected_pulses_us=s.START,source_sha256=sha,route_sha256=s.ROUTE_SHA,boot_id=s.BOOT,
            duration_seconds=240,observer_ready=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000)
    def test_exact_source_and_frames_required(self):
        s.validate(self.plan,self.raw,lambda:1)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw+b' ')
        with self.assertRaises(ValueError):s.validate(dict(self.plan,expected_sequence=43180),self.raw)
        r=FakeRegisters();r.values[0x20]=43181
        for i,v in enumerate(s.START):r.values[0x80+i*4]=v
        with patch.object(s.OpeningProbe,'lock_hashes',return_value=('lock',)):
            d=s.OpeningProbe(r,self.plan,Mock(),source_raw=self.raw,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.TARGETS[1])
            self.assertEqual(r.writes,[]);self.assertEqual(d.adopt(s.START)['enabled_mask'],63);d.off()
    def test_only_four_and_six_and_one_us_steps(self):
        for q in s.FRAMES:
            self.assertTrue(all(q[i]==s.START[i] for i in [0,1,2,4,6,7,8,9]))
        self.assertLessEqual(max(abs(x-y) for a,b in zip(s.FRAMES,s.FRAMES[1:]) for x,y in zip(a,b)),1)
    def test_finish_first_stops_before_other_levels(self):
        d=Device('full');d.pulses=s.START[:];events=[]
        with patch.object(s.m,'await_action'),patch.object(s,'reviewed_or_finish',return_value='finish'):s.run(d,events.append)
        self.assertEqual(d.pulses,s.TARGETS[1]);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(len([r for r in events if r['event']=='probe_step']),100)
    def test_each_support_stage_needs_gate(self):
        d=Device('full');d.pulses=s.START[:];gates=[]
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)),patch.object(s,'reviewed_or_finish',side_effect=['review_'+str(i) for i in range(1,6)]+['finish']):s.run(d,lambda e:None)
        self.assertEqual(gates,['probe_'+str(i) for i in range(1,7)]);self.assertEqual(d.pulses,s.START)
if __name__=='__main__':unittest.main()
