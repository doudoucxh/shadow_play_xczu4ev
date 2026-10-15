import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('annotate', Path(__file__).resolve().parents[1] /
    'integrations/calibration/annotate_person_coordinates.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AnnotationTests(unittest.TestCase):
    def test_axes_and_missing_point(self):
        result = module.normalize([[10,110],[210,110],[210,10],[10,10]],
                                  {'wusong_left': [60,85], 'wusong_neck': [110,60]})
        self.assertAlmostEqual(result['wusong_left'][0], .25)
        self.assertAlmostEqual(result['wusong_left'][1], .25)
        self.assertAlmostEqual(result['wusong_neck'][1], .5)
        self.assertIsNone(result['wusong_right'])

    def test_degenerate_and_outside_rejected(self):
        with self.assertRaises(ValueError):
            module.normalize([[0,0]]*4, {})
        with self.assertRaises(ValueError):
            module.normalize([[0,100],[100,100],[100,0],[0,0]], {'wusong_left': [101,50]})

    def test_annotations_do_not_verify_pairing_or_context(self):
        dataset = {'context_verified': False, 'samples': [{'sample_id': 'a',
            'evidence': {'front_file': 'a.jpg'}, 'command_frame_pair_verified': False}]}
        item = {'sample_id': 'a', 'front_file': 'a.jpg', 'corners_px': [[0,100],[100,100],[100,0],[0,0]],
                'points_px': {'wusong_left': [50,50]}, 'annotation_verified': True}
        result = module.annotate(dataset, [item])
        self.assertFalse(result['context_verified'])
        self.assertFalse(result['samples'][0]['command_frame_pair_verified'])
        self.assertNotIn('points', dataset['samples'][0])
        item['front_file'] = 'wrong.jpg'
        with self.assertRaises(ValueError):
            module.annotate(dataset, [item])


if __name__ == '__main__':
    unittest.main()
