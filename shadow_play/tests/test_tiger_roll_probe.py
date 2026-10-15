import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import tiger_roll_probe as t
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device


class HeightTests(unittest.TestCase):
    def setUp(self):
        self.raw=json.dumps(dict(event='story_complete')).encode()+b'\n'+json.dumps(dict(
            event='outputs_off',normal_frame_stop=True,state=dict(sequence=37562,pulse_us=t.START,
            enabled_mask=0,armed=False,pending=False,faults=0))).encode()
        sha=hashlib.sha256(self.raw).hexdigest()
        self.p=dict(profile=t.PROFILE,approval=t.m.c.APPROVAL,expected_sequence=37562,
            expected_pulses_us=t.START,boot_id=t.BOOT,source_sha256=sha,route_sha256=t.ROUTE_SHA,
            duration_seconds=240,observer_ready=True,dual_view_pose_reviewed=True,
            height_probe_only=True,reviewed_at_unix_ms=1000)
        self.patcher=patch.object(t,'SOURCE_SHA',sha);self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_bounds_and_source(self):
        t.validate(self.p,self.raw,lambda:1)
        self.assertEqual(len(t.FRAMES),601)
        for p in (dict(self.p,expected_sequence=1),dict(self.p,height_probe_only=False)):
            with self.assertRaises(ValueError):t.validate(p,self.raw,lambda:1)
        with self.assertRaises(ValueError):t.validate(self.p,self.raw+b' ',lambda:1)
        with self.assertRaises(ValueError):t.validate(self.p,self.raw,lambda:122)

    def test_only_tiger_enabled_and_exact_frames(self):
        reg=FakeRegisters();reg.values[0x20]=37562
        for i,v in enumerate(t.START):reg.values[0x80+i*4]=v
        now=[0.]
        with patch.object(t.HeightProbe,'lock_hashes',return_value=('lock',)):
            d=t.HeightProbe(reg,self.p,Mock(),source_raw=self.raw,wall=lambda:1,
                            clock=lambda:now[0],cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(t.pitch(head=80))
            self.assertEqual(reg.writes,[])
            self.assertEqual(d.adopt(t.START)['enabled_mask'],960)
            d.phase='height_probe';now[0]=.02;d.next_command=t.FRAMES[1]
            d.adopt(t.FRAMES[1])
            with self.assertRaises(RuntimeError):d.adopt(t.pitch(head=80))
            self.assertEqual(d.pulses[:6],t.START[:6]);d.off()

    def test_all_six_edges_gated_and_normal_stop(self):
        d=Device('full');d.pulses=t.START[:];events=[];gates=[]
        with patch.object(t.m,'await_action',side_effect=lambda d,e,n,s:gates.append(n)):
            t.run(d,events.append)
        self.assertEqual(gates,[a+str(i) for i in range(1,7) for a in ('probe_','review_')])
        self.assertEqual(d.pulses,t.START)
        self.assertTrue(d.normal and d.stopped)
        self.assertFalse(events[-1]['full_rollover'])

    def test_review_failure_stops_without_auto_return(self):
        d=Device('full');d.pulses=t.START[:];events=[]
        def gate(d,e,n,s):
            if n=='review_1':raise RuntimeError('view lost')
        with patch.object(t.m,'await_action',side_effect=gate):
            with self.assertRaisesRegex(RuntimeError,'view lost'):t.run(d,events.append)
        self.assertEqual(d.pulses,t.TARGETS[1]);self.assertTrue(d.stopped);self.assertFalse(d.normal)


if __name__=='__main__':unittest.main()
