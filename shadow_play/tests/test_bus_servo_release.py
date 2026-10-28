"""Selected torque release is independent of positioning and broadcast stop."""
import copy
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import BusDevice
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.protocol import ProtocolError, ServoUnavailable
from shadow_play.bus_servo.service import Controller, BOARD_ONLY, SELECTED_RELEASE
from shadow_play.bus_servo.transport import RemoteDevice
from shadow_play.tests.test_bus_servo_tiger import Registers, ServoWire, TIGER


class SelectedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.load(TIGER)
        self.reg = Registers(self.profile.layout)
        self.wires = patch('shadow_play.bus_servo.device.WireBus', ServoWire)
        self.wires.start()
        self.device = BusDevice(self.profile, self.reg)
        self.controller = Controller(self.profile, self.device, allow_release=True)
        self.seq = 0

    def tearDown(self):
        self.device.close()
        self.wires.stop()

    def rpc(self, op, **payload):
        self.seq += 1
        return self.controller.execute(dict(seq=self.seq, op=op, payload=payload))

    def packets(self):
        return [p for b in self.device.buses.values() for p in b.requests]

    def test_release_selected_only_without_motion_commissioning_or_lease(self):
        hello = self.rpc('hello')
        self.assertTrue(hello['release_allowed'])
        self.assertFalse(hello['motion_allowed'])
        self.assertIn(SELECTED_RELEASE, hello['capabilities'])
        self.rpc('probe', numbers=[7, 9])
        result = self.rpc('release', numbers=[7, 9], attended=True)
        self.assertEqual(result['release_acknowledged'], [7, 9])
        self.assertFalse(result['physical_release_verified'])
        self.assertEqual([p for p in self.packets() if p.endswith(b'ULK!')], [b'#007PULK!', b'#009PULK!'])
        for name in ('tiger8', 'tiger10'): self.assertEqual(self.device.buses[name].requests, [])
        self.assertEqual(self.reg.writes, [])
        self.assertFalse(self.device.claimed)
        for _ in range(3): self.rpc('status')
        self.assertEqual(self.rpc('stop')['state'], 'no_motion_lease')
        self.rpc('quit'); self.device.close()
        self.assertEqual(self.reg.writes, [])

    def test_release_permission_does_not_enable_angle_commands(self):
        self.rpc('probe', numbers=[7])
        before = self.packets()
        with self.assertRaises(RuntimeError):
            self.rpc('move', targets={'7':1501}, duration_ms=2000, attended=True)
        self.assertEqual(self.packets(), before)
        self.assertEqual(self.reg.writes, [])

    def test_release_requires_explicit_permission_electrical_gate_and_operator(self):
        self.rpc('probe', numbers=[7])
        before = self.packets()
        with self.assertRaises(ValueError): self.rpc('release', numbers=[7], attended=False)
        self.controller.allow_release = False
        with self.assertRaises(RuntimeError): self.rpc('release', numbers=[7], attended=True)
        data = copy.deepcopy(self.profile.data); data['electrical_3v3_verified'] = False
        self.controller.profile = Profile(data); self.controller.allow_release = True
        with self.assertRaises(RuntimeError): self.rpc('release', numbers=[7], attended=True)
        self.assertEqual(self.packets(), before)

    def test_undetected_axes_prevent_the_entire_release(self):
        self.rpc('probe', numbers=[7])
        before = self.packets()
        with self.assertRaises(ServoUnavailable): self.rpc('release', numbers=[7, 8], attended=True)
        self.assertEqual(self.packets(), before)

    def test_fresh_feedback_failure_prevents_all_torque_off(self):
        self.rpc('probe', numbers=[7, 8])
        with patch.object(self.device.buses['tiger8'], 'exchange', side_effect=TimeoutError('unpowered')):
            with self.assertRaises(ServoUnavailable): self.rpc('release', numbers=[7, 8], attended=True)
        self.assertFalse(any(p.endswith(b'ULK!') for p in self.packets()))
        self.assertEqual(self.reg.writes, [])
        self.assertEqual(self.controller.verified, set())

    def test_missing_ack_latches_failure_without_retry_or_broadcast(self):
        self.rpc('probe', numbers=[7])
        wire = self.device.buses['tiger7']; original = wire.exchange
        def exchange(packet, *args, **kwargs):
            if packet.endswith(b'ULK!'):
                wire.requests.append(packet)
                raise TimeoutError('no ACK')
            return original(packet, *args, **kwargs)
        with patch.object(wire, 'exchange', side_effect=exchange):
            with self.assertRaises(TimeoutError): self.rpc('release', numbers=[7], attended=True)
            with self.assertRaises(ServoUnavailable): self.rpc('release', numbers=[7], attended=True)
        self.assertEqual(wire.requests.count(b'#007PULK!'), 1)
        self.assertEqual(self.reg.writes, [])

    def test_wrong_id_ack_is_not_success(self):
        self.rpc('probe', numbers=[10])
        wire = self.device.buses['tiger10']; original = wire.exchange
        with patch.object(wire, 'exchange', side_effect=lambda p, *a, **kw: b'#009POK!' if p.endswith(b'ULK!') else original(p, *a, **kw)):
            with self.assertRaises(ProtocolError): self.rpc('release', numbers=[10], attended=True)
        self.assertFalse(self.device.claimed)
        self.assertEqual(self.reg.writes, [])

    def test_existing_motion_lease_keeps_its_stop_path(self):
        self.rpc('probe', numbers=[7])
        self.device.claimed = True; self.reg.lease = 1
        self.rpc('release', numbers=[7], attended=True)
        self.assertTrue(self.device.claimed)
        self.rpc('stop')
        self.assertIn((0x0c, 0x53544f50), self.reg.writes)


class ReleaseTransportTests(unittest.TestCase):
    def device(self):
        d = RemoteDevice.__new__(RemoteDevice)
        d.capabilities = [BOARD_ONLY, SELECTED_RELEASE]
        d.profile = Profile.load(TIGER)
        d.motion_active = False
        d.release_allowed = True
        return d

    def test_release_only_does_not_create_pc_motion_session(self):
        d = self.device(); calls = []
        d.request = lambda op, payload=None: calls.append((op,payload)) or {'release_acknowledged':[7]}
        d.release([7])
        self.assertFalse(d.motion_active)
        self.assertEqual(d.stop()['state'], 'no_motion_lease')
        self.assertEqual(len(calls), 1)
        d.motion_active = True; d.release([7])
        self.assertTrue(d.motion_active)

    def test_old_service_cannot_be_used_for_lease_free_release(self):
        d = self.device(); d.capabilities = [BOARD_ONLY]
        d.request = lambda op, payload=None: {'service':'bus-teach-v1', 'profile':d.profile.fingerprint,
            'simulation':False, 'motion_allowed':True, 'positions':{}, 'release_allowed':True}
        d.connect()
        self.assertFalse(d.release_allowed)
        with patch.object(d,'request') as send:
            with self.assertRaises(RuntimeError): d.release([7])
            send.assert_not_called()


if __name__ == '__main__': unittest.main()
