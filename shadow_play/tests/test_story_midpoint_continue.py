import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import story_midpoint_continue as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device, Audio


def evidence():
    def state(seq,p,active=True):
        return dict(sequence=seq,pulse_us=p,armed=active,enabled_mask=1023 if active else 0,faults=0,pending=False)
    frames=s.m.transition_frames(s.m.MIDPOINT,s.m.TARGETS[1])
    rows=[dict(event='probe_step',state=state(34029+i,q)) for i,q in enumerate(frames)]
    rows.extend([dict(event='first_edge_complete',state=state(34128,frames[-1])),
                 dict(event='outputs_off',normal_frame_stop=True,state=state(34129,frames[-1],False))])
    return ('\n'.join(json.dumps(r) for r in rows)+'\n').encode()


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.raw=evidence()
        self.sha=hashlib.sha256(self.raw).hexdigest()
        self.plan=dict(profile=s.PROFILE,expected_sequence=34129,expected_pulses_us=s.m.TARGETS[1],
                       boot_id=s.BOOT,source_sha256=self.sha,observer_ready=True,dual_view_pose_reviewed=True,
                       endpoint_comparison='no_obvious_change_in_new_dual_views',duration_seconds=240,
                       story_route_sha256=s.m.score.check_envelope()['route_sha256'],reviewed_at_unix_ms=1000)
        self.patch=patch.object(s,'SOURCE_SHA',self.sha);self.patch.start();self.addCleanup(self.patch.stop)

    def test_requires_real_source_and_fresh_review(self):
        s.validate(self.plan,self.raw,wall=lambda:1)
        for raw,wall in [(self.raw+b' ',lambda:1),(self.raw,lambda:122)]:
            with self.assertRaises(ValueError):s.validate(self.plan,raw,wall)
        for key,value in [('expected_sequence',34027),('expected_pulses_us',[1500]*10),('observer_ready',False)]:
            with self.assertRaises(ValueError):s.validate(dict(self.plan,**{key:value}),self.raw,lambda:1)

    def test_state_mismatch_no_register_writes(self):
        reg=FakeRegisters()
        with patch.object(s.ContinuationSession,'lock_hashes',return_value=('lock',)):
            with self.assertRaises(RuntimeError):
                s.ContinuationSession(reg,self.plan,Mock(),source_raw=self.raw,wall=lambda:1,cancel_path='__missing__')
        self.assertEqual(reg.writes,[])

    def test_only_same_endpoint_can_enable(self):
        reg=FakeRegisters();reg.values[0x20]=34129
        for i,v in enumerate(s.m.TARGETS[1]):reg.values[0x80+4*i]=v
        with patch.object(s.ContinuationSession,'lock_hashes',return_value=('lock',)):
            d=s.ContinuationSession(reg,self.plan,Mock(),source_raw=self.raw,wall=lambda:1,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.m.score.START)
            self.assertEqual(reg.writes,[])
            self.assertEqual(d.adopt(s.m.TARGETS[1])['enabled_mask'],1023)
            d.off()

    def test_three_edges_reviewed_before_audio_and_normal_off(self):
        d=Device('full');d.pulses=s.m.TARGETS[1][:];d.host.action=None
        a=Audio('full');a.duration=s.m.score.DURATION
        events=[];gates=[]
        def emit(e):
            events.append(e)
            if e['event']=='reference_held' and e.get('profile')==s.m.story.PROFILE:
                self.assertEqual(len(gates),6)
                d.host.action=('demo',d.sequence)
        with patch.object(s.m,'await_action',side_effect=lambda d,e,n,sl:gates.append(n)):
            s.run(d,emit,a)
        self.assertEqual(gates,[v+str(i) for i in range(2,5) for v in ('probe_','review_')])
        self.assertEqual(len([e for e in events if e['event']=='probe_step' and 'edge' in e]),300)
        self.assertTrue(d.normal and d.stopped and a.closed)
        self.assertIn('story_complete',[e['event'] for e in events])

    def test_audio_wait_reports_fresh_active_state_before_demo(self):
        d=Device('full');d.pulses=s.m.score.START[:];d.host.action=None
        a=Audio('full');a.duration=s.m.score.DURATION
        holds=[]
        def emit(e):
            if e['event']=='hold_alive':
                self.assertEqual(e['awaiting'],'demo')
                holds.append((d.clock(),e['state']['sequence']))
                if len(holds)==7:d.host.action=('demo',e['state']['sequence'])
        s.m.story.run(d,emit,a)
        self.assertGreaterEqual(holds[-1][0]-holds[0][0],3)
        self.assertEqual(len(set(seq for _,seq in holds)),1)
        self.assertTrue(d.normal and a.closed)


if __name__=='__main__':unittest.main()
