"""Offline UI bridge checks with synthetic pixel arrays; no devices or datasets."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/follow'))
from ui_frame_feed import UiFrameFeed, validate_feed_options


class UiFrameFeedTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'current.json'
        self.now = 10.
        self.feed = UiFrameFeed(self.path, _clock=lambda: self.now, _allowed_roots=[self.root])
        self.addCleanup(self.feed.close)
        self.frame = np.full((720, 1280, 3), (20, 40, 180), dtype=np.uint8)
        self.pose = [[640., 360., .9] for _ in range(9)]

    def publish(self, sequence=1, pose='default'):
        return self.feed.publish(self.frame, self.pose if pose == 'default' else pose,
                                 sequence, self.now - .01, 1)

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def test_pixels_and_pose_belong_to_same_input_and_survive_later_mutation(self):
        self.pose[0] = [320., 180., .9]
        self.assertTrue(self.publish())
        self.frame[:] = 255
        self.pose[0][:] = [0., 0., 0.]
        payload = self.read()
        image = cv2.imdecode(np.frombuffer(base64.b64decode(payload['jpeg_base64']), np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape, (360, 640, 3))
        np.testing.assert_allclose(image.mean(axis=(0, 1)), [20, 40, 180], atol=3)
        self.assertEqual(payload['pose']['head'], [.25, .25])
        self.assertEqual(payload['captured_s'], 9.99)
        self.assertEqual(payload['sequence'], 1)
        self.assertEqual(payload['session_id'], self.feed.session_id)

    def test_missing_detection_replaces_old_pose_with_empty_object(self):
        self.publish()
        self.now += .11
        self.publish(2, None)
        self.assertEqual(self.read()['pose'], {})
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_invalid_points_omitted_without_neck_or_hips_fabrication(self):
        self.pose[0][2] = .24
        self.pose[1][0] = float('nan')
        self.pose[3][1] = 721.
        self.pose[5][2] = .25
        self.publish()
        points = self.read()['pose']
        self.assertEqual(set(points), {'rightShoulder', 'rightElbow', 'leftWrist', 'rightWrist'})
        self.assertEqual(points['leftWrist'], [.5, .5])

    def test_max_ten_hz_drops_new_frame_without_rewriting_old_snapshot(self):
        self.publish()
        before = self.path.read_bytes()
        self.now += .05
        with patch('cv2.imencode', side_effect=AssertionError('throttled frame must not encode')):
            self.assertFalse(self.publish(2))
        self.assertEqual(self.path.read_bytes(), before)
        self.now += .06
        self.assertTrue(self.publish(3))
        self.assertEqual(self.read()['sequence'], 3)
        with self.assertRaises(ValueError):
            self.publish(2)

    def test_atomic_replace_failure_leaves_complete_prior_frame_no_temp_files(self):
        self.publish()
        before = self.path.read_bytes()
        self.now += .11
        def fail(source, destination):
            self.assertEqual(Path(destination).read_bytes(), before)
            self.assertEqual(json.loads(Path(source).read_text())['sequence'], 2)
            raise OSError('simulated replacement failure')
        with patch('ui_frame_feed.os.replace', side_effect=fail):
            with self.assertRaises(OSError):
                self.publish(2)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_close_removes_own_snapshot_but_not_new_owners_snapshot(self):
        self.publish()
        self.feed.close()
        self.assertFalse(self.path.exists())
        with self.assertRaises(RuntimeError):
            self.publish(2)
        replacement = UiFrameFeed(self.path, _clock=lambda: self.now, _allowed_roots=[self.root])
        replacement.publish(self.frame, None, 1, self.now, 0)
        data = self.read()
        data['session_id'] = '0' * 32
        self.path.write_text(json.dumps(data))
        replacement.close()
        self.assertTrue(self.path.exists())

    def test_bad_frame_metadata_and_old_or_future_capture_fail_before_write(self):
        for captured in [self.now - .251, self.now + .001]:
            with self.assertRaises(ValueError):
                self.feed.publish(self.frame, self.pose, 1, captured, 1)
        for frame in [None, self.frame[:100], self.frame.astype(np.float32)]:
            with self.assertRaises(ValueError):
                self.feed.publish(frame, self.pose, 1, self.now, 1)
        for pose, sequence, track in [(self.pose[:3], 1, 1), (self.pose, True, 1), (self.pose, 1, 0)]:
            with self.assertRaises(ValueError):
                self.feed.publish(self.frame, pose, sequence, self.now, track)
        self.assertFalse(self.path.exists())

    def test_cli_requires_non_motion_non_hdmi_usb_path(self):
        validate_feed_options('usb', 'none', True, '/run/shadow-ui/current.json')
        validate_feed_options('vdma', 'hdmi', False, None)
        for camera, display, no_send in [('vdma', 'none', True), ('usb', 'hdmi', True), ('usb', 'none', False)]:
            with self.assertRaises(ValueError):
                validate_feed_options(camera, display, no_send, '/tmp/current.json')
        for path in ['/home/current.json', '/tmp/../home/current.json', 'current.json', '/run/current.jpg', '/tmp']:
            with self.assertRaises(ValueError):
                validate_feed_options('usb', 'none', True, path)

    def test_runtime_path_cannot_escape_allowed_roots(self):
        with self.assertRaises(ValueError):
            UiFrameFeed(self.root.parent / 'outside.json', _allowed_roots=[self.root])


if __name__ == '__main__':
    unittest.main()
