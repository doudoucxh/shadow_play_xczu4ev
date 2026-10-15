"""Read-only GUI reporting and board lock rejection; no hardware."""
import sys
import queue
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from servo_center_session import CenterSession, MotionInhibitedError
from servo_manual_session import person_command_report
from servo_center_gui import Worker


class ReportingTests(unittest.TestCase):
    def test_worker_keeps_connection_after_lock_rejection(self):
        commands, events = queue.Queue(), queue.Queue()
        worker = Worker(commands, events)
        session = Mock()
        worker.session = session
        session.move.side_effect = MotionInhibitedError('PWM motion inhibited by test')
        session.status.return_value = dict(armed=False, enabled_mask=0, pending=False)
        commands.put(('move', (1, 1500)))
        commands.put(('shutdown', None))
        worker.run()
        received = []
        while not events.empty():
            received.append(events.get()[0])
        self.assertEqual(received, ['snapshot', 'motion_blocked', 'closed'])
        session.close.assert_called_once()  # Only explicit shutdown releases it.

    def test_explicit_lock_has_separate_exception(self):
        session = object.__new__(CenterSession)
        session.link = Mock()
        session.link.exchange.return_value = {'ok': False, 'error':
            'PWM motion inhibited by /run/shadow-pwm-motion-inhibit; status and OFF remain available'}
        with self.assertRaises(MotionInhibitedError):
            session._request('move', {})
        session.link.close.assert_not_called()

    def test_other_errors_remain_errors(self):
        session = object.__new__(CenterSession)
        session.link = Mock()
        session.link.exchange.return_value = {'ok': False, 'error': 'transport failed'}
        with self.assertRaises(RuntimeError) as error:
            session._request('status', {})
        self.assertNotIsInstance(error.exception, MotionInhibitedError)

    def test_off_snapshot_is_not_an_actual_start(self):
        report = person_command_report(dict(pulse_us=[1500]*10, sequence=34017,
                                            armed=False, enabled_mask=0))
        self.assertEqual(report.count('不能作起点'), 6)
        self.assertNotIn('正在输出', report)

    def test_only_enabled_channel_is_active(self):
        state = dict(pulse_us=[1500]*10, sequence=1, armed=True,
                     enabled_mask=2, pending=False, faults=0)
        self.assertEqual(person_command_report(state).count('正在输出'), 1)
        state['pending'] = True
        self.assertNotIn('正在输出', person_command_report(state))


if __name__ == '__main__':
    unittest.main()
