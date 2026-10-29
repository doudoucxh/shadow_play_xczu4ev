"""Named action capture and recall, with no real serial/device access."""
import copy
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.editing import capture_pose
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.pose_library import PoseLibrary, file_sha, load_catalog, move_targets, save_library
from shadow_play.bus_servo.pose_worker import PoseWorker
from shadow_play.bus_servo.session import TeachingSession

PROFILE = Path(__file__).resolve().parents[1] / 'config/bus_servo.json'


class PoseLibraryTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.load(PROFILE)
        self.library = PoseLibrary(self.profile)

    def pose(self, numbers=None, simulation=False, p=1500):
        numbers = numbers or list(range(1, 7))
        return capture_pose(self.profile, numbers, {n:dict(p=p, at=100+n*.001) for n in numbers}, simulation)

    def test_catalog_exactly_matches_drawing_ids(self):
        catalog = json.loads((PROFILE.parents[1] / 'hdmi_ui/source/catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(list(self.library.catalog)[:-1], ['wusong/'+row['id'] for row in catalog['actions']])
        self.assertEqual(len(self.library.catalog), 21)
        self.assertEqual(self.library.data['poses'], {})

    def test_all_actions_round_trip_and_role_isolation(self):
        for key, row in self.library.catalog.items():
            self.library.set_pose(key, self.pose(row['axes']), 'note')
        loaded = PoseLibrary(self.profile, self.library.data)
        for key, row in loaded.catalog.items():
            self.assertEqual(loaded.get_pose(key, live=True)['selected'], row['axes'])

    def test_partial_or_wrong_role_is_rejected_without_mutation(self):
        for nums in ([1], list(range(7, 11)), list(range(1, 11))):
            with self.assertRaises(ValueError):
                self.library.set_pose('wusong/neutral', self.pose(nums))
            self.assertEqual(self.library.data['poses'], {})

    def test_source_copy_and_simulation_cannot_drive_live(self):
        pose = self.pose(simulation=True)
        self.library.set_pose('wusong/neutral', pose)
        pose['positions']['1'] = 2000
        self.assertEqual(self.library.get_pose('wusong/neutral')['positions']['1'], 1500)
        with self.assertRaises(ValueError):
            self.library.get_pose('wusong/neutral', live=True)

    def test_unknown_schema_layout_tamper_and_missing_pose(self):
        with self.assertRaises(ValueError):
            self.library.get_pose('wusong/neutral')
        self.library.set_pose('wusong/neutral', self.pose())
        for field in ('schema', 'catalog_id', 'profile_sha256'):
            data = copy.deepcopy(self.library.data)
            data[field] = 'incorrect'
            with self.assertRaises(ValueError):
                PoseLibrary(self.profile, data)
        data = copy.deepcopy(self.library.data)
        data['poses']['wusong/neutral']['pose']['positions']['1'] = 1510
        with self.assertRaises(ValueError):
            PoseLibrary(self.profile, data)

    def test_bad_feedback_range_timestamp_missing_axis(self):
        pose = self.pose()
        for mutation in (lambda p:p['positions'].pop('2'), lambda p:p['positions'].__setitem__('1', 500),
                         lambda p:p['acquired_at'].__setitem__('1', 200)):
            candidate = copy.deepcopy(pose)
            mutation(candidate)
            with self.assertRaises(ValueError):
                self.library.set_pose('wusong/neutral', candidate)

    def test_atomic_save_history_and_concurrent_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.json'
            self.library.set_pose('wusong/neutral', self.pose())
            first = save_library(path, self.library, None)
            old = path.read_bytes()
            self.library.set_pose('wusong/neutral', self.pose(p=1510))
            second = save_library(path, self.library, first)
            self.assertEqual((path.parent/'library.history'/f'{first}.json').read_bytes(), old)
            self.assertNotEqual(first, second)
            with self.assertRaises(ValueError):
                save_library(path, self.library, first)
            self.assertEqual(file_sha(path), second)
            with patch('os.replace', side_effect=OSError('disk failure')), self.assertRaises(OSError):
                save_library(path, self.library, second)
            self.assertEqual(file_sha(path), second)

    def session(self):
        device = SimulationDevice(self.profile)
        session = TeachingSession(self.profile, device, 'unused')
        device.move = Mock(wraps=device.move)
        return session

    def test_move_uses_current_feedback_and_manual_speed_even_if_playback_unlimited(self):
        s = self.session()
        seconds = move_targets(s, {'1':1600}, .02)
        self.assertAlmostEqual(seconds, 13.5/30+.3)
        s.device.move.assert_called_once_with({'1':1600}, 750)
        self.assertEqual(set(s.device.motions), {1})

    def test_stop_during_second_read_prevents_any_target(self):
        s = self.session()
        stop = threading.Event()
        s.cancel_requested = stop.is_set
        original = s.read
        count = 0
        def read(numbers):
            nonlocal count
            count += 1
            rows = original(numbers)
            if count == 2:
                stop.set()
            return rows
        s.read = read
        with self.assertRaises(ValueError):
            move_targets(s, {'1':1600})
        s.device.move.assert_not_called()

    def test_invalid_targets_never_send(self):
        for targets, duration in (({'1':500}, 2), ({'11':1500}, 2), ({'1':1500}, float('nan'))):
            s = self.session()
            with self.assertRaises(ValueError):
                move_targets(s, targets, duration)
            s.device.move.assert_not_called()

    def test_worker_capture_is_fresh_and_token_bound(self):
        worker = PoseWorker(queue.Queue(), queue.Queue(), threading.Event())
        worker.session = self.session()
        worker.session.device.positions[1] = 1567
        worker.handle('capture', (42, 'wusong/open'))
        kind, (token, key, pose) = worker.events.get_nowait()
        self.assertEqual((kind, token, key), ('captured', 42, 'wusong/open'))
        self.assertEqual(pose['positions']['1'], 1567)
        self.assertEqual(pose['source'], 'simulation')
        worker.session.device.move.assert_not_called()

    def test_worker_rejects_simulated_recall_in_live_mode_before_io(self):
        worker = PoseWorker(queue.Queue(), queue.Queue(), threading.Event())
        worker.session = self.session()
        worker.session.device.simulation = False
        worker.session.device.motion_allowed = True
        with self.assertRaises(ValueError):
            worker.handle('recall', (('wusong/open', self.pose(simulation=True)), 2, True))
        worker.session.device.move.assert_not_called()

    def test_startup_stop_discards_queued_motion_and_shutdown_exits(self):
        commands, events, flag = queue.Queue(), queue.Queue(), threading.Event()
        worker = PoseWorker(commands, events, flag)
        commands.put(('move', ({'1':1500}, 2, True)))
        commands.put(('shutdown', None))
        flag.set()
        with patch('shadow_play.bus_servo.pose_worker.RemoteDevice', side_effect=AssertionError('No serial')):
            worker.start()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(worker.session)
        self.assertEqual(list(events.queue), [('stopped', None), ('closed', None)])


if __name__ == '__main__':
    unittest.main()
