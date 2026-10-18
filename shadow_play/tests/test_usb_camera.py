"""USB capture/geometry/error regression tests; no hardware opened."""
import ctypes
import multiprocessing as mp
from pathlib import Path
import struct
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/follow'))
import usb_camera as usb
from usb_hdmi import UsbHdmiDisplay


class UsbTests(unittest.TestCase):
    def test_metadata_node_is_not_capture(self):
        data = bytearray(104)
        struct.pack_into('=II', data, 84, 0x80000000 | 0x04000001, 0x04800000)
        self.assertFalse(usb.capture_capability(data))
        struct.pack_into('=I', data, 88, 0x04000001)
        self.assertTrue(usb.capture_capability(data))

    def test_missing_and_ambiguous_devices_fail(self):
        for devices in ([], [dict(device='/dev/video0'), dict(device='/dev/video2')]):
            with self.assertRaises(RuntimeError):
                usb.select_device('auto', devices)
        self.assertEqual(usb.select_device('auto', [dict(device='/dev/video2')]), '/dev/video2')

    def test_explicit_device_must_be_usb_capture(self):
        with self.assertRaises(RuntimeError):
            usb.select_device('/dev/video1', [dict(device='/dev/video0')])

    def test_four_by_three_letterbox_without_stretch(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        out = usb.normalize_frame(frame)
        self.assertEqual(out.shape, (720, 1280, 3))
        self.assertTrue(np.all(out[:, :160] == 114))
        self.assertTrue(np.all(out[:, 160:1120] == 0))
        self.assertTrue(np.all(out[:, 1120:] == 114))

    def test_default_not_rotated_or_mirrored(self):
        raw = np.zeros((720, 1280, 3), np.uint8)
        raw[:360, :640] = 255
        self.assertTrue(np.all(usb.normalize_frame(raw)[:360, :640] == 255))
        rotated = usb.normalize_frame(raw, 180)
        self.assertTrue(np.all(rotated[360:, 640:] == 255))
        mirrored = usb.normalize_frame(raw, mirror=True)
        self.assertTrue(np.all(mirrored[:360, 640:] == 255))

    def test_portrait_rotation_and_owned_copy(self):
        raw = np.zeros((1280, 720, 3), np.uint8)
        out = usb.normalize_frame(raw, 90)
        self.assertTrue(out.flags.c_contiguous)
        self.assertFalse(np.shares_memory(out, raw))
        self.assertEqual(out.shape, usb.SHAPE)
        with self.assertRaises(ValueError):
            usb.normalize_frame(raw, 45)

    def test_reject_bad_frames(self):
        for raw in (None, np.zeros((10,10),np.uint8), np.zeros((10,10,3),np.float32)):
            with self.assertRaises(ValueError):
                usb.normalize_frame(raw)

    def camera_stub(self, age=0., sequence=8):
        camera = usb.LatestUsbCamera.__new__(usb.LatestUsbCamera)
        camera.closed = False
        camera.timeout, camera.max_age = .02, .25
        camera.published = camera.dropped = camera.rejected = 0
        camera.last_sequence = 3
        camera.pixels = bytearray(int(np.prod(usb.SHAPE)))
        camera.sequence = ctypes.c_ulonglong(sequence)
        camera.timestamp = ctypes.c_double(time.monotonic()-age)
        camera.mutex = threading.Lock()
        camera._check = Mock()
        return camera

    def test_latest_frame_skips_queue_and_owns_pixels(self):
        camera = self.camera_stub()
        frame, sequence, _ = camera.read()
        self.assertEqual(sequence, 8)
        self.assertEqual(camera.dropped, 4)
        camera.pixels[0] = 99
        self.assertEqual(frame[0,0,0], 0)

    def test_stale_and_missing_frames_fail(self):
        for camera in (self.camera_stub(age=1), self.camera_stub(sequence=3)):
            with self.assertRaises(RuntimeError):
                camera.read()

    def test_startup_wait_does_not_relax_freshness_or_later_timeout(self):
        camera = self.camera_stub(sequence=3)
        clock = [0.]
        def advance(delay):
            clock[0] += delay
            if clock[0] >= .04:
                camera.sequence.value = 4
                camera.timestamp.value = clock[0]
        with patch.object(usb.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(usb.time, 'sleep', side_effect=advance):
            frame, sequence, _ = camera.read(timeout=.1)
        self.assertEqual(sequence, 4)
        self.assertEqual(camera.timeout, .02)
        with self.assertRaises(RuntimeError):
            self.camera_stub(age=1).read(timeout=10)

    def test_hung_driver_shutdown_is_bounded(self):
        camera = self.camera_stub()
        camera.stop, camera.info, camera.process = Mock(), Mock(), Mock()
        camera.process.is_alive.side_effect = [True, False, False]
        camera.close()
        camera.process.terminate.assert_called_once()
        camera.close()
        camera.process.terminate.assert_called_once()

    def test_worker_reports_read_failure_and_releases(self):
        ctx = mp.get_context('spawn')
        capture, info = Mock(), Mock()
        capture.isOpened.return_value = True
        capture.read.return_value = (False, None)
        with patch.object(usb.cv2, 'VideoCapture', return_value=capture):
            usb._worker(dict(device='/dev/video0', fourcc='MJPG', width=1280, height=720,
                             fps=30, rotation=0, mirror=False),
                        ctx.RawArray('B', int(np.prod(usb.SHAPE))), ctx.RawValue('Q',0),
                        ctx.RawValue('d',0.), ctx.Lock(), ctx.Event(), info)
        self.assertEqual(info.send.call_args[0][0][0], 'error')
        capture.release.assert_called_once()

    def test_real_child_open_failure_cleans_up(self):
        # Exercise spawn/shared memory and IPC on Linux, with no actual camera.
        with patch.object(usb,'select_device',return_value='/dev/nonexistent-shadow-test-camera'):
            camera=usb.LatestUsbCamera(timeout=5)
        try:
            with self.assertRaises(RuntimeError):
                camera.read()
        finally:
            camera.close()
        self.assertFalse(camera.process.is_alive())

    def test_hdmi_ignores_capture_dma_errors(self):
        display = UsbHdmiDisplay.__new__(UsbHdmiDisplay)
        display.words = Mock()
        display.words.read.side_effect = lambda offset: 0 if offset == 4 else 0x15190
        display.check()
        display.words.read.assert_called_once_with(4)
        display.words.read.side_effect = None
        display.words.read.return_value = 0x15190
        with self.assertRaises(RuntimeError):
            display.check()

    def test_usb_follow_headless_never_opens_legacy_dma(self):
        # This integration case runs on Linux with the installed board runtime.
        import board_follow_with_sender as follow
        camera = Mock()
        camera.metadata = {'device':'fake-test-input'}
        camera.published, camera.dropped, camera.rejected = 3, 0, 0
        sequence = [0]
        def read():
            sequence[0] += 1
            return np.zeros(usb.SHAPE, np.uint8), sequence[0], time.monotonic()
        camera.read.side_effect = read
        model = Mock()
        model.order, model.input_fix, model.buffers = [], 7, []
        model.runner.wait.return_value = 0
        prepare = Mock(return_value=(np.zeros((1,384,384,3),np.int8), (.3,0,84,1280,720)))
        with patch.object(sys,'argv',['usb-test','--camera','usb','--display','none','--frames','2']), \
             patch.object(follow,'open_usb',return_value=camera), \
             patch.object(follow,'check_hardware_fingerprint'), \
             patch.object(follow,'DpuModel',return_value=model), \
             patch.object(follow,'VdmaFullFrame',side_effect=AssertionError('legacy DMA opened')), \
             patch.object(follow,'Display',side_effect=AssertionError('legacy HDMI opened')), \
             patch.object(follow,'QuantizedInput',return_value=prepare), \
             patch.object(follow,'decode_int8',return_value=([],[],[])), \
             patch.object(follow,'PoseSender') as sender:
            follow.main()
        self.assertEqual(sender.return_value.publish.call_count, 2)
        self.assertIsNone(sender.return_value.publish.call_args[0][0])
        camera.close.assert_called_once()
        sender.return_value.close.assert_called_once()

    def test_camera_start_failure_precedes_dpu_and_releases(self):
        import board_follow_with_sender as follow
        camera = Mock()
        camera.read.side_effect = RuntimeError('camera disconnected')
        with patch.object(sys,'argv',['usb-test','--camera','usb','--display','none','--no-send']), \
             patch.object(follow,'open_usb',return_value=camera), \
             patch.object(follow,'DpuModel') as model, \
             patch.object(follow,'PoseSender') as sender:
            with self.assertRaisesRegex(RuntimeError, 'disconnected'):
                follow.main()
        model.assert_not_called()
        sender.assert_not_called()
        camera.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
