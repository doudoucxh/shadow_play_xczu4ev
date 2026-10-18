"""Preparation integrity checks, without connecting to a board or camera."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import prepare_v20_performance as prepare
import v20_preparation_model as model


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=prepare.build(prepare.DEFAULT_SOURCE)

    def test_independent_coverage_groups_and_drills_not_an_extra_scene(self):
        p=self.plan
        self.assertEqual(len(p['actions']),14);self.assertEqual(len(p['position_groups']),4)
        self.assertEqual(p['main_scene_order'],['A%02d'%n for n in range(1,11)])
        self.assertEqual(p['separate_drills'],['A11','A12','A13','A14'])
        self.assertEqual(p['uncovered_impact_ids'],['P04','P05','P06','P07','P08'])
        self.assertFalse(p['continuous_full_show_available'])
        self.assertEqual(len(p['audio_impact_coverage']),19)
        self.assertEqual(next(c for c in p['audio_impact_coverage'] if c['id']=='P01')['covered_by'],['A06','A11','A14'])

    def test_every_endpoint_has_a_recorded_source_not_an_inverse_guess(self):
        poses=self.plan['historical_a01_poses']
        allowed={tuple(p['pulse_us']) for p in poses.values()}
        for key in self.plan['a01_candidate']['keyframes']:
            self.assertIn(tuple(key['pulse_us']),allowed)
            self.assertEqual(key['pulse_us'][:6],[1500]*6)
        self.assertEqual(poses['head_lift']['pulse_us'][6:],[1500,1540,1500,1500])
        self.assertEqual(poses['tail_lift']['pulse_us'][6:],[1500,1500,1500,1460])
        self.assertEqual(poses['both_lift']['pulse_us'][6:],[1500,1540,1500,1460])
        for key,value in poses.items():
            if key!='midpoint':
                source=value['source'];path=ROOT/source['path']
                self.assertEqual(source['sha256'],prepare.sha(path))
                self.assertFalse(value['current_assembly_verified'])

    def test_original_timing_full_frames_and_limits(self):
        data=model.compile_frames(self.plan['a01_candidate'])
        self.assertEqual(len(data['frames']),316);self.assertEqual(data['duration_s'],6.3)
        self.assertEqual(data['frames'][0]['source_time_s'],2.7)
        self.assertEqual(data['frames'][-1]['source_time_s'],9.)
        self.assertLessEqual(data['peak_step_us'],3)
        for row in data['frames']:
            self.assertEqual(row['enabled_mask'],960)
            self.assertEqual(row['pulse_us'][:6],[1500]*6)
            self.assertTrue(all(1460<=v<=1540 for v in row['pulse_us'][6:]))

    def test_quarter_speed_stretches_motion_without_claiming_audio_sync(self):
        candidate=self.plan['a01_candidate'];data=model.compile_frames(candidate,.25)
        self.assertEqual(len(data['frames']),1261);self.assertEqual(data['duration_s'],25.2)
        self.assertFalse(data['sound_preview_allowed'])
        self.assertEqual(data['frames'][400]['pulse_us'],model.sample(candidate,2.))
        self.assertLessEqual(data['peak_step_us'],1)

    def test_direction_checks_are_individual_unreviewed_out_and_back(self):
        self.assertEqual(len(self.plan['a01_direction_checks']),6)
        for check in self.plan['a01_direction_checks']:
            data=model.compile_frames(check)
            self.assertEqual(len(data['frames']),301)
            self.assertEqual(data['frames'][0]['pulse_us'],[1500]*10)
            self.assertEqual(data['frames'][-1]['pulse_us'],[1500]*10)
            self.assertFalse(check['reviewed']);self.assertIsNone(check['observer_note'])
            self.assertEqual(data['peak_step_us'],1)

    def test_no_measured_pose_is_fabricated_for_remaining_actions(self):
        for action in self.plan['actions']:
            self.assertFalse(action['motor_ready']);self.assertIsNone(action['manual_start_pulse_us'])
            self.assertIsNone(action['measured_waypoints']);self.assertIsNone(action['onsite_review'])
            self.assertEqual(set(action['reference_ranges']),{'WH','WL','WR','TH','TT'})
        self.assertFalse(self.plan['motor_ready']);self.assertFalse(self.plan['automatic_replay_allowed'])

    def test_preview_preserves_v20_standing_and_riding_arc_sides(self):
        descriptions={a['id']:a['preview_description'] for a in self.plan['actions']}
        for action in ('A05','A06','A12','A13'):self.assertIn('右外侧',descriptions[action])
        self.assertIn('低位',descriptions['A05'])
        self.assertIn('左外侧',descriptions['A08']);self.assertIn('11击',descriptions['A08'])
        self.assertIn('左上右下',descriptions['A13']);self.assertIn('不包含拖行',descriptions['A10'])

    def test_malformed_or_expanded_candidate_never_compiles(self):
        baseline=self.plan['a01_candidate']
        for mutate in [lambda c:c.update(enabled_mask=1023),lambda c:c.update(motor_ready=True),
                       lambda c:c['keyframes'][1]['pulse_us'].__setitem__(0,1501),
                       lambda c:c['keyframes'][1]['pulse_us'].__setitem__(7,1541),
                       lambda c:c['keyframes'][1].update(time_s=0)]:
            candidate=copy.deepcopy(baseline);mutate(candidate)
            with self.assertRaises(ValueError):model.compile_frames(candidate)
        for speed in (0,1.1,float('nan'),True):
            with self.assertRaises(ValueError):model.compile_frames(baseline,speed)

    def test_sampling_does_not_create_an_execution_permission(self):
        candidate=copy.deepcopy(self.plan['a01_candidate']);candidate['motor_ready']=True;candidate['execution_binding']={'pretend':'approved'}
        gate=model.proposed_runtime_gate(candidate,self.plan['reference_checkpoint'])
        self.assertFalse(gate['execution_available']);self.assertFalse(gate['camera_required'])
        self.assertIn('Preparation tool has no hardware transport',gate['reasons'])

    def test_wrong_audio_version_is_rejected(self):
        original=prepare.load
        def load(path):
            data=original(path)
            if path.name=='task1_audio.json':data['source']['sha256']='0'*64
            return data
        with patch.object(prepare,'load',side_effect=load):
            with self.assertRaises(ValueError):prepare.build(prepare.DEFAULT_SOURCE)

    def test_output_retains_source_plan_and_escapes_script_content(self):
        plan=copy.deepcopy(self.plan);plan['actions'][0]['preview_description']='</script><script>window.bad=true</script>'
        before=copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'preview';frames=Path(folder)/'frames'
            prepare.write_outputs(plan,out,frames)
            text=(out/'preview.html').read_text(encoding='utf-8')
            self.assertTrue(r'\u003c/script>' in text,'Escape HTML delimiters in JSON data')
            self.assertTrue('<script>window.bad' not in text,'Description must remain JSON data')
            self.assertTrue((out/'准备单.md').is_file())
            self.assertEqual(len(list(frames.glob('*.json'))),8)
        self.assertEqual(plan,before)


if __name__=='__main__':unittest.main()
