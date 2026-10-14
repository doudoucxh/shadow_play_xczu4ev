import unittest
from test_story_audio_session import Device,Audio
import story_motion_v2 as s
import story_audio_session_v2 as actor

class Tests(unittest.TestCase):
    def test_full_audio_with_reference_entry_and_exit(self):
        d=Device('full');d.pulses=s.BASE[:];a=Audio('full');events=[]
        actor.run(d,events.append,a)
        self.assertTrue(d.normal and d.stopped and a.closed)
        self.assertEqual(d.pulses,s.BASE)
        complete=next(e for e in events if e['event']=='timeline_complete')
        self.assertEqual(complete['original_range_s'],[0,s.DURATION])
        self.assertEqual(len([e for e in events if e['event']=='timeline_checkpoint']),len(set(t for track in [s.HUMAN,s.TIGER] for t,_,_ in track)))
    def test_failure_stops_without_return(self):
        d=Device('full');d.pulses=s.BASE[:];a=Audio('full',True);events=[]
        with self.assertRaisesRegex(RuntimeError,'speaker lost'):actor.run(d,events.append,a)
        self.assertTrue(d.stopped and a.closed);self.assertFalse(d.normal)
        self.assertNotIn('story_complete',[e['event'] for e in events])
    def test_no_withdrawn_crossing_and_bounded_steps(self):
        self.assertLessEqual(s.check_envelope()['peak_20ms_step_us'],22)
        self.assertTrue(all(p[0]<=1575 for _,p,_ in s.HUMAN))
        self.assertTrue(all(p[0]==1510 and p[2]==1550 for _,p,_ in s.TIGER))
        self.assertEqual(s.sample(0),s.BASE)
        self.assertEqual(s.sample(s.DURATION),s.BASE)
    def test_shadow_roar_matches_observed_timing(self):
        import tiger_shadow_roar as roar
        for i in range(151):self.assertEqual(s.sample(4+i*.02)[6:],roar.sample(i*.02)[6:])

if __name__=='__main__':unittest.main()
