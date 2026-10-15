import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_hip_arc_probe as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device

class ArcTests(unittest.TestCase):
    def setUp(self):
        rows=[dict(event='probe_complete',axis=i) for i in [1,2]]
        rows += [dict(event='hip_extension_comparison_complete'),dict(event='outputs_off',normal_frame_stop=True,
                 state=dict(sequence=42999,pulse_us=s.START,enabled_mask=0,armed=False,faults=0,pending=False))]
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        sha=hashlib.sha256(self.raw).hexdigest();p=patch.object(s,'SOURCE_SHA',sha);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=42999,
            expected_pulses_us=s.START,source_sha256=sha,route_sha256=s.ROUTE_SHA,boot_id=s.BOOT,
            duration_seconds=240,observer_ready=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000)
    def test_source_state_and_next_frame_enforced(self):
        s.validate(self.plan,self.raw,lambda:1)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw+b' ')
        with self.assertRaises(ValueError):s.validate(dict(self.plan,expected_sequence=42998),self.raw)
        r=FakeRegisters();r.values[0x20]=42999
        for i,v in enumerate(s.START):r.values[0x80+i*4]=v
        with patch.object(s.OpeningProbe,'lock_hashes',return_value=('lock',)):
            d=s.OpeningProbe(r,self.plan,Mock(),source_raw=self.raw,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.HIP)
            self.assertEqual(r.writes,[])
            self.assertEqual(d.adopt(s.START)['enabled_mask'],63);d.off()
    def test_arc_boundaries_reversal_and_limits(self):
        self.assertEqual([len(e) for e in s.EDGE_FRAMES],[100,80,80,100])
        self.assertEqual(s.ARC[0],s.EXTENDED);self.assertEqual(s.ARC[-1],s.HIP)
        self.assertEqual([s.HIP]+s.EDGE_FRAMES[2],list(reversed(s.ARC)))
        for q in s.FRAMES:
            self.assertEqual(q[6:],s.START[6:]);self.assertEqual(q[2],1565)
            self.assertTrue(1212<=q[1]<=1252)
        self.assertLessEqual(max(abs(x-y) for a,b in zip(s.FRAMES,s.FRAMES[1:]) for x,y in zip(a,b)),3)
        # No deliberate interior holds; integer quantization can repeat endpoint frames.
        for i in range(15,65):self.assertNotEqual(s.ARC[i],s.ARC[i+1])
    def test_only_four_gates_not_one_per_arc_point(self):
        d=Device('full');d.pulses=s.START[:];gates=[];events=[]
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)),patch.object(s,'reviewed_or_finish',side_effect=['review_1','review_2','review_3','finish']):s.run(d,events.append)
        self.assertEqual(gates,['probe_1','probe_2','probe_3','probe_4'])
        self.assertEqual(d.pulses,s.START);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(len([r for r in events if r['event']=='probe_step']),360)
    def test_stop_on_error_without_automatic_reverse(self):
        d=Device('full');d.pulses=s.START[:]
        with patch.object(s.m,'await_action'),patch.object(s,'reviewed_or_finish',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):s.run(d,lambda e:None)
        self.assertEqual(d.pulses,s.EXTENDED);self.assertTrue(d.stopped);self.assertFalse(d.normal)

if __name__=='__main__':unittest.main()
