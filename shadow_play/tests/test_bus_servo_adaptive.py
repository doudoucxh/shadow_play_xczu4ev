"""Measured following error must stretch replay, never increase speed."""
import copy
import hashlib
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch

from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.service import Controller, ADAPTIVE_PLAYBACK
from shadow_play.bus_servo.session import PlaybackRejected
from shadow_play.bus_servo.transport import RemoteDevice
from shadow_play.tests import test_bus_servo_scheduling as scheduling
from shadow_play.tools.prepare_bus_console import build

PROFILE = Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class AdaptiveControllerTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.load(PROFILE)
        self.device = SimulationDevice(self.profile)
        self.controller = Controller(self.profile, self.device)
        self.device.move = Mock()

    def move(self, targets, ms, adaptive=True):
        return self.controller.execute(dict(seq=self.controller.last_sequence+1, op='move',
            payload=dict(targets=targets, duration_ms=ms, adaptive_duration=adaptive, attended=True)))

    def test_two_count_following_error_at_speed_boundary_stretches_group(self):
        # Planned 1500 -> 1600 takes 450ms, actual start 1498 needs 459ms.
        self.device.positions[7] = 1498
        with self.assertRaisesRegex(ValueError, 'Axis 7: increase move duration'):
            self.move({'1':1500, '7':1600}, 450, False)
        self.device.move.assert_not_called()
        result = self.move({'1':1500, '7':1600}, 450)
        self.assertEqual(result['duration_ms'], 459)
        self.assertEqual(result['requested_duration_ms'], 450)
        self.device.move.assert_called_once_with({'1':1500, '7':1600}, 459)

    def test_largest_selected_distance_sets_shared_duration_and_never_shortens(self):
        result = self.move({'1':1510, '7':1700}, 100)
        self.assertEqual(result['duration_ms'], 900)
        self.assertEqual(self.move({'1':1510}, 2000)['duration_ms'], 2000)

    def test_invalid_last_axis_prevents_entire_group_dispatch(self):
        with self.assertRaises(ValueError): self.move({'1':1510, '7':2500}, 100)
        self.device.move.assert_not_called()

    def test_duration_bound_and_boolean_are_enforced_before_dispatch(self):
        data = copy.deepcopy(self.profile.data)
        for row in data['axes']: row['max_speed_deg_s'] = 1
        self.controller = Controller(Profile(data), self.device)
        with self.assertRaisesRegex(ValueError, '9999'): self.move({'7':1700}, 100)
        with self.assertRaisesRegex(ValueError, 'boolean'): self.move({'7':1510}, 100, 1)
        self.device.move.assert_not_called()

    def test_failed_feedback_does_not_dispatch_or_retry(self):
        self.device.read = Mock(side_effect=TimeoutError('lost feedback'))
        with self.assertRaises(TimeoutError): self.move({'7':1600}, 450)
        self.device.read.assert_called_once_with([7])
        self.device.move.assert_not_called()


class AdaptiveSchedulingTests(unittest.TestCase):
    setUp = scheduling.SchedulingTests.setUp
    tearDown = scheduling.SchedulingTests.tearDown

    def test_extended_ack_duration_controls_send_deadline_and_cursor(self):
        original = self.device.move
        def extended(targets, ms):
            original(targets, ms*3)
            return {'sent':True, 'duration_ms':ms*3}
        self.device.playback_move = extended
        s = self.session
        s.tick([1,7]); ack = self.now[0]
        self.assertEqual(s.segment_duration_ms, 600)
        self.now[0] = ack+.3
        self.assertAlmostEqual(s.playback_elapsed(), .1)
        s.next_poll = s.next_board_poll = ack+1
        s.tick([1,7]); self.assertEqual(len(self.device.moves),1)
        self.now[0] = ack+.6
        s.tick([1,7]); self.assertEqual(len(self.device.moves),2)

    def test_old_service_rejected_before_feedback_or_movement(self):
        self.session.playing = False; self.device.adaptive_playback = False
        count = len(self.device.calls)
        with self.assertRaisesRegex(PlaybackRejected, '更新'):
            self.session.start_playback(self.record,[1,7])
        self.assertEqual(len(self.device.calls),count)


class AdaptiveTransportTests(unittest.TestCase):
    def test_explicit_opt_in_and_ack_validation_without_retry(self):
        device = RemoteDevice.__new__(RemoteDevice)
        device.adaptive_playback = True
        device.request = Mock(return_value={'sent':True,'duration_ms':459,'requested_duration_ms':450})
        self.assertEqual(device.playback_move({'7':1600},450)['duration_ms'],459)
        self.assertTrue(device.request.call_args.args[1]['adaptive_duration'])
        for ms in (449,10000,True):
            device.request.reset_mock()
            device.request.return_value = {'sent':True,'duration_ms':ms,'requested_duration_ms':450}
            with self.assertRaises(ValueError): device.playback_move({'7':1600},450)
            device.request.assert_called_once()

    def test_missing_capability_never_transmits(self):
        device = RemoteDevice.__new__(RemoteDevice)
        device.adaptive_playback = False; device.request = Mock()
        with self.assertRaises(RuntimeError):device.playback_move({'7':1600},450)
        device.request.assert_not_called()


class ServiceOverlayTests(unittest.TestCase):
    def test_overlay_is_hashed_and_runs_with_base_package_relative_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'console'
            manifest = build(PROFILE,out,allow_motion=True,service_overlay=True)
            self.assertTrue(manifest['service_overlay'])
            self.assertEqual(set(manifest['files']), {'bus_servo.json','start_console.sh','service.py'})
            for name, expected in manifest['files'].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),expected)
            script = (out/'start_console.sh').read_text()
            compile(script.split("<<'VERIFY'\n",1)[1].split('\nVERIFY',1)[0], 'verify', 'exec')
            self.assertIn(manifest['files']['service.py'],script)
            module = runpy.run_path(str(out/'service.py'),run_name='shadow_play.bus_servo.service')
            self.assertEqual(module['ADAPTIVE_PLAYBACK'],ADAPTIVE_PLAYBACK)
            self.assertTrue(callable(module['main']))


if __name__ == '__main__': unittest.main()
