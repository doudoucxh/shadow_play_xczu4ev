"""Offline temporal/route properties; no assertion of physical clearance."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations'/'calibration'))
import story_motion_opening_v4 as s
import story_motion_v3_candidate as previous


class OpeningV4Tests(unittest.TestCase):
    def test_audio_and_tiger_unchanged(self):
        score=json.loads((ROOT/'planning/wusong_complete_20261014/score.json').read_text(encoding='utf-8'))
        self.assertEqual(s.DURATION,score['audio']['sample_frames']/score['audio']['sample_rate_hz'])
        self.assertEqual(s.TIGER,previous.TIGER)
        self.assertEqual(s.HITS,previous.HITS)
        self.assertEqual(s.sample(0),s.START)
        self.assertEqual(s.sample(s.DURATION),s.START)

    def test_continuous_track_and_inset_mechanical_limits(self):
        result=s.check_envelope()
        self.assertLessEqual(result['certified_any_phase_25ms_step_us'],22)
        for track in (s.HUMAN,s.TIGER):
            self.assertTrue(all(a[0]<b[0] for a,b in zip(track,track[1:])))
            for t,q,_ in track:
                self.assertEqual(s.sample_track(track,t),q)
                self.assertTrue(0<=t<=s.DURATION)
        for i in range(6711):
            q=s.sample(min(i*.01,s.DURATION))
            for j,(lo,hi) in enumerate(s.DEGREE_LIMITS):
                self.assertTrue(500+lo*2000/270<=q[j]<=500+hi*2000/270)
            self.assertEqual(q[2],1565)
            self.assertTrue(1414<=q[3]<=1554)

    def test_observed_cadences_and_cross_keyframe_windows(self):
        for period in (.0217,.025):
            for phase in (0,.001,.007,.013,.019):
                t=phase;a=s.sample(t)
                while t<s.DURATION:
                    t=min(t+period,s.DURATION);b=s.sample(t)
                    self.assertLessEqual(max(abs(x-y) for x,y in zip(a,b)),22)
                    a=b
        for track in (s.HUMAN,s.TIGER):
            for t,_,_ in track:
                for dt in (.001,.007,.013,.024):
                    a,b=s.sample(t-dt),s.sample(t-dt+.025)
                    self.assertLessEqual(max(abs(x-y) for x,y in zip(a,b)),22)

    def test_dialogue_has_repeated_pointing_with_wrist_near_side(self):
        dialogue=[(t,q) for t,q,_ in s.HUMAN if 17<=t<23]
        self.assertGreaterEqual(sum(q==s.H_POINT for t,q in dialogue),3)
        self.assertGreaterEqual(sum(q==s.H_POINT_RETRACT for t,q in dialogue),3)
        self.assertTrue(all(q[:2]==[1570,1242] for _,q in dialogue))

    def test_fight_candidate_bounds_and_varied_intentions(self):
        fight=[(t,q,label) for t,q,label in s.HUMAN if 29<=t<58]
        for _,q,_ in fight:
            self.assertTrue(1510<=q[0]<=1570 and 1242<=q[1]<=1372)
            self.assertTrue(1460<=q[4]<=1540 and 1500<=q[5]<=1660)
        self.assertGreaterEqual(len(set(tuple(q) for _,q,_ in fight)),6)
        self.assertTrue(any(q==s.H_UP for _,q,_ in fight))
        self.assertTrue(any(q==s.H_HAMMER for _,q,_ in fight))
        for hit in s.HITS:
            self.assertTrue(any(t==hit and label.startswith('P') for t,_,label in fight))

    def test_no_playback_or_false_effect_verification(self):
        result=s.check_envelope()
        for key in ('motor_ready','automatic_replay_allowed','loaded_clearance_proven',
                    'hip_pose_verified','same_side_hammer_verified','overhead_crossing_verified'):
            self.assertFalse(result[key])
        self.assertFalse(hasattr(s,'run'))
        self.assertNotEqual(s.START,previous.START)


if __name__=='__main__':unittest.main()
