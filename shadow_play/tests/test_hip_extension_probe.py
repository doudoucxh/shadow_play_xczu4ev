import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_hip_extension_probe as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device

class ExtensionTests(unittest.TestCase):
    def setUp(self):
        rows=[dict(event='probe_complete',axis=i) for i in range(1,7)]
        rows += [dict(event='path_reviewed',axis=6),dict(event='hold_alive',awaiting='probe_7'),
                 dict(event='outputs_off',normal_frame_stop=False,state=dict(sequence=42797,pulse_us=s.START,enabled_mask=0,armed=False,faults=0,pending=False))]
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        sha=hashlib.sha256(self.raw).hexdigest();p=patch.object(s,'SOURCE_SHA',sha);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=42797,
            expected_pulses_us=s.START,source_sha256=sha,route_sha256=s.ROUTE_SHA,boot_id=s.BOOT,
            duration_seconds=120,observer_ready=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000)
    def test_exact_source_only_and_no_skipping(self):
        s.validate(self.plan,self.raw,lambda:1)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw+b' ')
        with self.assertRaises(ValueError):s.validate(dict(self.plan,expected_sequence=42796),self.raw)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw,lambda:122)
        r=FakeRegisters();r.values[0x20]=42797
        for i,v in enumerate(s.START):r.values[0x80+i*4]=v
        with patch.object(s.OpeningProbe,'lock_hashes',return_value=('lock',)):
            d=s.OpeningProbe(r,self.plan,Mock(),source_raw=self.raw,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.EXTENDED)
            self.assertEqual(r.writes,[])
            self.assertEqual(d.adopt(s.START)['enabled_mask'],63);d.off()
    def test_no_other_axis_changes_and_two_edges(self):
        self.assertEqual(len(s.FRAMES),201)
        for q in s.FRAMES:self.assertEqual(q[1:],s.START[1:])
        self.assertLessEqual(max(abs(a[0]-b[0]) for a,b in zip(s.FRAMES,s.FRAMES[1:])),1)
    def test_review_and_finish_without_continuing(self):
        d=Device('full');d.pulses=s.START[:];events=[]
        with patch.object(s.m,'await_action'),patch.object(s,'reviewed_or_finish',return_value='finish'):
            s.run(d,events.append)
        self.assertEqual(d.pulses,s.EXTENDED);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(len([r for r in events if r['event']=='probe_step']),100)
    def test_return_requires_second_request(self):
        d=Device('full');d.pulses=s.START[:];gates=[]
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)),patch.object(s,'reviewed_or_finish',side_effect=['review_1','finish']):s.run(d,lambda e:None)
        self.assertEqual(gates,['probe_1','probe_2']);self.assertEqual(d.pulses,s.START)

if __name__=='__main__':unittest.main()
