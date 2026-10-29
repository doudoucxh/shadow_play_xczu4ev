"""Playback clock, segment boundaries and GUI-worker reporting, without hardware."""
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.gui import Worker
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.session import TeachingSession
from shadow_play.bus_servo.timeline import PlaybackTimeline, format_time
from shadow_play.tests.test_bus_servo import recording


PROFILE = Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class TimelineTests(unittest.TestCase):
    def test_speed_and_nonzero_acquisition_origin(self):
        record = {'samples': [{'t': .05}, {'t': 10.05}]}
        for speed in (.25, .5, 1, 2):
            timeline = PlaybackTimeline(record, speed)
            p = timeline.snapshot(5/speed, 'playing')
            self.assertAlmostEqual(p['duration_s'], 10/speed)
            self.assertAlmostEqual(p['source_s'], 5)
            self.assertAlmostEqual(p['fraction'], .5)

    def test_deadline_is_not_final_position_confirmation(self):
        timeline = PlaybackTimeline({'samples': [{'t': 0}, {'t': .3333}]}, 1, .333)
        self.assertEqual(timeline.snapshot(2, 'playing')['state'], 'checking')
        complete = timeline.snapshot(2, 'completed')
        self.assertEqual(complete['elapsed_s'], .333)
        self.assertEqual(complete['source_s'], .3333)
        self.assertEqual(complete['fraction'], 1)
        self.assertEqual(timeline.snapshot(-1)['fraction'], 0)

    def test_segment_boundary_and_last_segment(self):
        timeline = PlaybackTimeline({'samples': [{'t': 0}, {'t': 10}], 'segments_summary': [
            {'name': '起势', 'end_s': 2}, {'name': '动作', 'end_s': 8}, {'name': '收势', 'end_s': 10}]}, .5)
        self.assertIn('起势', timeline.snapshot(3.9)['segment'])
        self.assertIn('第 2/3 段 · 动作', timeline.snapshot(4)['segment'])
        self.assertIn('收势', timeline.snapshot(20, 'completed')['segment'])

    def test_empty_or_one_frame_and_time_format(self):
        for samples in ([], [{'t': .1}]):
            p = PlaybackTimeline({'samples': samples}, .5).snapshot()
            self.assertEqual(p['duration_s'], 0)
            self.assertEqual(p['fraction'], 0)
        self.assertEqual(format_time(59.99), '00:59.9')
        self.assertEqual(format_time(60), '01:00.0')
        self.assertEqual(format_time(6000), '100:00.0')

    def worker_run(self, fail_final=False):
        profile = Profile.load(PROFILE); record = recording(profile)
        now = [0.0]; events = queue.Queue(); moves = []

        class Device(SimulationDevice):
            def move(self, targets, milliseconds):
                moves.append((targets, milliseconds))
                super().move(targets, milliseconds)

            def read(self, numbers):
                if fail_final and now[0] >= .8:
                    raise TimeoutError('final feedback unavailable')
                return super().read(numbers)

        script = iter([(0, 'connect', (profile, True, 'unused')),
                       (0, 'select', [1, 7]), (0, 'play', (record, [1, 7], .5)),
                       *[(t, None, None) for t in (.1, .201, .3, .401, .5, .601, .7, .801)],
                       (.9, 'shutdown', None)])

        class Commands:
            def get(self, timeout):
                at, op, value = next(script); now[0] = at
                return op, value

        worker = Worker(Commands(), events, threading.Event())
        with patch('shadow_play.bus_servo.gui.SimulationDevice', Device), \
                patch('shadow_play.bus_servo.gui.TeachingSession',
                      side_effect=lambda p, d, directory: TeachingSession(p, d, directory, clock=lambda: now[0])), \
                patch('shadow_play.bus_servo.device.time.monotonic', side_effect=lambda: now[0]):
            worker.run()
        messages = []
        while not events.empty():messages.append(events.get_nowait())
        return messages, moves

    def test_worker_reports_actual_session_clock_without_extra_moves(self):
        messages, moves = self.worker_run()
        progress = [value for kind, value in messages if kind in ('playing', 'playback_progress')]
        self.assertEqual(progress[0]['elapsed_s'], 0)
        self.assertEqual(progress[-1]['state'], 'completed')
        self.assertEqual(progress[-1]['fraction'], 1)
        elapsed = [p['elapsed_s'] for p in progress]
        self.assertEqual(elapsed, sorted(elapsed))
        self.assertEqual(len(moves), 4)
        self.assertTrue(all(ms == 200 for _, ms in moves))
        self.assertFalse(any(kind == 'error' for kind, _ in messages))

    def test_failed_final_feedback_never_reports_completed(self):
        messages, moves = self.worker_run(fail_final=True)
        progress = [value for kind, value in messages if kind == 'playback_progress']
        self.assertTrue(any(kind == 'error' for kind, _ in messages))
        self.assertFalse(any(p['state'] == 'completed' for p in progress))
        self.assertLess(progress[-1]['elapsed_s'], .8)
        self.assertEqual(len(moves), 4)


if __name__ == '__main__':unittest.main()
