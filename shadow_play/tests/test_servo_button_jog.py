"""Bounded button targets plus real Tk event state with no serial worker."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from servo_button_jog import load_button_limits, next_button_pulse, checked_target, STEP_US
from servo_manual_session import pulse_to_angle


class LimitsTests(unittest.TestCase):
    def test_all_ten_ranges_are_rounded_inward_with_ten_degree_margin(self):
        limits = load_button_limits()
        angles = [(10,260),(95,260),(10,260),(50,170),(70,260),
                  (50,170),(50,190),(100,190),(70,200),(50,170)]
        for channel, (low, high) in enumerate(angles, 1):
            first, last = limits[channel]
            self.assertGreaterEqual(pulse_to_angle(first), low)
            self.assertLessEqual(pulse_to_angle(last), high)
            self.assertLess(pulse_to_angle(first)-low, .136)
            self.assertLess(high-pulse_to_angle(last), .136)
            self.assertEqual(checked_target(limits, channel, 1500), 1500)

    def test_steps_never_cross_either_limit_and_stop_at_limit(self):
        limits = load_button_limits()
        for channel, (low, high) in limits.items():
            for start in range(low, high+1):
                for direction in (-1, 1):
                    target = next_button_pulse(limits, channel, start, direction)
                    self.assertTrue(low <= target <= high)
                    self.assertTrue(0 <= direction*(target-start) <= STEP_US)
            self.assertEqual(next_button_pulse(limits, channel, low, -1), low)
            self.assertEqual(next_button_pulse(limits, channel, high, 1), high)

    def test_out_of_range_start_never_jumps_back_into_range(self):
        limits = load_button_limits()
        for channel, (low, high) in limits.items():
            for start in (low-1, high+1):
                with self.assertRaises(ValueError): next_button_pulse(limits, channel, start, 1)
        for direction in (0, 2, True, 1.0):
            with self.assertRaises(ValueError): next_button_pulse(limits, 1, 1500, direction)


class NoHardwareWorker:
    def __init__(self, commands, events): pass
    def start(self): pass


class ButtonUiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from servo_manual_gui import ManualApp
        self.root = tk.Tk()
        with patch.object(ManualApp, 'worker_class', NoHardwareWorker):
            self.app = ManualApp(self.root)
        self.root.update_idletasks()
        self.app.connected = True
        self.app.control_mode.set('button')
        self.app.control_mode_changed()
        self.app.confirmed.set(True)
        self.sequence = 0
        self.ack(1500)

    def tearDown(self):
        self.app.release_press()
        self.root.update_idletasks()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def ack(self, pulse):
        self.sequence += 1
        state = dict(armed=True, enabled_mask=1, pending=False, faults=0,
                     sequence=self.sequence, pulse_us=[pulse]+[1500]*9)
        self.app.events.put(('active', (1, state)))
        self.app.receive()

    def test_press_sends_one_step_and_no_more_until_ack(self):
        self.app.start_press(1)
        self.assertEqual(self.app.commands.get_nowait(), ('move', (1, 1508)))
        self.assertTrue(self.app.busy)
        self.app.press_step()
        self.assertTrue(self.app.commands.empty())
        self.ack(1508)
        self.assertIsNotNone(self.app.press_job)
        self.root.after_cancel(self.app.press_job)
        self.app.press_step()
        self.assertEqual(self.app.commands.get_nowait(), ('move', (1, 1516)))

    def test_release_during_pending_ack_does_not_resume(self):
        self.app.start_press(-1)
        self.assertEqual(self.app.commands.get_nowait(), ('move', (1, 1492)))
        self.app.release_press()
        self.ack(1492)
        self.assertIsNone(self.app.press_job)
        self.app.press_step()
        self.assertTrue(self.app.commands.empty())
        self.assertEqual(self.app.holding_channel, 1)

    def test_stop_cancels_repeat_and_only_queues_stop(self):
        self.app.start_press(1)
        self.app.commands.get_nowait()
        self.ack(1508)
        self.app.stop()
        self.assertEqual(self.app.commands.get_nowait(), ('stop', None))
        self.assertIsNone(self.app.press_job)
        self.assertEqual(self.app.press_direction, 0)
        self.ack(1508)
        self.assertIsNone(self.app.press_job)
        self.assertTrue(self.app.commands.empty())

    def test_window_focus_loss_cancels_repeat(self):
        self.app.start_press(1)
        self.app.commands.get_nowait()
        self.ack(1508)
        with patch.object(self.root, 'focus_displayof', return_value=None):
            self.app.check_press_focus()
        self.assertEqual(self.app.press_direction, 0)
        self.assertIsNone(self.app.press_job)

    def test_actual_mouse_leave_binding_cancels_repeat(self):
        self.app.start_press(1)
        self.app.commands.get_nowait()
        self.ack(1508)
        self.app.press_buttons[1].event_generate('<Leave>')
        self.assertEqual(self.app.press_direction, 0)
        self.assertIsNone(self.app.press_job)

    def test_actual_mouse_release_binding_cancels_repeat(self):
        self.app.start_press(1)
        self.app.commands.get_nowait()
        self.ack(1508)
        self.app.press_buttons[1].event_generate('<ButtonRelease-1>')
        self.assertEqual(self.app.press_direction, 0)
        self.assertIsNone(self.app.press_job)

    def test_idle_unconfirmed_disconnected_and_outside_range_cannot_move(self):
        self.app.holding_channel = None
        self.app.start_press(1)
        self.assertTrue(self.app.commands.empty())
        self.app.holding_channel = 1
        self.app.confirmed.set(False)
        self.app.start_press(1)
        self.assertTrue(self.app.commands.empty())
        self.app.confirmed.set(True)
        self.app.connected = False
        self.app.start_press(1)
        self.assertTrue(self.app.commands.empty())
        self.app.connected = True
        self.app.latest['pulse_us'][0] = 500
        self.app.start_press(1)
        self.assertTrue(self.app.commands.empty())
        self.assertEqual(self.app.press_direction, 0)

    def test_boundary_stops_without_another_command(self):
        high = self.app.button_limits[1][1]
        self.app.latest['pulse_us'][0] = high
        self.app.start_press(1)
        self.assertTrue(self.app.commands.empty())
        self.assertEqual(self.app.press_direction, 0)

    def test_mode_and_selection_changes_clear_confirmation(self):
        self.app.control_mode.set('target')
        self.app.control_mode_changed()
        self.assertFalse(self.app.confirmed.get())
        self.app.confirmed.set(True)
        self.app.number.set(4)
        self.app.selection_changed()
        self.assertFalse(self.app.confirmed.get())
        self.assertIn('G13', self.app.selected.get())

    def test_numeric_entry_in_button_mode_cannot_bypass_limits(self):
        self.app.angle.set('0')
        self.app.send_target()
        self.assertTrue(self.app.commands.empty())
        self.assertIn('超出', self.app.state.get())

    def test_disconnect_and_error_cancel_scheduled_steps(self):
        self.app.start_press(1)
        self.app.commands.get_nowait()
        self.ack(1508)
        self.app.on_event('error', 'test failure')
        self.assertEqual(self.app.press_direction, 0)
        self.assertIsNone(self.app.press_job)
        self.assertIsNone(self.app.latest)

    def test_mode_controls_and_stop_button_fit_in_window(self):
        self.root.update()
        self.assertTrue(self.app.press_buttons[1].winfo_viewable())
        self.assertTrue(self.app.stop_button.winfo_viewable())
        self.assertLessEqual(self.app.history.winfo_rooty()+self.app.history.winfo_height(),
                             self.root.winfo_rooty()+self.root.winfo_height())
        self.assertLessEqual(self.root.winfo_rooty()+self.root.winfo_height(), self.root.winfo_screenheight()-35)


if __name__ == '__main__':
    unittest.main()
