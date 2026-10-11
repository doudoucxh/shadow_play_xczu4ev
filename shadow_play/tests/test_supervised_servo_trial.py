import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / 'integrations/calibration'
sys.path.insert(0, str(SOURCE))
from supervised_servo_trial import trial


class RetiredTrialTests(unittest.TestCase):
    def test_imported_trial_rejects_even_authorized_without_touching_device(self):
        device = Mock()
        with self.assertRaisesRegex(RuntimeError, 'disabled after puppet pulling'):
            trial(device, 7, 1500, observer_present=True,
                  estimated_start_authorized=True, hold_seconds=2)
        self.assertEqual(device.mock_calls, [])

    def test_execute_fails_without_loading_mmio_driver(self):
        result = subprocess.run([sys.executable, str(SOURCE / 'supervised_servo_trial.py'),
                                 '--channel', '7', '--pulse-us', '1500', '--execute',
                                 '--observer-present', '--estimated-start-authorized'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('disabled after puppet pulling', result.stderr)
        self.assertNotIn('/dev/mem', result.stderr)
        self.assertNotIn('servo_pwm_device', result.stderr)

    def test_dry_run_is_explicitly_non_executable(self):
        result = subprocess.run([sys.executable, str(SOURCE / 'supervised_servo_trial.py'),
                                 '--channel', '7', '--pulse-us', '1500'],
                                capture_output=True, text=True, check=True)
        row = json.loads(result.stdout)
        self.assertIs(row['execution_allowed'], False)
        self.assertIs(row['actual_position_verified'], False)


if __name__ == '__main__':
    unittest.main()
