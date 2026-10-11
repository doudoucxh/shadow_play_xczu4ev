import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from check_stage_reference import compare


class StageReferenceCheckTests(unittest.TestCase):
    def setUp(self):
        self.reference = np.random.RandomState(20261011).uniform(20, 180, (100, 160))
        self.spec = {'image_width': 160, 'image_height': 100,
                     'reference_pixels': [[30, 70], [130, 70], [130, 30], [30, 30]]}

    def test_static_image_with_gain_and_offset_preserves_anchors(self):
        report = compare(self.spec, self.reference, 1.2*self.reference+10)
        self.assertTrue(report['same_view_candidate'])
        self.assertTrue(all(a['shift_px'] == [0, 0] for a in report['anchors']))
        self.assertFalse(report['motion_permission'])
        self.assertFalse(report['actual_servo_position_known'])

    def test_known_camera_translation_requires_reference_review(self):
        moved = np.roll(np.roll(self.reference, 4, axis=1), -3, axis=0)
        report = compare(self.spec, self.reference, moved)
        self.assertFalse(report['same_view_candidate'])
        self.assertTrue(all(a['shift_px'] == [4, -3] for a in report['anchors']))

    def test_occluded_marker_does_not_pass_with_other_markers_visible(self):
        occluded = self.reference.copy()
        occluded[52:89, 112:149] = 90
        report = compare(self.spec, self.reference, occluded)
        self.assertFalse(report['same_view_candidate'])
        self.assertFalse(report['anchors'][1]['within_diagnostic_tolerance'])

    def test_missing_contrast_or_changed_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            compare(self.spec, np.zeros_like(self.reference), self.reference)
        with self.assertRaises(ValueError):
            compare(self.spec, self.reference, self.reference[:90])

    def test_invalid_marker_coordinates_are_rejected(self):
        self.spec['reference_pixels'][0] = [float('nan'), 70]
        with self.assertRaises(ValueError):
            compare(self.spec, self.reference, self.reference)
        self.spec['reference_pixels'][0] = [5, 70]
        with self.assertRaises(ValueError):
            compare(self.spec, self.reference, self.reference)


if __name__ == '__main__':
    unittest.main()
