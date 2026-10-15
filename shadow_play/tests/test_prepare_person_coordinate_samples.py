import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'integrations/calibration/prepare_person_coordinate_samples.py'
spec = importlib.util.spec_from_file_location('prepare_coordinates', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrepareTests(unittest.TestCase):
    def test_candidates_never_become_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'front.jpg').touch()
            (root/'top.jpg').touch()
            phase = {'command_pulses_us': [1500]*10,
                     'frame_evidence': {'front': {'file': 'front.jpg'}, 'top': {'file': 'top.jpg'}}}
            record = root/'record.json'
            record.write_text(json.dumps({'phases': [phase]}))
            result = module.prepare([record], root)
            self.assertEqual(result['coverage']['resolved_dual_frame_count'], 1)
            self.assertFalse(result['context_verified'])
            self.assertFalse(result['samples'][0]['command_frame_pair_verified'])
            self.assertTrue(all(v is None for v in result['samples'][0]['points'].values()))
            (root/'duplicate').mkdir()
            (root/'duplicate/front.jpg').touch()
            result = module.prepare([record], root)
            self.assertIsNone(result['samples'][0]['evidence']['front_file'])
            self.assertEqual(result['coverage']['resolved_dual_frame_count'], 0)

    def test_invalid_command_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root/'record.json'
            record.write_text(json.dumps({'checkpoints': [{'command_pulses_us': [True]*10}]}))
            with self.assertRaises(ValueError):
                module.prepare([record], root)


if __name__ == '__main__':
    unittest.main()
