"""Protocol and nonblocking delivery checks without camera or motor hardware."""

import errno
import importlib.util
import json
import pathlib
import socket
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "integrations" / "follow" / "pose_sender.py"
SPEC = importlib.util.spec_from_file_location("follow_pose_sender", MODULE_PATH)
sender_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sender_module)
SESSION = "0123456789abcdef0123456789abcdef"


class FakeSocket:
    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.packets = []
        self.blocking = None
        self.closed = False

    def setblocking(self, enabled):
        self.blocking = enabled

    def sendto(self, packet, destination):
        self.packets.append((packet, destination))
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return len(packet)

    def close(self):
        self.closed = True


class FollowFrameTests(unittest.TestCase):
    def build(self, pose=None, **changes):
        values = dict(sequence=12, captured_s=100.5, track_id=1, session_id=SESSION)
        values.update(changes)
        return sender_module.build_frame(pose, **values)

    def test_normalizes_original_anatomical_names_without_rotation_or_pelvis(self):
        pose = sender_module.demo_pose(0)
        pose[5] = [960, 180, 0.92]
        frame = self.build(pose)
        self.assertEqual(set(frame), {"version", "source", "session_id", "seq", "track_id", "captured_s", "detected", "points"})
        self.assertEqual(frame["version"], 2)
        self.assertEqual(frame["source"], "camera")
        self.assertEqual(list(frame["points"]), list(sender_module.KEYPOINT_NAMES))
        self.assertEqual(frame["points"]["left_wrist"], {"x": 0.75, "y": 0.25, "confidence": 0.92})
        self.assertNotIn("pelvis", frame["points"])
        self.assertNotIn("neck", frame["points"])
        self.assertEqual(json.loads(sender_module.encode_frame(frame)), frame)
        self.assertLess(len(sender_module.encode_frame(frame)), 16 * 1024)

    def test_no_detection_sends_empty_heartbeat(self):
        for track_id in (0, 7):
            frame = self.build(None, track_id=track_id)
            self.assertIs(frame["detected"], False)
            self.assertEqual(frame["points"], {})
            self.assertEqual(frame["track_id"], track_id)

    def test_invalid_joint_data_is_omitted_without_clamping(self):
        pose = [
            [-1, 200, 0.9], [1281, 200, 0.9], [200, 721, 0.9],
            [float("nan"), 0, 1], [0, float("inf"), 1], [0, 0, 0],
            [0, 0, 0.249], [0, 0, 1.1], [1280, 720, 0.25],
        ]
        frame = self.build(pose)
        self.assertEqual(frame["points"], {"right_hip": {"x": 1.0, "y": 1.0, "confidence": 0.25}})
        self.assertIs(frame["detected"], True)
        pose[8] = [True, "0.5", float("nan")]
        self.assertEqual(self.build(pose)["points"], {})

    def test_metadata_rejects_float_boolean_negative_and_overflow_ids(self):
        for name in ("sequence", "track_id"):
            for value in (-1, 1.0, True, "1", 1 << 64):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.build(**{name: value})
        frame = self.build(sequence=(1 << 64) - 1)
        self.assertEqual(frame["seq"], (1 << 64) - 1)
        for timestamp in (-1, float("nan"), float("inf"), True, "100"):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.build(captured_s=timestamp)
        for session in ("", "abc", SESSION.upper(), 123):
            with self.subTest(session=session), self.assertRaises(ValueError):
                self.build(session_id=session)
        with self.assertRaises(ValueError):
            self.build(sender_module.demo_pose(0), track_id=0)

    def test_shape_errors_are_frame_errors(self):
        for pose in ([], [[0, 0, 1]] * 8, [[0, 0, 1]] * 10, [[0, 0]] * 9, [None] * 9, 1):
            with self.subTest(pose=pose), self.assertRaises(ValueError):
                self.build(pose)

    def test_encoder_enforces_json_finiteness_and_datagram_size(self):
        with self.assertRaises(ValueError):
            sender_module.encode_frame({"bad": float("nan")})
        with self.assertRaises(ValueError):
            sender_module.encode_frame({"oversized": "x" * (16 * 1024)})


class FollowSenderTests(unittest.TestCase):
    def test_nonblocking_full_buffer_drops_current_frame_never_retries(self):
        fake = FakeSocket([BlockingIOError(errno.EAGAIN, "busy"), OSError(errno.ENOBUFS, "full")])
        with sender_module.PoseSender(_socket=fake) as sender:
            self.assertIs(fake.blocking, False)
            self.assertFalse(sender.publish(None, 1, 10, 0))
            self.assertFalse(sender.publish(None, 2, 10.02, 0))
            self.assertTrue(sender.publish(sender_module.demo_pose(0), 9, 10.1, 1))
            frames = [json.loads(packet) for packet, _ in fake.packets]
            self.assertEqual([frame["seq"] for frame in frames], [1, 2, 9])
            self.assertEqual({frame["session_id"] for frame in frames}, {sender.session_id})
            self.assertEqual(sender.stats, {"attempted": 3, "sent": 1, "dropped": 2, "invalid_frames": 0, "send_errors": 0})
            self.assertEqual([destination for _, destination in fake.packets], [("127.0.0.1", 56000)] * 3)
        self.assertTrue(fake.closed)
        with self.assertRaises(RuntimeError):
            sender.publish(None, 10, 11, 0)

    def test_rejects_duplicate_and_old_sequences_without_sending(self):
        fake = FakeSocket()
        with sender_module.PoseSender(_socket=fake) as sender:
            sender.publish(None, 5, 10, 0)
            for sequence in (5, 4):
                with self.assertRaises(ValueError):
                    sender.publish(None, sequence, 11, 0)
            sender.publish(None, 8, 12, 0)
            self.assertEqual(len(fake.packets), 2)
            self.assertEqual(sender.stats["invalid_frames"], 2)

    def test_unexpected_os_failure_is_visible(self):
        fake = FakeSocket([OSError(errno.EBADF, "bad descriptor")])
        with sender_module.PoseSender(_socket=fake) as sender:
            with self.assertRaises(OSError):
                sender.publish(None, 1, 10, 0)
            self.assertEqual(sender.stats["send_errors"], 1)

    def test_session_changes_only_when_sender_is_recreated(self):
        with sender_module.PoseSender(_socket=FakeSocket()) as first:
            with sender_module.PoseSender(_socket=FakeSocket()) as second:
                self.assertNotEqual(first.session_id, second.session_id)
                self.assertEqual(len(first.session_id), 32)

    def test_real_loopback_delivers_one_full_datagram(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(1)
            with sender_module.PoseSender(receiver.getsockname()[1]) as sender:
                self.assertTrue(sender.publish(sender_module.demo_pose(0), 1, 5.5, 1))
                packet, _ = receiver.recvfrom(16 * 1024)
                frame = json.loads(packet)
                self.assertEqual(frame["session_id"], sender.session_id)
                self.assertEqual(frame["seq"], 1)
                self.assertEqual(len(frame["points"]), 9)


if __name__ == "__main__":
    unittest.main()
