"""Offline tests: conjunction geometry, unknown provenance and persistence."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    'mechanism_calibration_model', Path(__file__).parents[1] / 'tools' / 'mechanism_calibration_model.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def snapshot(servo1=1500, rail1=0, rail2=0, mask=1023):
    return m.new_snapshot([servo1] + [1500] * 9, mask, rails={
        'rail1': {'position_mm': rail1, 'origin_known': True, 'position_kind': 'manual_measured'},
        'rail2': {'position_mm': rail2, 'origin_known': True, 'position_kind': 'manual_measured'}})


class CalibrationModelTests(unittest.TestCase):
    def test_unknown_defaults_and_off_history_not_current(self):
        s = m.new_snapshot()
        self.assertEqual(s['pulse_us'], [None] * 10)
        self.assertIsNone(s['feedback'])
        off = snapshot(mask=0)
        self.assertEqual(off['pulse_us'][0], 1500)
        self.assertIsNone(m.axis_value(off, 'servo1'))
        self.assertEqual(m.axis_value(snapshot(mask=1), 'servo1'), 1500)
        self.assertIsNone(m.axis_value(snapshot(mask=1), 'servo2'))

    def test_off_cannot_claim_commanded_current(self):
        s = snapshot()
        s['enabled_mask'] = 0
        with self.assertRaises(ValueError):
            m.validate_snapshot(s)

    def test_explicit_operator_measurement_is_retained(self):
        s = snapshot(mask=0)
        s['servo_provenance'][0] = 'manual_measured'
        m.validate_snapshot(s)
        self.assertEqual(m.axis_value(s, 'servo1'), 1500)

    def test_simulation_is_labelled_and_distinct(self):
        s = snapshot()
        s['servo_provenance'] = ['simulation_command'] * 10
        s['rails']['rail1']['position_kind'] = 'simulated'
        m.validate_snapshot(s)
        self.assertEqual(m.axis_value(s, 'rail1'), 0)

    def test_segment_crossing_is_blocked_even_when_endpoints_outside(self):
        p = m.new_project('rod-length-v1')
        m.add_zone(p, 'crossing', {'servo1': [1490, 1510], 'rail1': [40, 60]})
        result = m.check_move(p, snapshot(1400, 0), snapshot(1600, 100))
        self.assertFalse(result['allowed'])
        self.assertEqual(result['intersections'], ['crossing'])
        self.assertFalse(result['clearance_certified'])

    def test_box_is_conjunction_not_union(self):
        p = m.new_project()
        m.add_zone(p, 'crossing', {'servo1': [1490, 1510], 'rail1': [80, 90]})
        # Each coordinate separately crosses its interval, but never together.
        self.assertTrue(m.check_move(p, snapshot(1400, 0), snapshot(1600, 100))['allowed'])

    def test_closed_box_tangent_and_single_point_are_blocked(self):
        p = m.new_project()
        m.add_zone(p, 'edge', {'servo1': [1500, 1500], 'rail1': [50, 50]})
        self.assertFalse(m.check_move(p, snapshot(1400, 0), snapshot(1600, 100))['allowed'])
        self.assertFalse(m.check_move(p, snapshot(1500, 50), snapshot(1500, 50))['allowed'])

    def test_parallel_segment_outside_box_is_clear_of_recorded_box(self):
        p = m.new_project()
        m.add_zone(p, 'edge', {'servo1': [1550, 1560], 'rail1': [40, 60]})
        self.assertTrue(m.check_move(p, snapshot(1500, 0), snapshot(1500, 100))['allowed'])

    def test_extreme_finite_coordinates_do_not_overflow_segment_math(self):
        p = m.new_project()
        m.add_zone(p, 'crossing', {'rail1': [-10, 10]})
        self.assertFalse(m.check_move(p, snapshot(1500, -1e308), snapshot(1500, 1e308))['allowed'])

    def test_unknown_box_coordinate_blocks(self):
        p = m.new_project()
        m.add_zone(p, 'unknown rail', {'rail1': [10, 20], 'servo1': [1400, 1600]})
        a = snapshot()
        a['rails']['rail1'] = {'position_mm': None, 'origin_known': False, 'position_kind': 'unknown'}
        result = m.check_move(p, a, snapshot(1550, 40))
        self.assertFalse(result['allowed'])
        self.assertIn('unknown', result['reasons'][0])
        result = m.check_move(p, snapshot(mask=0), snapshot())
        self.assertFalse(result['allowed'])

    def test_safe_sample_never_creates_safe_volume(self):
        p = m.new_project()
        m.record_sample(p, snapshot(), 'visible position', 'safe', 'one observed posture')
        self.assertFalse(m.check_move(p, snapshot(), snapshot())['clearance_certified'])
        m.add_zone(p, 'known collision', {'servo1': [1490, 1510]})
        self.assertFalse(m.check_move(p, snapshot(), snapshot())['allowed'])

    def test_limits_opt_in_and_block_unknown(self):
        p = m.new_project()
        m.set_axis_limit(p, 'rail1', 0, 50, enabled=False)
        self.assertTrue(m.check_move(p, snapshot(), snapshot(1500, 100))['allowed'])
        m.set_axis_limit(p, 'rail1', 0, 50)
        self.assertFalse(m.check_move(p, snapshot(), snapshot(1500, 100))['allowed'])
        m.set_axis_limit(p, 'servo1', 1400, 1600)
        self.assertFalse(m.check_move(p, snapshot(mask=0), snapshot())['allowed'])

    def test_geometry_mismatch_is_not_silently_reused(self):
        p = m.new_project('old')
        m.add_zone(p, 'collision', {'servo1': [1500, 1510]})
        p['geometry_id'] = 'new'
        self.assertFalse(m.check_move(p, snapshot(1200), snapshot(1300))['allowed'])
        with self.assertRaises(ValueError):
            m.add_zone(p, 'old', {'servo1': [1400, 1500]}, 'old')

    def test_strict_numbers_and_reversed_bounds(self):
        for value in (True, float('nan'), float('inf'), float('-inf'), '1500'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.new_snapshot([value] + [1500] * 9, 1023)
            with self.subTest(bound=value), self.assertRaises(ValueError):
                m.add_zone(m.new_project(), 'bad', {'rail1': [0, value]})
        for bounds in ({'rail1': [10, 0]}, {'servo4': [499, 1500]}, {'bogus': [0, 1]}):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                m.add_zone(m.new_project(), 'bad', bounds)
        with self.assertRaises(ValueError):
            m.new_snapshot(enabled_mask=True)

    def test_json_roundtrip_and_csv_keeps_all_axes_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = m.new_project('geometry-a')
            p['geometry_notes'] = '杆长与机位记录'
            m.record_sample(p, snapshot(mask=0), '观察', 'near_danger', '离幕距离未测')
            m.add_zone(p, 'danger', {'servo4': [1400, 1600], 'rail2': [1, 4]})
            path = Path(tmp) / 'project.json'
            m.save_project(p, path)
            self.assertEqual(m.load_project(path), p)
            csv_path = Path(tmp) / 'samples.csv'
            m.export_csv(p, csv_path)
            with csv_path.open(encoding='utf-8-sig', newline='') as stream:
                row = list(csv.DictReader(stream))[0]
            self.assertEqual(row['servo10_pulse_us'], '1500')
            self.assertEqual(row['servo1_usable_coordinate_us'], '')
            self.assertEqual(row['servo1_provenance'], 'unknown')
            self.assertEqual(row['rail2_position_kind'], 'manual_measured')
            self.assertEqual(row['notes'], '离幕距离未测')

    def test_atomic_failure_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'project.json'
            p = m.new_project('old')
            m.save_project(p, path)
            newer = m.new_project('new')
            with mock.patch.object(m.os, 'replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    m.save_project(newer, path)
            self.assertEqual(m.load_project(path), p)
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])

    def test_invalid_json_and_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'project.json'
            for text in ('{"schema_version":1,"schema_version":1}', '{"a":NaN}', '{"a":Infinity}'):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    m.load_project(path)
        p = m.new_project()
        p['samples'] = [{'snapshot': None}]
        with self.assertRaises(ValueError):
            m.validate_project(p)
        s = snapshot()
        s['nominal_angle_deg'][0] += 1
        with self.assertRaises(ValueError):
            m.validate_snapshot(s)


if __name__ == '__main__':
    unittest.main()
