import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import capture_supervised_plan as capture


class MotionStopTests(unittest.TestCase):
    def test_missing_invalid_or_active_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stop.json'
            with self.assertRaises(RuntimeError): capture.require_motion_review_clear(path)
            for data in ('{', '[]', '{}', '{"schema_version":1,"active":0}',
                         '{"schema_version":1,"active":true}'):
                path.write_text(data, encoding='utf-8')
                with self.assertRaises(RuntimeError): capture.require_motion_review_clear(path)

    def test_explicit_review_clear_can_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stop.json'
            path.write_text(json.dumps({'schema_version': 1, 'active': False}), encoding='utf-8')
            capture.require_motion_review_clear(path)

    def test_current_incident_locks_real_cli_before_io(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'capture'
            argv = ['capture', '--board-plan', '/tmp/test.json', '--output', str(output)]
            with patch.object(sys, 'argv', argv), \
                    patch.object(capture.urllib.request, 'urlopen') as camera, \
                    patch.object(capture.threading, 'Thread') as worker:
                with self.assertRaisesRegex(RuntimeError, 'Loaded motion is stopped'):
                    capture.main()
                camera.assert_not_called()
                worker.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
