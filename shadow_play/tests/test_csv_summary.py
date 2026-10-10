"""Regression for speed validation of six-decimal realtime CSV recordings."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('pc_check', Path(__file__).resolve().parents[1] / 'tools/pc_check.py')
pc_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc_check)


class CsvRoundingTests(unittest.TestCase):
    def check(self, final_angle, final_time='0.540098'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'angles.csv'
            path.write_text('time_s,axis_id,angle_deg,mode,input_state\n'
                            '0.520086,left,97.196179,camera,tracking_or_holding\n'
                            f'{final_time},left,{final_angle},camera,tracking_or_holding\n')
            return pc_check.csv_summary(path, {'left': dict(min_deg=0, max_deg=180, max_speed_deg_s=90)})

    def test_actual_realtime_rounding(self):
        self.assertEqual(self.check('98.997324')['samples'], 2)

    def test_excess_beyond_rounding_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'speed limit'):
            self.check('98.998324')

    def test_non_increasing_time_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'time did not increase'):
            self.check('97.196179', '0.520086')


if __name__ == '__main__':
    unittest.main()
