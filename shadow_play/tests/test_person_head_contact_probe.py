import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_head_contact_probe as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device

class HeadTests(unittest.TestCase):
    def setUp(self):
        self.raw='\n'.join(json.dumps(r) for r in [dict(event='story_complete'),dict(event='outputs_off',
            normal_frame_stop=True,state=dict(sequence=41688,pulse_us=s.START,enabled_mask=0,armed=False,faults=0,pending=False))]).encode()
        sha=hashlib.sha256(self.raw).hexdigest();p=patch.object(s,'SOURCE_SHA',sha);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=41688,
            expected_pulses_us=s.START,source_sha256=sha,route_sha256=s.ROUTE_SHA,boot_id=s.BOOT,
            duration_seconds=240,observer_ready=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=1000)
    def test_validation_and_person_only_enable(self):
        s.validate(self.plan,self.raw,lambda:1)
        with self.assertRaises(ValueError):s.validate(dict(self.plan,expected_sequence=41687),self.raw)
        reg=FakeRegisters();reg.values[0x20]=41688
        for i,v in enumerate(s.START):reg.values[0x80+i*4]=v
        with patch.object(s.HeadProbe,'lock_hashes',return_value=('lock',)):
            d=s.HeadProbe(reg,self.plan,Mock(),source_raw=self.raw,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.TARGETS[1])
            self.assertEqual(reg.writes,[])
            self.assertEqual(d.adopt(s.START)['enabled_mask'],63);d.off()
    def test_finish_after_first_does_not_execute_second(self):
        d=Device('full');d.pulses=s.START[:];events=[]
        with patch.object(s.m,'await_action'),patch.object(s,'reviewed_or_finish',return_value='finish'):
            s.run(d,events.append)
        self.assertEqual(d.pulses,s.TARGETS[1]);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(len([r for r in events if r['event']=='probe_step']),100)
    def test_second_step_only_after_review(self):
        d=Device('full');d.pulses=s.START[:];events=[];gates=[]
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)),patch.object(s,'reviewed_or_finish',side_effect=['review_1','finish']):
            s.run(d,events.append)
        self.assertEqual(gates,['probe_1','probe_2']);self.assertEqual(d.pulses,s.TARGETS[2])
        self.assertTrue(d.normal and d.stopped)
    def test_stale_finish_rejected(self):
        d=Device('full');d.host.action=('finish',d.sequence-1)
        with self.assertRaises(RuntimeError):s.reviewed_or_finish(d,lambda e:None,1,lambda dt:None)
    def test_error_stops_without_return(self):
        d=Device('full');d.pulses=s.START[:]
        with patch.object(s.m,'await_action'),patch.object(s,'reviewed_or_finish',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):s.run(d,lambda e:None)
        self.assertTrue(d.stopped);self.assertFalse(d.normal);self.assertEqual(d.pulses,s.TARGETS[1])

if __name__=='__main__':unittest.main()
