import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/calibration'))
from servo_pwm_device import PwmDevice, CaptureDriver, IDS
from servo_console import ConsoleController
from serial_gateway import SerialLink


class FakeRegisters:
    def __init__(self, apply=True):
        self.values = {0:0x53503130, 4:1, 0x28:20000, 0x2c:100000000}
        self.writes = []
        self.apply = apply
        for index in range(10):
            self.values[0x80+index*4] = 1500

    def read(self, address):
        return self.values.get(address, 0)

    def write(self, address, value):
        self.writes.append((address, value))
        if address == 0x0c:
            self.values.update({8:0, 0x10:0, 0x24:0})
        elif address == 0x10:
            self.values.update({0x10:1, 0x0c:0})
        elif address == 0x18:
            self.values[0x24] = 1
            if self.apply:
                for i in range(10):
                    self.values[0x80+i*4] = self.values[0x40+i*4]
                self.values[8] = self.values[0x14]
                self.values[0x20] = (self.read(0x20)+1)&0xffffffff
                self.values[0x24] = 0
        else:
            self.values[address] = value


def config():
    result = json.loads((ROOT/'config/capture.servos.real.template.json').read_text())
    for axis in result['axes']:
        axis.update(min=1490, max=1510, initial=1500)
    return result


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.reg = FakeRegisters()
        self.device = PwmDevice(self.reg)

    def test_construction_readonly_and_explicit_arm(self):
        self.device.status(); self.device.kick()
        self.assertEqual(self.reg.writes, [])
        with self.assertRaises(RuntimeError):
            self.device.commit([1500]*10, 1)
        self.assertEqual(self.reg.writes, [])
        result = self.device.commit([1500]*10, 1, allow_arm=True)
        self.assertEqual(result['enabled_mask'], 1)
        self.assertIsNone(result['position_feedback'])
        self.assertEqual(self.device.off()['enabled_mask'], 0)

    def test_invalid_group_never_writes(self):
        for pulses, mask in (([1500]*9, 1), ([499]+[1500]*9, 1), ([1500.0]*10, 1),
                             ([1500]*10, 1024), ([1500]*10, True)):
            with self.assertRaises(ValueError):
                self.device.commit(pulses, mask, allow_arm=True)
        self.assertEqual(self.reg.writes, [])

    def test_unknown_commit_is_not_retried(self):
        self.reg.apply = False
        with self.assertRaises(TimeoutError):
            self.device.commit([1500]*10, 1, allow_arm=True)
        self.assertEqual(sum(address == 0x18 for address, _ in self.reg.writes), 1)
        before = len(self.reg.writes)
        with self.assertRaises(RuntimeError):
            self.device.commit([1500]*10, 1, allow_arm=True)
        self.assertEqual(len(self.reg.writes), before)

    def test_capture_requires_all_initialized_and_only_one_changed(self):
        driver = CaptureDriver(config(), self.device)
        with self.assertRaises(RuntimeError):
            driver.read_state()
        self.device.commit([1500]*10, 1023, allow_arm=True)
        state = driver.read_state(); axes = state['adopted']
        self.reg.writes.clear()
        for invalid in (float('nan'), float('inf'), 1511, True):
            candidate = copy.deepcopy(axes); candidate[0]['value'] = invalid
            with self.assertRaises(ValueError):
                driver.apply_targets(candidate, [])
        candidate = copy.deepcopy(axes); candidate[0]['value'] += 5; candidate[1]['value'] += 5
        with self.assertRaises(ValueError):
            driver.apply_targets(candidate, [])
        with self.assertRaises(ValueError):
            driver.apply_targets(axes, [{'id':'wusong_slide','value':1}])
        self.assertEqual(self.reg.writes, [])
        axes[9]['value'] += 5
        result = driver.apply_targets(axes, [])
        self.assertEqual(result['adopted'][9]['value'], 1505)
        self.assertEqual([a['value'] for a in result['adopted'][:9]], [1500]*9)

    def test_missing_template_limits_rejected(self):
        template = json.loads((ROOT/'config/capture.servos.real.template.json').read_text())
        with self.assertRaises(ValueError):
            ConsoleController(self.device, template)

    def test_console_no_init_without_reference_and_exact_replay(self):
        console = ConsoleController(self.device)
        req = {'transport_id':uuid.uuid4().hex, 'operation':'initialize', 'payload':{'channel':1}}
        self.assertFalse(console.handle(req)['ok'])
        self.assertEqual(self.reg.writes, [])
        console.commissioning[IDS[0]] = dict(reference_verified=True, basis='unloaded_center',
                                             initial_us=1500, min_us=1490, max_us=1510)
        # A previously rejected command stays rejected, even if settings changed.
        self.assertFalse(console.handle(req)['ok'])
        req['transport_id'] = uuid.uuid4().hex
        first = console.handle(req)
        self.assertTrue(first['ok']); count = len(self.reg.writes)
        self.assertEqual(console.handle(req), first)
        self.assertEqual(len(self.reg.writes), count)
        changed = copy.deepcopy(req); changed['payload']['channel'] = 2
        with self.assertRaises(ValueError):
            console.handle(changed)
        jog = {'transport_id':uuid.uuid4().hex, 'operation':'jog', 'payload':{'channel':1,'delta_us':5}}
        self.assertTrue(console.handle(jog)['ok'])
        jog['transport_id'] = uuid.uuid4().hex; jog['payload']['delta_us'] = 11
        self.assertFalse(console.handle(jog)['ok'])
        self.assertEqual(self.device.status()['pulse_us'][0], 1505)
        self.assertEqual(self.device.status()['enabled_mask'], 1)

    def test_watchdog_heartbeat_never_rearms(self):
        self.device.commit([1500]*10, 1, allow_arm=True)
        self.reg.values.update({0x10:0, 8:0, 0x0c:2})
        self.reg.writes.clear()
        console = ConsoleController(self.device)
        result = console.handle({'transport_id':uuid.uuid4().hex,'operation':'heartbeat','payload':{}})
        self.assertTrue(result['ok']); self.assertFalse(result['result']['armed'])
        self.assertEqual(self.reg.writes, [])

    def test_maintenance_cannot_move_behind_capture_gui(self):
        from types import SimpleNamespace
        console = ConsoleController(self.device)
        console.capture = SimpleNamespace(owner='active-capture-session')
        for operation, payload in (('initialize', {'channel':1}), ('jog', {'channel':1,'delta_us':5})):
            ack = console.handle({'transport_id':uuid.uuid4().hex,'operation':operation,'payload':payload})
            self.assertFalse(ack['ok']); self.assertIn('GUI owns',ack['error'])
        self.assertEqual(self.reg.writes, [])

    def test_gateway_ignores_console_noise_and_stops_after_timeout(self):
        class FakeSerial:
            def __init__(self): self.lines=[]; self.sent=[]; self.reply=True
            def write(self, data):
                req=json.loads(data); self.sent.append(req)
                if self.reply:
                    ack={'transport_id':req['transport_id'],'ok':True,'result':{'armed':False,
                        'enabled_mask':0,'identity':'SP10','clock_hz':100000000,'period_us':20000}}
                    self.lines.extend([b'kernel: unrelated text\r\n', b'@@SP10@@'+json.dumps(ack).encode()+b'\r\n'])
            def readline(self, size): return self.lines.pop(0) if self.lines else b''
            def close(self): pass
        port=FakeSerial()
        with patch('serial_gateway.threading.Thread'):
            link=SerialLink(port,io.StringIO())
        self.assertEqual(port.sent[0]['operation'],'hello')
        port.reply=False
        with patch('serial_gateway.time.monotonic', side_effect=[0,0,2]):
            with self.assertRaises(TimeoutError): link.exchange('status',{})
        self.assertTrue(link.failed)
        before=len(port.sent)
        with self.assertRaises(RuntimeError): link.exchange('initialize',{'channel':1})
        self.assertEqual(len(port.sent),before)


if __name__ == '__main__':
    unittest.main()
