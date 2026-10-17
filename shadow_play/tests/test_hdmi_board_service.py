"""Offline HTTP and freshness tests; never open a camera or a motor device."""
import base64
from functools import partial
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'hdmi_ui/runtime'
sys.path.insert(0, str(RUNTIME))
from board_service import BoardBridge, BoardCamera, Unavailable, decode_live_frame
from serve import Handler


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'frame.json'
        # Only a protocol envelope fixture, not an image or detection claim.
        self.packet = dict(version=1, session_id='a'*32, sequence=12,
                           captured_s=100.0, width=640, height=360,
                           pose={'leftWrist': [.3, .7]},
                           jpeg_base64=base64.b64encode(b'\xff\xd8fixture\xff\xd9').decode())

    def read(self, now=100.1, started=99):
        self.path.write_text(json.dumps(self.packet), encoding='utf-8')
        return decode_live_frame(self.path, now, started)

    def test_frame_has_only_received_points(self):
        frame = self.read()
        self.assertEqual(frame['pose'], {'leftWrist': [.3, .7]})
        self.assertEqual(frame['sequence'], 12)
        self.assertAlmostEqual(frame['captured_age_ms'], 100)

    def test_stale_future_and_previous_run_rejected(self):
        for now, started in [(101,99),(99,98),(100.1,100.05)]:
            with self.subTest(now=now, started=started), self.assertRaises(ValueError):
                self.read(now, started)

    def test_no_person_is_empty_not_last_pose(self):
        self.read()
        self.packet['pose'] = {}
        self.assertEqual(self.read()['pose'], {})

    def test_invalid_point_or_jpeg_rejected(self):
        for value in [[True,.3],[float('nan'),.3],[1.1,.3],[]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.packet['pose'] = {'head':value}
                self.read()
        self.packet['pose'] = {}
        self.packet['jpeg_base64'] = 'not-a-jpeg'
        with self.assertRaises(ValueError):
            self.read()

    def test_bad_session_sequence_and_size_rejected(self):
        self.packet['sequence'] = True
        with self.assertRaises(ValueError): self.read()
        self.packet['sequence'] = 1
        self.packet['session_id'] = '../old'
        with self.assertRaises(ValueError): self.read()
        self.path.write_bytes(b' ' * 1500001)
        with self.assertRaises(ValueError): decode_live_frame(self.path,100.1,99)

    def test_non_object_packet_and_boolean_version_rejected(self):
        for value in (None, [], 1, dict(self.packet, version=True)):
            self.packet = value
            with self.assertRaises(ValueError): self.read()

    def test_camera_no_configuration_never_spawns(self):
        camera = BoardCamera('not-installed')
        with patch.object(camera,'configuration_error',return_value='unconfigured'), patch('subprocess.Popen') as popen:
            with self.assertRaises(Unavailable): camera.start()
            popen.assert_not_called()

    def test_camera_lease_expiry_stops_only_owned_instance(self):
        camera = BoardCamera('not-installed')
        camera.process = object()
        camera.last_request = time.monotonic()-11
        with patch.object(camera,'stop') as stop:
            camera.expire()
            stop.assert_called_once_with()


class FakeCamera:
    def __init__(self): self.starts = self.stops = 0
    def status(self): return dict(configured=False,running=False,live=False,error='test: no hardware')
    def frame(self): raise Unavailable('no real frame')
    def start(self): self.starts += 1
    def stop(self): self.stops += 1
    def expire(self): pass


class QuietHandler(Handler):
    def log_message(self, *args): pass


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.camera = FakeCamera()
        self.server = ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(RUNTIME/'web')))
        self.server.bridge = BoardBridge(self.camera)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.origin = 'http://127.0.0.1:'+str(self.port)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()
        self.server.bridge.close()

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        self.addCleanup(c.close)
        c.request(method,path,body=body,headers=headers or {})
        r = c.getresponse()
        return r.status,json.loads(r.read())

    def authorized(self):
        return {'Origin':self.origin,'X-Shadow-Token':self.server.bridge.token,
                'Content-Type':'application/json'}

    def test_status_never_claims_motor_ready(self):
        code,data = self.request('GET','/api/status')
        self.assertEqual(code,200)
        self.assertFalse(data['motion']['ready'])
        self.assertFalse(data['camera']['live'])

    def test_motion_rejected_despite_client_claims(self):
        for kind in ('rail','pose','classic','unlock','stop'):
            code,data = self.request('POST','/api/control',json.dumps({'kind':kind,'ready':True,'position':.5}),self.authorized())
            self.assertEqual(code,409)
            self.assertFalse(data['ok'])
        self.assertEqual(self.camera.starts,0)

    def test_cross_origin_missing_token_and_rebinding_rejected(self):
        for headers in [{},{**self.authorized(),'Origin':'https://example.com'},
                        {**self.authorized(),'X-Shadow-Token':'wrong'},
                        {**self.authorized(),'Host':'example.com:'+str(self.port)}]:
            code,_ = self.request('POST','/api/camera/start','{}',headers)
            self.assertEqual(code,403)
        self.assertEqual(self.camera.starts,0)

    def test_explicit_start_stop_and_missing_frame(self):
        self.assertEqual(self.request('POST','/api/camera/start','{}',self.authorized())[0],200)
        self.assertEqual(self.camera.starts,1)
        self.assertEqual(self.request('GET','/api/camera/frame')[0],503)
        self.assertEqual(self.request('POST','/api/camera/stop','{}',self.authorized())[0],200)
        self.assertEqual(self.camera.stops,1)

    def test_oversized_or_non_object_body_rejected(self):
        for body in ('[]','x'*16385):
            self.assertEqual(self.request('POST','/api/camera/start',body,self.authorized())[0],400)
        self.assertEqual(self.camera.starts,0)

    def test_audio_requires_same_origin_and_does_not_start_camera(self):
        class Audio:
            def __init__(self): self.starts = self.stops = 0
            def start(self): self.starts += 1
            def stop(self): self.stops += 1
            def expire(self): pass
            def status(self, touch=False): return dict(running=self.starts > self.stops)
        audio = Audio()
        self.server.bridge.audio = audio
        self.assertEqual(self.request('POST','/api/audio/start','{}')[0],403)
        self.assertEqual(audio.starts,0)
        self.assertEqual(self.request('POST','/api/audio/start','{}',self.authorized())[0],200)
        self.assertTrue(self.request('GET','/api/audio/status')[1]['running'])
        self.assertEqual(self.camera.starts,0)
        self.assertEqual(self.request('POST','/api/audio/stop','{}',self.authorized())[0],200)
        self.assertEqual(audio.stops,1)


if __name__ == '__main__': unittest.main()
