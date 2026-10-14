"""Offline properties only: these do not certify physical motion."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations'/'calibration'))
import story_motion_v3_candidate as s


class CandidateTests(unittest.TestCase):
    def test_original_audio_and_hits_retained(self):
        score=json.loads((ROOT/'planning/wusong_complete_20261014/score.json').read_text(encoding='utf-8'))
        self.assertEqual(s.DURATION,score['audio']['sample_frames']/score['audio']['sample_rate_hz'])
        self.assertEqual(s.HITS,[46.38,47.78,50.21,51.68,53.35,54.56,56.82,57.44])
        for hit in s.HITS:
            self.assertTrue(any(t==hit and label.startswith('P') for t,_,label in s.HUMAN))

    def test_command_envelope_and_step_bound(self):
        result=s.check_envelope()
        self.assertLessEqual(result['peak_20ms_step_us'],22)
        self.assertEqual(s.sample(0),s.START)
        self.assertEqual(s.sample(s.DURATION),s.START)
        for track in (s.HUMAN,s.TIGER):
            self.assertTrue(all(a[0]<b[0] for a,b in zip(track,track[1:])))
            self.assertTrue(all(0<=t<=s.DURATION for t,_,_ in track))

    def test_roar_followed_by_bite_and_no_false_completion(self):
        high=[i for i,(_,q,_) in enumerate(s.TIGER) if q==s.TO]
        self.assertGreaterEqual(len(high),3)
        for i in high:
            later=s.TIGER[i+1:]
            self.assertTrue(any(q==s.TP and t-s.TIGER[i][0]<=1 for t,q,_ in later))
        self.assertFalse(s.MOTOR_READY)
        self.assertFalse(s.AUTOMATIC_REPLAY_ALLOWED)
        self.assertFalse(s.check_envelope()['loaded_clearance_proven'])
        self.assertFalse(s.check_envelope()['feet_at_bottom_verified'])
        self.assertFalse(hasattr(s,'run'))

    def test_no_long_frozen_active_tiger_and_pose_variety(self):
        active=[row for row in s.TIGER if row[0]<58]
        self.assertLessEqual(max(b[0]-a[0] for a,b in zip(active,active[1:])),1.5)
        self.assertGreaterEqual(len(set(tuple(q) for _,q,_ in s.HUMAN)),8)
        self.assertGreaterEqual(len(set(tuple(q) for _,q,_ in s.TIGER)),10)


if __name__=='__main__':unittest.main()
