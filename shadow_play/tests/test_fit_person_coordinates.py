import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

MODULE_DIR = Path(__file__).resolve().parents[1] / 'integrations/calibration'
sys.path.insert(0, str(MODULE_DIR))
from fit_person_coordinates import fit, predict, train


def synthetic():
    rng = np.random.default_rng(251)
    inputs = rng.uniform(-1, 1, (24, 6))
    coupling = np.eye(6) * .12 + np.ones((6, 6)) * .008
    xy = .5 + inputs @ coupling
    samples = []
    for i, (command, point) in enumerate(zip(1500 + inputs * 90, xy)):
        samples.append(dict(sample_id=str(i), command_us=command.tolist(),
                            points=dict(zip(('wusong_left', 'wusong_neck', 'wusong_right'), point.reshape(3, 2).tolist())),
                            evidence=dict(front_file='sim/front-{}.jpg'.format(i), top_file='sim/top-{}.jpg'.format(i)),
                            annotation_verified=True, command_frame_pair_verified=True))
    return dict(version=1, geometry_id='synthetic-geometry', camera_id='synthetic-camera',
                coordinate_system='normalized_curtain', context_verified=True,
                simulation_only=True, samples=samples)


class PersonCoordinatesTests(unittest.TestCase):
    def setUp(self):
        self.data = synthetic()

    def test_coupled_synthetic_model(self):
        report = fit(self.data)
        self.assertFalse(report['deployment_ready'])
        self.assertTrue(report['simulation_only'])
        self.assertEqual(report['distinct_command_count'], 24)
        self.assertLess(max(report['validation']['inverse_rmse_per_axis_us']), 1e-8)
        self.assertLess(max(report['validation']['forward_rmse_per_point_normalized']), 1e-10)
        json.dumps(report, allow_nan=False)

    def test_real_label_preserved_without_claiming_deployment(self):
        self.data['simulation_only'] = False
        report = fit(self.data)
        self.assertFalse(report['simulation_only'])
        self.assertFalse(report['deployment_ready'])

    def test_missing_points_excluded(self):
        self.data['samples'][0]['points']['wusong_left'] = None
        report = fit(self.data)
        self.assertEqual(report['sample_count'], 23)
        self.assertEqual(report['excluded_samples'][0]['reasons'], ['missing_points'])

    def test_unverified_or_missing_evidence_excluded(self):
        for key in ('annotation_verified', 'command_frame_pair_verified'):
            data = copy.deepcopy(self.data)
            data['samples'][0][key] = False
            self.assertEqual(fit(data)['excluded_sample_count'], 1)
        self.data['samples'][0]['evidence']['top_file'] = ' '
        self.assertEqual(fit(self.data)['excluded_sample_count'], 1)

    def test_context_not_verified_rejected(self):
        self.data['context_verified'] = False
        with self.assertRaisesRegex(ValueError, 'context_verified'):
            fit(self.data)

    def test_rank_deficient_commands(self):
        for sample in self.data['samples']:
            sample['command_us'][5] = sample['command_us'][4]
        with self.assertRaisesRegex(ValueError, 'rank deficient'):
            fit(self.data)

    def test_rank_deficient_points(self):
        for sample in self.data['samples']:
            sample['points']['wusong_right'] = sample['points']['wusong_left'][:]
        with self.assertRaisesRegex(ValueError, 'rank deficient'):
            fit(self.data)

    def test_nearly_singular_design_rejected(self):
        rng = np.random.default_rng(42)
        values = rng.normal(size=(30, 6))
        values[:, 5] = values[:, 4] + rng.normal(size=30) * 1e-8
        with self.assertRaisesRegex(ValueError, 'conditioned'):
            train(values, values)

    def test_duplicate_commands_held_together_and_spread_measured(self):
        repeat = copy.deepcopy(self.data['samples'][0])
        repeat['sample_id'] = 'repeat'
        repeat['points']['wusong_left'][0] += .01
        self.data['samples'].append(repeat)
        report = fit(self.data)
        folds = report['validation']['folds']
        fold = next(f for f in folds if '0' in f['held_sample_ids'])
        self.assertEqual(fold['held_sample_ids'], ['0', 'repeat'])
        self.assertEqual(fold['training_sample_count'], 23)
        self.assertEqual(len(folds), 24)
        spread = report['validation']['repeated_command_spreads'][0]
        self.assertAlmostEqual(spread['max_distance_from_mean_per_point'][0], .005)
        held = self.data['samples'][:1] + [repeat]
        remaining = self.data['samples'][1:24]
        x = np.asarray([s['command_us'] for s in remaining])
        y = np.asarray([sum((s['points'][k] for k in ('wusong_left', 'wusong_neck', 'wusong_right')), []) for s in remaining])
        # The independently fitted held-out prediction ignores the noisy repeat.
        estimate = predict(train(x, y), np.asarray([s['command_us'] for s in held]))
        self.assertAlmostEqual(estimate[0, 0], held[0]['points']['wusong_left'][0])

    def test_at_least_fourteen_distinct_commands(self):
        exact = copy.deepcopy(self.data)
        exact['samples'] = exact['samples'][:14]
        self.assertEqual(fit(exact)['distinct_command_count'], 14)
        self.data['samples'] = self.data['samples'][:13]
        with self.assertRaisesRegex(ValueError, '14 distinct'):
            fit(self.data)

    def test_rank_loss_in_held_out_fold_rejected(self):
        # Full fit has rank six, but only one group carries dimension six.
        for sample in self.data['samples'][1:]:
            sample['command_us'][5] = 1500
        with self.assertRaisesRegex(ValueError, 'rank deficient'):
            fit(self.data)

    def test_bad_coordinates_and_command_values(self):
        for value in (-.1, 1.1, float('nan'), float('inf'), True, '0.5'):
            data = copy.deepcopy(self.data)
            data['samples'][0]['points']['wusong_left'][0] = value
            with self.assertRaises(ValueError):
                fit(data)
        self.data['samples'][0]['command_us'][0] = float('inf')
        with self.assertRaises(ValueError):
            fit(self.data)

    def test_duplicate_id_rejected(self):
        self.data['samples'][1]['sample_id'] = '0'
        with self.assertRaisesRegex(ValueError, 'unique'):
            fit(self.data)

    def test_mixed_context_rejected(self):
        for key, value in (('geometry_id', 'different'), ('camera_id', 'different'),
                           ('coordinate_system', 'pixels'), ('simulation_only', False)):
            data = copy.deepcopy(self.data)
            data['samples'][0][key] = value
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                fit(data)

    def test_cli_exclusive_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'input.json', Path(folder) / 'output.json'
            source.write_text(json.dumps(self.data), encoding='utf-8')
            command = [sys.executable, str(MODULE_DIR / 'fit_person_coordinates.py'), str(source), '--output', str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
