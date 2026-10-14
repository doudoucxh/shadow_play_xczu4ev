import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('story', ROOT/'tools/build_story_rehearsal.py')
story = importlib.util.module_from_spec(spec)
spec.loader.exec_module(story)


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.score = json.loads((ROOT/'planning/wusong_complete_20261014/score.json').read_text(encoding='utf-8'))

    def test_new_audio_version_and_sample_exact_coverage(self):
        story.validate(self.score)
        self.assertEqual(self.score['audio']['sample_frames'], 2959360)
        self.assertEqual(len(self.score['scenes']), 20)
        self.assertAlmostEqual(self.score['audio']['duration_s'], 2959360/44100)

    def test_reject_gap_and_motor_ready(self):
        bad = copy.deepcopy(self.score)
        bad['scenes'][3]['start_sample'] += 1
        with self.assertRaises(AssertionError):
            story.validate(bad)
        bad = copy.deepcopy(self.score)
        bad['motor_ready'] = True
        with self.assertRaises(AssertionError):
            story.validate(bad)

    def test_punches_alternate_and_do_not_overlap_recovery(self):
        cues = self.score['impact_cues']
        self.assertEqual([c['time_s'] for c in cues], [46.38,47.78,50.21,51.68,53.35,54.56,56.82,57.44])
        for a,b in zip(cues,cues[1:]):
            self.assertNotEqual(a['arm'],b['arm'])
            self.assertLess(a['phases'][-1]['time_s'],b['phases'][0]['time_s'])

    def test_recorded_anchors_are_exact_not_scaled(self):
        for motif in self.score['recorded_motifs'].values():
            source = json.loads((ROOT/motif['source']).read_text(encoding='utf-8'))
            for original, copied in zip(source['poses'],motif['anchors']):
                self.assertEqual(copied['command_pulse_us'],original.get('command_pulse_us', original.get('command_pulses_us')))
                self.assertEqual(copied['evidence_views'],original.get('views',{}))

    def test_terminal_pose_is_not_center_reset(self):
        self.assertFalse(self.score['end_policy']['automatic_center'])
        self.assertFalse(self.score['slide_rails_enabled'])
        self.assertFalse(self.score['automatic_replay_allowed'])


if __name__ == '__main__':
    unittest.main()
