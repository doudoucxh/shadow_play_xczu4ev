import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import story_opening_v4_session as s
from test_servo_commissioning import FakeRegisters
from test_story_audio_session import Device,Audio

class RehearsalTests(unittest.TestCase):
    def setUp(self):
        status_patch=patch.object(s.score,'STATUS','offline_candidate_not_executed')
        status_patch.start();self.addCleanup(status_patch.stop)
        state=dict(sequence=43685,pulse_us=s.START,armed=False,enabled_mask=0,pending=False,faults=0)
        rows=[dict(event='probe_complete',axis=i) for i in (1,2,3)]
        rows += [dict(event='hold_alive',awaiting='review_3',state=state),dict(event='outputs_off',normal_frame_stop=False,state=state)]
        self.raw='\n'.join(json.dumps(x) for x in rows).encode();sha=hashlib.sha256(self.raw).hexdigest()
        p=patch.object(s,'SOURCE_SHA',sha);p.start();self.addCleanup(p.stop)
        self.plan=dict(profile=s.PROFILE,approval=s.m.c.APPROVAL,expected_sequence=43685,expected_pulses_us=s.START,
            source_sha256=sha,entry_sha256=s.ENTRY_SHA,story_route_sha256=s.score.check_envelope()['route_sha256'],
            boot_id=s.BOOT,duration_seconds=600,story_mode='full',observer_ready=True,dual_view_pose_reviewed=True,
            endpoint_comparison='overall_pose_retained_small_passive_wrist_shift',reviewed_at_unix_ms=1000)
    def test_exact_lineage_freshness_and_frames(self):
        s.validate(self.plan,self.raw,lambda:1)
        for p in (dict(self.plan,expected_sequence=43383),dict(self.plan,entry_sha256='bad'),dict(self.plan,observer_ready=False)):
            with self.assertRaises(ValueError):s.validate(p,self.raw)
        with self.assertRaises(ValueError):s.validate(self.plan,self.raw,lambda:121)
        self.assertTrue(all(q[6:]==s.START[6:] for q in s.FRAMES))
    def test_withdrawn_high_head_candidate_cannot_enable(self):
        with patch.object(s.score,'STATUS','withdrawn_after_S_component_review_head_too_high'):
            with self.assertRaisesRegex(ValueError,'withdrawn'):s.validate(self.plan,self.raw)
    def test_no_skip_to_show_before_component_review(self):
        r=FakeRegisters();r.values[0x20]=43685
        for i,v in enumerate(s.START):r.values[0x80+4*i]=v
        with patch.object(s.OpeningSession,'lock_hashes',return_value=('lock',)):
            d=s.OpeningSession(r,self.plan,Mock(),source_raw=self.raw,cancel_path='__missing__')
            with self.assertRaises(RuntimeError):d.adopt(s.TARGETS[1])
            self.assertEqual(r.writes,[]);self.assertEqual(d.adopt(s.START)['enabled_mask'],1023);d.off()
    def test_finish_component_does_not_start_audio(self):
        d=Device('full');d.pulses=s.START[:];audio=Mock();ev=[]
        with patch.object(s.m,'await_action'),patch.object(s,'review_or_finish',return_value='finish'):
            s.run(d,ev.append,audio)
        self.assertTrue(d.normal and d.stopped);audio.start.assert_not_called();audio.close.assert_called_once()
        self.assertEqual(len([x for x in ev if x['event']=='probe_step']),100)
    def test_review_failure_stops_in_place(self):
        d=Device('full');d.pulses=s.START[:];audio=Mock()
        with patch.object(s.m,'await_action'),patch.object(s,'review_or_finish',side_effect=RuntimeError('lost view')):
            with self.assertRaises(RuntimeError):s.run(d,lambda x:None,audio)
        self.assertTrue(d.stopped);self.assertFalse(d.normal);self.assertEqual(d.pulses,s.TARGETS[1]);audio.start.assert_not_called()
    def test_all_reviews_then_fresh_demo_full_audio(self):
        d=Device('full');d.pulses=s.START[:];d.host.action=None;audio=Audio('full');audio.duration=s.score.DURATION;ev=[]
        def emit(x):
            ev.append(x)
            if x['event']=='reference_held' and 'story_mode' in x:
                self.assertTrue(d.components_complete);d.host.action=('demo',d.sequence)
        with patch.object(s.m,'await_action'),patch.object(s,'review_or_finish',side_effect=['review_'+str(i) for i in range(1,6)]),patch.object(s.m.story,'score'),patch.object(s.m.story,'ROUTE_SHA'),patch.object(s.m.story,'PROFILE'):
            s.run(d,emit,audio)
        self.assertIn('story_complete',[x['event'] for x in ev]);self.assertTrue(d.normal and d.stopped)
        self.assertEqual(d.pulses,s.START);self.assertTrue(audio.closed)

if __name__=='__main__':unittest.main()
