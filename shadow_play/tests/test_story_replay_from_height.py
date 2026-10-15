import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import story_replay_from_height as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device,Audio


class ReplayTests(unittest.TestCase):
    def setUp(self):
        state=dict(sequence=38465,pulse_us=s.REFERENCE,enabled_mask=960,armed=True,pending=False,faults=0)
        rows=[]
        for i,v in enumerate((1410,1490,1410,1330),1):
            q=s.REFERENCE[:];q[7]=v
            rows.append(dict(event='probe_complete',axis=i,state=dict(state,pulse_us=q)))
        rows.extend([dict(event='hold_alive',awaiting='review_4',state=state),
                     dict(event='outputs_off',normal_frame_stop=False,state=dict(state,enabled_mask=0,armed=False))])
        self.raw='\n'.join(json.dumps(r) for r in rows).encode()
        self.show='\n'.join(json.dumps(r) for r in [dict(event='story_complete'),
            dict(event='outputs_off',normal_frame_stop=True,state=dict(sequence=37562,pulse_us=s.m.score.START))]).encode()
        a=hashlib.sha256(self.raw).hexdigest();b=hashlib.sha256(self.show).hexdigest()
        for key,val in [('SOURCE_SHA',a),('SHOW_SHA',b)]:
            p=patch.object(s,key,val);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=38465,
            expected_pulses_us=s.REFERENCE,boot_id=s.BOOT,source_sha256=a,show_sha256=b,
            story_mode='full',duration_seconds=240,observer_ready=True,dual_view_pose_reviewed=True,
            endpoint_comparison='no_obvious_change_in_new_dual_views',
            story_route_sha256=s.m.score.check_envelope()['route_sha256'],reviewed_at_unix_ms=1000)

    def test_evidence_state_and_freshness(self):
        s.validate(self.plan,self.raw,self.show,lambda:1)
        for p in [dict(self.plan,expected_sequence=38064),dict(self.plan,expected_pulses_us=s.m.score.START),
                  dict(self.plan,observer_ready=False),dict(self.plan,story_route_sha256='bad')]:
            with self.assertRaises(ValueError):s.validate(p,self.raw,self.show,lambda:1)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw+b' ',self.show,lambda:1)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw,self.show,lambda:122)

    def test_entry_is_exact_and_cannot_jump_to_show(self):
        reg=FakeRegisters();reg.values[0x20]=38465
        for i,v in enumerate(s.REFERENCE):reg.values[0x80+4*i]=v
        with patch.object(s.ReplaySession,'lock_hashes',return_value=('lock',)):
            d=s.ReplaySession(reg,self.plan,Mock(),source_raw=self.raw,show_raw=self.show,wall=lambda:1,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.m.score.START)
            self.assertEqual(reg.writes,[])
            self.assertEqual(d.adopt(s.REFERENCE)['enabled_mask'],1023)
            with self.assertRaises(RuntimeError):d.adopt(s.m.score.START)
            d.off()

    def test_full_handoff_after_entry_and_fresh_demo(self):
        d=Device('full');d.pulses=s.REFERENCE[:];d.host.action=None
        audio=Audio('full');audio.duration=s.m.score.DURATION
        events=[];gates=[]
        def emit(e):
            events.append(e)
            if e['event']=='reference_held' and e.get('profile')==s.m.story.PROFILE:
                self.assertEqual(gates,['probe_1','review_1'])
                self.assertEqual(d.pulses,s.m.score.START)
                d.host.action=('demo',d.sequence)
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)):
            s.run(d,emit,audio)
        self.assertEqual(len([e for e in events if e['event']=='probe_step' and 'edge' in e]),100)
        self.assertIn('story_complete',[e['event'] for e in events])
        self.assertTrue(d.normal and d.stopped and audio.closed)

    def test_review_failure_stops_without_audio_or_return(self):
        d=Device('full');d.pulses=s.REFERENCE[:];events=[];audio=Mock()
        def gate(d,e,n,sl):
            if n=='review_1':raise RuntimeError('view unavailable')
        with patch.object(s.m,'await_action',side_effect=gate):
            with self.assertRaises(RuntimeError):s.run(d,events.append,audio)
        audio.start.assert_not_called();audio.close.assert_called_once()
        self.assertTrue(d.stopped);self.assertFalse(d.normal)


if __name__=='__main__':unittest.main()
