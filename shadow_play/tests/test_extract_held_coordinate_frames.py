import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/calibration'))
from extract_held_coordinate_frames import extract


class HeldFrameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events, self.frames = [], []

    def event(self, time, pulse=1500, active=True):
        self.events.append(dict(host_unix_ms=time, state=dict(pulse_us=[pulse]*10,
                           enabled_mask=1023 if active else 0, armed=active)))

    def frame(self, time, camera, age=0, fid=None):
        name = '{}_{}.jpg'.format(camera, len(self.frames))
        Image.new('RGB', (4, 4), 'white').save(self.root / name)
        self.frames.append(dict(camera=camera, file=name, host_unix_ns=int(time*1e6),
                                age_ms=age, frame_id=fid or name))

    def run_extract(self):
        for name, rows in [('events', self.events), ('frames', self.frames)]:
            (self.root / (name+'.jsonl')).write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
        return extract([self.root])

    def test_same_status_does_not_restart_hold_and_center_pair_chosen(self):
        self.event(1000)
        self.event(4000)
        self.event(7000, active=False)
        for time in [2000, 3100, 4750, 6400, 6800]:
            self.frame(time, 'front')
            self.frame(time+10, 'top')
        report = self.run_extract()
        self.assertEqual(len(report['windows']), 1)
        window = report['windows'][0]
        self.assertEqual(window['start_host_unix_ms'], 1000)
        self.assertEqual(window['frames']['front']['host_unix_ms'], 4750)
        self.assertFalse(window['command_frame_pair_verified'])
        self.assertFalse(report['deployment_ready'])

    def test_short_and_unterminated_holds_ignored(self):
        self.event(1000)
        self.event(3000, 1510)
        self.frame(6000, 'front')
        self.frame(6010, 'top')
        report = self.run_extract()
        self.assertFalse(report['windows'])
        self.assertTrue(any(s['reason'] == 'unterminated_final_hold' for s in report['skipped']))

    def test_off_separates_identical_commands(self):
        self.event(1000)
        self.event(2000, active=False)
        self.event(2100)
        self.event(5000, active=False)
        self.frame(3500, 'front')
        self.frame(3510, 'top')
        self.assertFalse(self.run_extract()['windows'])

    def test_exposure_age_and_pair_separation(self):
        self.event(1000)
        self.event(7000, active=False)
        self.frame(4000, 'front', age=1500)  # Exposure before start guard.
        self.frame(4010, 'top')
        self.frame(5000, 'front')  # No top within 100 ms.
        self.assertFalse(self.run_extract()['windows'])

    def test_bad_age_duplicate_missing_and_bad_jpeg_rejected(self):
        self.event(1000)
        self.event(7000, active=False)
        self.frame(2000, 'front', fid='same')
        self.frame(4500, 'front', fid='same')
        self.frame(4500, 'top', age=-1)
        self.frame(4501, 'top')
        (self.root / self.frames[-1]['file']).write_bytes(b'broken')
        self.frame(4502, 'top')
        (self.root / self.frames[-1]['file']).unlink()
        self.frame(4500, 'front', fid='valid_front')
        report = self.run_extract()
        self.assertFalse(report['windows'])
        reasons = {s['reason'] for s in report['skipped']}
        self.assertTrue({'duplicate_or_stale_frame_id', 'invalid_host_time_or_negative_age',
                         'jpeg_decode_failed', 'missing_or_outside_session_file'} <= reasons)

    def test_lazy_decode_only_center_pair_and_fallback(self):
        self.event(1000)
        self.event(7000, active=False)
        for time in (3100, 4000, 4750, 6000):
            self.frame(time, 'front')
            self.frame(time, 'top')
        with patch('extract_held_coordinate_frames.Image.open', wraps=Image.open) as opened:
            report = self.run_extract()
            self.assertEqual(opened.call_count, 2)
        self.assertEqual(report['windows'][0]['frames']['front']['host_unix_ms'], 4750)
        (self.root / self.frames[4]['file']).write_bytes(b'bad closest JPEG')
        with patch('extract_held_coordinate_frames.Image.open', wraps=Image.open) as opened:
            report = self.run_extract()
            self.assertEqual(opened.call_count, 4)
        self.assertEqual(report['windows'][0]['frames']['front']['host_unix_ms'], 4000)
        self.assertTrue(any(s['reason'] == 'jpeg_decode_failed' for s in report['skipped']))

    def test_missing_event_time_and_invalid_state_fail_closed(self):
        self.event(1000)
        del self.events[0]['host_unix_ms']
        with self.assertRaisesRegex(ValueError, 'host_unix_ms'):
            self.run_extract()
        self.events[0]['host_unix_ms'] = 1000
        self.events[0]['state']['pulse_us'] = [1500]
        with self.assertRaisesRegex(ValueError, 'complete state'):
            self.run_extract()

    def test_any_of_ten_axes_change_splits_hold(self):
        self.event(1000)
        self.event(4000)
        self.events[-1]['state']['pulse_us'][9] = 1510
        self.event(8000, active=False)
        self.frame(6100, 'front')
        self.frame(6150, 'top')
        window = self.run_extract()['windows'][0]
        self.assertEqual(window['start_host_unix_ms'], 4000)
        self.assertEqual(window['commands'][9], 1510)

    def test_cli_does_not_overwrite(self):
        self.event(1000)
        self.event(7000, active=False)
        self.run_extract()
        output = self.root / 'report.json'
        command = [sys.executable, str(Path(__file__).resolve().parents[1] /
                   'integrations/calibration/extract_held_coordinate_frames.py'),
                   str(self.root), '--output', str(output)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(original, output.read_bytes())


if __name__ == '__main__':
    unittest.main()
