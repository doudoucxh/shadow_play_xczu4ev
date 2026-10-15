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

    def test_finish_rejects_wrong_endpoint_and_executes_five_reviewed_edges(self):
        s=dict(sequence=38064,pulse_us=t.pitch(head=80),enabled_mask=960,armed=True,pending=False,faults=0)
        rows=[dict(event='probe_complete',axis=1,state=s),
              dict(event='hold_alive',awaiting='review_1',state=s),
              dict(event='outputs_off',normal_frame_stop=False,state=dict(s,enabled_mask=0,armed=False))]
        raw=('\n'.join(json.dumps(r) for r in rows)).encode();sha=hashlib.sha256(raw).hexdigest()
        p=dict(self.p,profile=t.FINISH_PROFILE,expected_sequence=38064,expected_pulses_us=t.pitch(head=80),
               source_sha256=sha,route_sha256=t.route_digest(t.FINISH_TARGETS))
        with patch.object(t,'FINISH_SHA',sha):
            t.validate(p,raw,lambda:1)
            with self.assertRaises(ValueError):t.validate(dict(p,expected_pulses_us=t.START),raw,lambda:1)
            reg=FakeRegisters();reg.values[0x20]=38064
            for i,v in enumerate(t.pitch(head=80)):reg.values[0x80+4*i]=v
            with patch.object(t.HeightProbe,'lock_hashes',return_value=('lock',)):
                d=t.HeightProbe(reg,p,Mock(),source_raw=raw,wall=lambda:1,cancel_path='__missing__')
                with self.assertRaises(RuntimeError):d.adopt(t.START)
                self.assertEqual(reg.writes,[])
                self.assertEqual(d.adopt(t.pitch(head=80))['enabled_mask'],960);d.off()
        d=Device('full');d.plan['profile']=t.FINISH_PROFILE;d.pulses=t.pitch(head=80)
        events=[];gates=[]
        with patch.object(t.m,'await_action',side_effect=lambda d,e,n,s:gates.append(n)):
            t.run(d,events.append)
        self.assertEqual(gates,[a+str(i) for i in range(1,6) for a in ('probe_','review_')])
        self.assertEqual(d.pulses,t.START);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(len([r for r in events if r['event']=='probe_step']),500)

    def test_resume_exact_timeout_provenance_and_remaining_route(self):
        states=[dict(sequence=37563+i*100,pulse_us=q,enabled_mask=960,armed=True,pending=False,faults=0)
                for i,q in enumerate(t.TARGETS[1:5],1)]
        states[-1]['sequence']=37963
        rows=[dict(event='probe_complete',axis=i,state=s) for i,s in enumerate(states,1)]
        rows.append(dict(event='hold_alive',awaiting='review_4',state=states[-1]))
        rows.append(dict(event='outputs_off',normal_frame_stop=False,
                         state=dict(states[-1],enabled_mask=0,armed=False)))
        raw=('\n'.join(json.dumps(r) for r in rows)).encode();sha=hashlib.sha256(raw).hexdigest()
        p=dict(self.p,profile=t.RESUME_PROFILE,expected_sequence=37963,expected_pulses_us=t.pitch(head=40),
               source_sha256=sha,route_sha256=t.route_digest(t.RESUME_TARGETS))
        with patch.object(t,'RESUME_SHA',sha):
            t.validate(p,raw,lambda:1)
            with self.assertRaises(ValueError):t.validate(dict(p,expected_sequence=37562),raw,lambda:1)
            reg=FakeRegisters();reg.values[0x20]=37963
            for i,v in enumerate(t.pitch(head=40)):reg.values[0x80+4*i]=v
            with patch.object(t.HeightProbe,'lock_hashes',return_value=('lock',)):
                d=t.HeightProbe(reg,p,Mock(),source_raw=raw,wall=lambda:1,cancel_path='__missing__')
                with self.assertRaises(RuntimeError):d.adopt(t.START)
                self.assertEqual(reg.writes,[])
                self.assertEqual(d.adopt(t.pitch(head=40))['enabled_mask'],960);d.off()
        d=Device('full');d.plan['profile']=t.RESUME_PROFILE;d.pulses=t.pitch(head=40)
        events=[]
        with patch.object(t.m,'await_action'):
            t.run(d,events.append)
        self.assertEqual(d.pulses,t.START)
        self.assertEqual([r['state']['pulse_us'] for r in events if r['event']=='probe_complete'],t.RESUME_TARGETS[1:])
        self.assertTrue(d.normal and d.stopped)


if __name__=='__main__':unittest.main()
