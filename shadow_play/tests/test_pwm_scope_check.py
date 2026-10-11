import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/calibration'))
from pwm_scope_check import scope_check


class FakeDevice:
    def __init__(self):
        self.state = dict(identity='SP10', clock_hz=100000000, period_us=20000,
                          armed=False, enabled_mask=0, faults=0, pending=False,
                          sequence=78, pulse_us=[1537,1241,1537,1574,1537,1648,1500,1500,1500,1500])
        self.commits = []; self.off_count = 0; self.commit_error = False

    def status(self): return copy.deepcopy(self.state)

    def commit(self, pulses, mask, allow_arm=False):
        self.commits.append((pulses[:], mask, allow_arm))
        self.state.update(pulse_us=pulses[:], enabled_mask=mask, armed=True, sequence=79)
        if self.commit_error: raise TimeoutError('uncertain adoption')
        return self.status()

    def off(self):
        self.off_count += 1
        self.state.update(enabled_mask=0, armed=False, pending=False)
        return self.status()

    def kick(self): pass


class ScopeCheckTests(unittest.TestCase):
    def run_check(self, device, **overrides):
        ticks = [0.0]
        def sleep(dt): ticks[0] += dt
        options = dict(servo_power_off_confirmed=True, emit=lambda event: None,
                       clock=lambda: ticks[0], sleep=sleep)
        options.update(overrides)
        scope_check(device, 4, 78, 1, **options)

    def test_only_selected_signal_and_preserve_all_existing_pulses(self):
        d = FakeDevice(); initial = d.status()['pulse_us']
        self.run_check(d)
        self.assertEqual(d.commits, [(initial, 8, True)])
        self.assertEqual(d.off_count, 1)
        self.assertFalse(d.state['armed'])

    def test_no_power_confirmation_no_write(self):
        d = FakeDevice()
        with self.assertRaises(ValueError): self.run_check(d, servo_power_off_confirmed=False)
        self.assertEqual((d.commits, d.off_count), ([], 0))

    def test_changed_sequence_or_active_output_rejected_without_write(self):
        for change in ({'sequence': 79}, {'armed': True}, {'enabled_mask': 8}, {'faults': 2}):
            d = FakeDevice(); d.state.update(change)
            with self.assertRaises(RuntimeError): self.run_check(d)
            self.assertEqual((d.commits, d.off_count), ([], 0))

    def test_uncertain_commit_stops_without_retry(self):
        d = FakeDevice(); d.commit_error = True
        with self.assertRaises(TimeoutError): self.run_check(d)
        self.assertEqual(len(d.commits), 1)
        self.assertEqual(d.off_count, 1)

    def test_interrupt_stops_output(self):
        d = FakeDevice()
        def interrupt(_): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.run_check(d, sleep=interrupt)
        self.assertEqual(d.off_count, 1)

    def test_fault_during_hold_stops_without_rearm(self):
        d = FakeDevice()
        def fault(_): d.state['faults'] = 2
        with self.assertRaises(RuntimeError): self.run_check(d, sleep=fault)
        self.assertEqual(len(d.commits), 1)
        self.assertEqual(d.off_count, 1)


if __name__ == '__main__': unittest.main()
