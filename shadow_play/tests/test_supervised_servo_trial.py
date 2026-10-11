import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from supervised_servo_trial import trial


class FakeDevice:
    def __init__(self):
        self.state = dict(identity='SP10', clock_hz=100000000, period_us=20000,
                          armed=False, enabled_mask=0, pending=False, faults=0,
                          pulse_us=[1500]*10)
        self.commits = []; self.off_count = 0; self.kicks = 0
        self.commit_error = False; self.watchdog = False

    def status(self): return copy.deepcopy(self.state)

    def commit(self, pulses, mask, allow_arm=False):
        self.commits.append((pulses[:], mask, allow_arm))
        self.state.update(armed=True, enabled_mask=mask, pulse_us=pulses[:])
        if self.commit_error: raise TimeoutError('uncertain commit')
        return self.status()

    def kick(self):
        self.kicks += 1
        if self.watchdog: self.state.update(armed=False, enabled_mask=0, faults=2)

    def off(self):
        self.off_count += 1
        self.state.update(armed=False, enabled_mask=0, pending=False)
        return self.status()


class TrialTests(unittest.TestCase):
    def run_trial(self, d, **kwargs):
        return trial(d, 1, 1500, observer_present=True,
                     estimated_start_authorized=True, **kwargs)

    def test_missing_authorization_and_invalid_request_do_not_write(self):
        d = FakeDevice()
        for kwargs in ({}, {'observer_present': True},
                       {'observer_present': True, 'estimated_start_authorized': 'yes'}):
            with self.assertRaises(ValueError): trial(d, 1, 1500, **kwargs)
        for duration in (0, 3, float('nan'), True):
            with self.assertRaises(ValueError): self.run_trial(d, hold_seconds=duration)
        self.assertFalse(d.commits); self.assertEqual(d.off_count, 0)

    def test_does_not_take_over_active_or_faulted_outputs(self):
        for field, value in (('armed', True), ('enabled_mask', 2), ('faults', 2),
                             ('pending', True), ('period_us', 10000)):
            d = FakeDevice(); d.state[field] = value
            with self.assertRaises(RuntimeError): self.run_trial(d)
            self.assertFalse(d.commits); self.assertEqual(d.off_count, 0)

    def test_only_one_channel_then_off_and_never_claims_actual_position(self):
        d = FakeDevice(); events = []
        with patch('supervised_servo_trial.time.monotonic', side_effect=[0, 2]):
            self.run_trial(d, emit=events.append)
        self.assertEqual(d.commits, [([1500]*10, 1, True)])
        self.assertEqual(d.off_count, 1); self.assertFalse(d.state['armed'])
        self.assertIs(events[0]['actual_position_verified'], False)
        self.assertEqual(events[-1]['event'], 'outputs_off')

    def test_uncertain_commit_and_observer_error_always_turn_off_no_retry(self):
        d = FakeDevice(); d.commit_error = True
        with self.assertRaises(TimeoutError): self.run_trial(d)
        self.assertEqual(len(d.commits), 1); self.assertEqual(d.off_count, 1)
        d = FakeDevice()
        def fail_on_adopted(event):
            if event['event'] == 'adopted': raise RuntimeError('observer failed')
        with self.assertRaises(RuntimeError): self.run_trial(d, emit=fail_on_adopted)
        self.assertEqual(len(d.commits), 1); self.assertEqual(d.off_count, 1)

    def test_watchdog_expiry_never_rearms(self):
        d = FakeDevice(); d.watchdog = True
        with patch('supervised_servo_trial.time.monotonic', side_effect=[0, .1, .2]), \
                patch('supervised_servo_trial.time.sleep'):
            with self.assertRaises(RuntimeError): self.run_trial(d)
        self.assertEqual(len(d.commits), 1); self.assertEqual(d.off_count, 1)
        self.assertEqual(d.kicks, 1)


if __name__ == '__main__': unittest.main()
