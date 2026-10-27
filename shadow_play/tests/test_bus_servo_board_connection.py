"""Board-only connection, explicit discovery, and fail-closed feedback states."""
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import BusDevice
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.protocol import ServoUnavailable
from shadow_play.bus_servo.service import Controller, serve, BOARD_ONLY
from shadow_play.bus_servo.session import TeachingSession
from shadow_play.bus_servo.transport import RemoteDevice
from shadow_play.tests.test_bus_servo_tiger import Registers, ServoWire, TIGER


class BoardConnectionTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.load(TIGER)
        self.reg = Registers(self.profile.layout)
        self.wire_patch = patch('shadow_play.bus_servo.device.WireBus', ServoWire)
        self.wire_patch.start()
        self.device = BusDevice(self.profile, self.reg)
        self.controller = Controller(self.profile, self.device)
        self.seq = 0

    def tearDown(self):
        self.device.close()
        self.wire_patch.stop()

    def rpc(self, op, **payload):
        self.seq += 1
        return self.controller.execute({'seq': self.seq, 'op': op, 'payload': payload})

    def packets(self):
        return [p for b in self.device.buses.values() for p in b.requests]

    def test_unpowered_hello_status_stop_quit_never_transmit_or_claim(self):
        result = self.rpc('hello')
        self.assertEqual(result['positions'], {})
        self.assertIn(BOARD_ONLY, result['capabilities'])
        self.assertFalse(result['motion_allowed'])
        for _ in range(20): self.rpc('status')
        self.assertEqual(self.rpc('stop')['state'], 'no_motion_lease')
        self.rpc('quit')
        self.assertEqual(self.reg.writes, [])
        self.assertEqual(self.packets(), [])

    def test_read_before_discovery_cannot_send(self):
        self.rpc('hello')
        with self.assertRaises(ServoUnavailable): self.rpc('read', numbers=[7])
        self.assertEqual(self.packets(), [])

    def test_explicit_probe_only_queries_selected_ids(self):
        self.rpc('hello')
        self.assertEqual(set(self.rpc('probe', numbers=[7, 9])), {7, 9})
        self.assertEqual(self.controller.verified, {7, 9})
        self.assertEqual(self.device.buses['tiger8'].requests, [])
        self.assertEqual(self.device.buses['tiger10'].requests, [])
        self.assertEqual(len(self.packets()), 8)
        self.assertEqual(self.reg.writes, [])
        with self.assertRaises(ServoUnavailable): self.rpc('read', numbers=[10])
        self.assertEqual(len(self.packets()), 8)

    def test_query_timeout_keeps_board_status_but_never_automatically_retries(self):
        with patch.object(self.device.buses['tiger7'], 'exchange', side_effect=TimeoutError('no reply')) as send:
            with self.assertRaises(ServoUnavailable): self.rpc('probe', numbers=[7])
            self.assertFalse(self.controller.closed)
            for _ in range(20): self.rpc('status')
            with self.assertRaises(ServoUnavailable): self.rpc('probe', numbers=[7])
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.controller.verified, set())
        self.assertEqual(self.reg.writes, [])

    def test_serve_accepts_status_and_quit_after_unpowered_probe(self):
        requests = [dict(seq=i, op=op, payload=p) for i, (op,p) in enumerate([
            ('hello', {}), ('probe', {'numbers': [7]}), ('status', {}), ('quit', {})], 1)]
        raw = b''.join((json.dumps(r)+'\n').encode() for r in requests)
        emitted = []
        with patch('shadow_play.bus_servo.service.select.select', return_value=([5], [], [])), \
                patch('shadow_play.bus_servo.service.os.read', return_value=raw), \
                patch.object(self.device.buses['tiger7'], 'exchange', side_effect=TimeoutError('no reply')) as send:
            serve(self.controller, 5, emitted.append)
        self.assertTrue(emitted[2]['servo_unavailable'])
        self.assertTrue(emitted[3]['ok'])
        self.assertTrue(emitted[4]['result']['closing'])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(self.reg.writes, [])

    def test_motion_feedback_failure_is_fatal_even_when_driver_already_stopped(self):
        self.rpc('probe', numbers=[7])
        self.device.claimed = True
        self.reg.lease = 1
        with patch.object(self.device.buses['tiger7'], 'exchange', side_effect=TimeoutError('lost')):
            with self.assertRaises(TimeoutError): self.rpc('read', numbers=[7])
        self.assertFalse(self.device.claimed)
        self.assertEqual(self.controller.verified, set())
        self.assertIn((0x0c, 0x53544f50), self.reg.writes)

    def bridge(self):
        parent = self
        class Bridge:
            simulation = False
            motion_allowed = False
            def connect(self): return parent.rpc('hello')['positions']
            def board_status(self): return parent.rpc('status')
            def probe(self, numbers): return parent.rpc('probe', numbers=numbers)
            def read(self, numbers): return parent.rpc('read', numbers=numbers)
            def stop(self): return parent.rpc('stop')
            def close(self): parent.rpc('quit')
        return Bridge()

    def test_session_idle_ticks_and_close_do_not_query_unpowered_servos(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = [0]
            s = TeachingSession(self.profile, self.bridge(), temp, clock=lambda:clock[0])
            for i in range(20):
                clock[0] = i * .5
                self.assertEqual(s.tick([7,8,9,10]), (None, False))
            with self.assertRaises(ServoUnavailable): s.capture_pose([7])
            with self.assertRaises(ServoUnavailable): s.start_recording([7])
            self.assertFalse(s.recording)
            self.assertEqual(list(Path(temp).iterdir()), [])
            s.stop(); s.close()
        self.assertEqual(self.packets(), [])
        self.assertEqual(self.reg.writes, [])

    def test_session_selection_does_not_query_unverified_axis(self):
        with tempfile.TemporaryDirectory() as temp:
            s = TeachingSession(self.profile, self.bridge(), temp)
            s.probe([7])
            time.sleep(.16)
            self.assertEqual(s.tick([10]), (None, False))
            self.assertEqual(len(self.packets()), 4)
            self.assertEqual(set(s.last_feedback), {7})
            s.close()

    def test_worker_preserves_board_link_after_probe_timeout(self):
        from shadow_play.bus_servo.gui import Worker
        commands, events, stop = queue.Queue(), queue.Queue(), threading.Event()
        worker = Worker(commands, events, stop)
        with patch('shadow_play.bus_servo.gui.RemoteDevice', return_value=self.bridge()), \
                patch.object(self.device.buses['tiger7'], 'exchange', side_effect=TimeoutError('no reply')) as send:
            worker.start()
            try:
                commands.put(('connect', (self.profile, False, 'mock')))
                self.assertEqual(events.get(timeout=2)[0], 'connected')
                commands.put(('probe', [7]))
                self.assertEqual(events.get(timeout=2)[0], 'servos_unavailable')
                time.sleep(.6)
                self.assertIsNotNone(worker.session)
                self.assertTrue(events.empty())
                self.assertEqual(send.call_count, 1)
            finally:
                commands.put(('shutdown', None)); worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(self.reg.writes, [])


class PcProtocolTests(unittest.TestCase):
    def device(self):
        d = RemoteDevice.__new__(RemoteDevice)
        d.sequence = 0; d.failed = False; d.motion_active = False
        d.port = type('Port', (), {'writes': [], 'write': lambda self, b:self.writes.append(b)})()
        return d

    def test_old_board_refused_before_hello_can_query_servos(self):
        d = self.device(); d.capabilities = []
        with self.assertRaisesRegex(RuntimeError, '更新板端'): d.connect()
        self.assertEqual(d.port.writes, [])

    def test_idle_servo_error_does_not_poison_serial_link(self):
        d = self.device()
        d._receive = lambda deadline: {'seq':d.sequence,'ok':False,'servo_unavailable':True,'error':'unpowered'}
        with self.assertRaises(ServoUnavailable): d.request('probe', {'numbers':[7]})
        self.assertFalse(d.failed)
        d._receive = lambda deadline: {'seq':d.sequence,'ok':True,'result':{'verified':[]}}
        self.assertEqual(d.board_status(), {'verified':[]})
        before = len(d.port.writes)
        self.assertEqual(d.stop()['state'], 'no_motion_lease')
        self.assertEqual(len(d.port.writes), before)

    def test_active_or_wrong_sequence_error_still_latches_transport(self):
        for active, seq in ((True,1),(False,2)):
            d = self.device(); d.motion_active=active
            d._receive = lambda deadline: {'seq':seq,'ok':False,'servo_unavailable':True,'error':'lost'}
            with self.assertRaises(RuntimeError): d.request('read', {'numbers':[7]})
            self.assertTrue(d.failed)


if __name__ == '__main__': unittest.main()
