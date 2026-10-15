import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import story_midpoint_session as m
from test_servo_commissioning import FakeRegisters


def plan():
    return dict(profile=m.PROFILE,expected_pulses_us=[1500]*10,expected_sequence=34027,
                operator_midpoint_confirmed=True,observer_ready=True,dual_view_pose_reviewed=True,
                story_route_sha256=m.score.check_envelope()['route_sha256'],duration_seconds=240)


class MidpointTests(unittest.TestCase):
    def test_full_transition_and_audio_handoff_offline(self):
        from unittest.mock import patch
        from test_story_audio_session import Device, Audio
        class Tracked(Device):
            def adopt(self,q):
                limit=24 if getattr(self,'phase','')=='timeline' else 3
                assert max(abs(x-y) for x,y in zip(q,self.pulses))<=limit
                return super().adopt(q)
        d=Tracked('full');d.pulses=[1500]*10;d.host.action=None
        audio=Audio('full');audio.duration=m.score.DURATION
        events=[];reviews=[]
        def emit(event):
            events.append(event)
            if event['event']=='reference_held' and event.get('profile')==m.story.PROFILE:
                d.host.action=('demo',d.sequence)
        with patch.object(m,'await_action',side_effect=lambda d,e,expected,s:reviews.append(expected)):
            m.run(d,emit,audio)
        self.assertEqual(reviews,[v+str(i) for i in range(1,5) for v in ('probe_','review_')])
        self.assertEqual(d.pulses,m.score.START)
        self.assertTrue(d.stopped and d.normal and audio.closed)
        self.assertIn('story_complete',[e['event'] for e in events])

    def test_fixed_transition(self):
        m.validate(plan())
        self.assertEqual(m.TARGETS[0],[1500]*10)
        self.assertEqual(m.TARGETS[-1],m.score.START)
        for a,b in zip(m.TARGETS,m.TARGETS[1:]):
            frames=m.transition_frames(a,b)
            self.assertEqual(frames[-1],b)
            for q in frames:
                self.assertTrue(all(min(x,y)<=v<=max(x,y) for x,y,v in zip(a,b,q)))

    def test_stale_or_wrong_reference_rejected_without_writes(self):
        reg=FakeRegisters()
        # Existing test fixtures use no real lock; inject stable lock evidence.
        from unittest.mock import patch
        with patch.object(m.MidpointSession,'lock_hashes',return_value=('unchanged',)):
            with self.assertRaises(RuntimeError):
                m.MidpointSession(reg,plan(),Mock(),cancel_path='__missing_cancel__')
        self.assertEqual(reg.writes,[])

    def test_first_enable_is_only_midpoint_then_fixed_step(self):
        from unittest.mock import patch
        reg=FakeRegisters();reg.values[0x20]=34027
        now=[0.]
        with patch.object(m.MidpointSession,'lock_hashes',return_value=('unchanged',)):
            d=m.MidpointSession(reg,plan(),Mock(),clock=lambda:now[0],cancel_path='__missing_cancel__')
            with self.assertRaises(RuntimeError):d.adopt(m.score.START)
            self.assertEqual(reg.writes,[])
            self.assertEqual(d.adopt([1500]*10)['enabled_mask'],1023)
            d.phase='transition';d.next_command=[1501]*10;now[0]=.02
            d.adopt([1501]*10)
            d.next_command=[1505]*10;now[0]=.04
            with self.assertRaises(RuntimeError):d.adopt([1505]*10)
            d.off()

    def test_confirmation_is_not_inferred_from_registers(self):
        p=plan();p['operator_midpoint_confirmed']=False
        with self.assertRaises(ValueError):m.validate(p)


if __name__=='__main__':unittest.main()
