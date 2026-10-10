"""Contract tests for board handoff and offline fitting; no hardware is accessed."""
import copy
import importlib.util
import json
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import board_server as server
import tcp_bridge as bridge
try:
    import fit_local
except ModuleNotFoundError as error:
    if error.name != 'numpy':
        raise
    fit_local = None


def config():
    return {'version': 1, 'simulation_only': False, 'reference_view': 'front',
        'stage': {'width_mm': 800, 'height_mm': 500},
        'axes': [{'id': name, 'rod': 'wusong_neck', 'unit': 'us', 'min': 1000,
                  'max': 2000, 'initial': 1500, 'jog_step': 10, 'max_step': 100} for name in ('pan', 'tilt')],
        'slides': [{'id': 'slide', 'unit': 'mm', 'value': 10, 'state_kind': 'commanded',
                    'controllable': True, 'min': 0, 'max': 100, 'jog_step': 1, 'max_step': 5}]}


class Driver:
    def __init__(self):
        self.calls = 0
        self.current = {'adopted': [{'axis_id': a['id'], 'value': a['initial'], 'unit': a['unit']} for a in config()['axes']],
                        'slides': config()['slides'], 'feedback': None}
        for key in ('min', 'max', 'jog_step', 'max_step'):
            self.current['slides'][0].pop(key)
    def read_state(self):
        return copy.deepcopy(self.current)
    def apply_targets(self, axes, slides):
        self.calls += 1
        for axis in axes:
            axis['value'] = round(axis['value'])
        self.current.update(adopted=axes, slides=slides)
        return self.read_state()


def request(seq=1, kind='capture_sync', value=1550.2):
    state = Driver().read_state()
    state['adopted'][0]['value'] = value
    return {'version': 2, 'type': kind, 'session_id': 'test_session', 'seq': seq,
            'axes': state['adopted'], 'slides': state['slides']}


class HandoffTests(unittest.TestCase):
    def test_sync_adopted_values_dedup_and_fault(self):
        driver = Driver()
        control = server.Controller(config(), driver)
        ack = control.handle(request())
        self.assertTrue(ack['accepted'])
        self.assertEqual(ack['adopted'][0]['value'], 1500)
        self.assertEqual(driver.calls, 0)
        command = request(2, 'capture_target')
        ack = control.handle(command)
        self.assertEqual(ack['adopted'][0]['value'], 1550)
        self.assertIsNone(ack['feedback'])
        self.assertEqual(control.handle(command), ack)
        self.assertEqual(driver.calls, 1)
        with self.assertRaises(ValueError):
            control.handle(request(2, 'capture_target', 1551))
        self.assertFalse(control.handle(request(3, 'capture_target', 1800))['accepted'])
        self.assertFalse(control.handle(request(4, 'capture_target', 1551))['accepted'])
        self.assertEqual(driver.calls, 1)
        self.assertTrue(control.handle(request(5))['accepted'])

    def test_bad_units_and_second_owner(self):
        driver = Driver()
        control = server.Controller(config(), driver)
        self.assertFalse(control.handle(request(1, 'capture_target'))['accepted'])
        self.assertTrue(control.handle(request(2))['accepted'])
        bad = request(3, 'capture_target')
        bad['axes'][0]['unit'] = 'deg'
        self.assertFalse(control.handle(bad)['accepted'])
        other = request(1)
        other['session_id'] = 'other'
        self.assertFalse(control.handle(other)['accepted'])
        self.assertEqual(driver.calls, 0)

    def test_adapter_failure_does_not_retry(self):
        class Failed(Driver):
            def apply_targets(self, axes, slides):
                self.calls += 1
                raise RuntimeError('partial commit, state unknown')
        driver = Failed()
        control = server.Controller(config(), driver)
        control.handle(request())
        command = request(2, 'capture_target')
        self.assertFalse(control.handle(command)['accepted'])
        self.assertFalse(control.handle(command)['accepted'])
        self.assertEqual(driver.calls, 1)

    def test_tcp_real_service_contract(self):
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
            with socketserver.TCPServer(('127.0.0.1', 0), server.Handler) as tcp:
                tcp.controller = server.Controller(config(), Driver())
                tcp.log = log
                thread = threading.Thread(target=tcp.serve_forever, daemon=True)
                thread.start()
                try:
                    ack = bridge.forward(request(), *tcp.server_address, timeout=2)
                    self.assertTrue(ack['accepted'])
                    ack = bridge.forward(request(2, 'capture_target'), *tcp.server_address, timeout=2)
                    self.assertEqual(ack['adopted'][0]['value'], 1550)
                    self.assertEqual(tcp.controller.driver.calls, 1)
                finally:
                    tcp.shutdown()
                    thread.join(2)

    @unittest.skipIf(fit_local is None, 'numpy required for offline fitting tests')
    def test_fit_and_context_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            cfg = config()
            (path/'config.snapshot.json').write_text(json.dumps(cfg))
            (path/'metadata.json').write_text(json.dumps({'session_id': 's', 'simulation_only': False, 'reference_view': 'front'}))
            (path/'calibration_000001.json').write_text(json.dumps({'reference_view': 'front'}))
            (path/'frame.png').write_bytes(b'fixture evidence')
            rows = []
            for i in range(5):
                for j in range(5):
                    state = Driver().read_state()
                    state.update(accepted=True, confirmed=True, backend='external')
                    state['adopted'][0]['value'] = 1450+20*i+2*j
                    state['adopted'][1]['value'] = 1450+3*i+20*j
                    state['axes'] = state.pop('adopted')
                    rows.append({'sample_id': 'p'+str(len(rows)), 'session_id': 's', 'rod': 'wusong_neck',
                        'stage_mm': {'x': 200+10*i, 'y': 100+10*j}, 'state': state,
                        'calibration_id': 'calibration_000001', 'frame_path': 'frame.png'})
            def save():
                (path/'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
            save()
            fit = fit_local.fit(path, 'wusong_neck')
            self.assertLess(fit['validation']['forward_max_error_mm'], 1e-8)
            self.assertFalse(fit['deployment_ready'])
            rows[-1]['state']['slides'][0]['value'] += 1
            save()
            with self.assertRaisesRegex(ValueError, 'other axes'):
                fit_local.fit(path, 'wusong_neck')
            rows[-1]['state']['slides'][0]['value'] -= 1
            rows[-1]['state']['backend'] = 'simulation'
            save()
            with self.assertRaisesRegex(ValueError, 'only external'):
                fit_local.fit(path, 'wusong_neck')


if __name__ == '__main__':
    unittest.main()
