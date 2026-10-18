import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/calibration'))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))
from test_servo_commissioning import FakeRegisters
from v20_first_direction import (FirstDirectionDevice, HostLease, ROUTE, MASK, IMAGE, SCHEMA,
                                 INTERRUPTED_PULSES, INTERRUPTED_BOOT,
                                 LATEST_PULSES, route,
                                 HISTORICAL_SOURCE, MIDPOINT, digest, run_check, validate_plan)
from run_v20_first_direction import parse_event, FreshCamera, completed_camera_reference


class Clock:
    now = 0.
    begun = True
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds
    def check(self): pass


def plan():
    return dict(schema=SCHEMA, session_id='1' * 32, boot_id='12345678-1234-1234-1234-123456789012',
                expected_sequence=0, expected_pulse_us=MIDPOINT[:], route_sha256=digest(ROUTE),
                historical_source_sha256=HISTORICAL_SOURCE, operator_midpoint_reference=True,
                onsite_observer=True, camera_required=False, enabled_mask=MASK, interruption_reviewed=False)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.locks = [self.path / 'global', self.path / 'local']
        for f in self.locks: f.write_text('inhibit')
        self.clock = Clock()
        self.reg = FakeRegisters()
        self.p = plan()

    def device(self, **kwargs):
        options = dict(boot_id=self.p['boot_id'], marker=dict(boot_id=self.p['boot_id'], sha256=IMAGE),
            used_path=self.path / 'used', motion_inhibit_paths=self.locks,
            cancel_path=self.path / 'cancel', clock=self.clock)
        options.update(kwargs)
        return FirstDirectionDevice(self.reg, self.p, self.clock, **options)

    def test_fixed_route_and_single_axis(self):
        self.assertEqual(len(ROUTE), 301)
        self.assertEqual(ROUTE[0], MIDPOINT)
        self.assertEqual(ROUTE[-1], MIDPOINT)
        self.assertEqual(ROUTE[100][6], 1540)
        self.assertEqual(ROUTE[150][6], 1540)
        self.assertTrue(all(p[:6] + p[7:] == [1500] * 9 for p in ROUTE))
        self.assertEqual(max(abs(a[6] - b[6]) for a, b in zip(ROUTE, ROUTE[1:])), 1)

    def test_construction_and_inspection_are_read_only(self):
        self.device().check()
        self.assertEqual(self.reg.writes, [])

    def test_complete_and_locked_normal_driver(self):
        d = self.device()
        with self.assertRaises(RuntimeError): d._check_motion_allowed()
        rows = []
        run_check(d, rows.append, sleep=self.clock.sleep)
        self.assertTrue(rows[-1]['route_complete'])
        self.assertEqual(rows[-1]['state']['sequence'], 302)
        self.assertFalse(rows[-1]['state']['armed'])
        self.assertEqual(rows[-1]['state']['pulse_us'], MIDPOINT)
        self.assertEqual({r['state']['enabled_mask'] for r in rows[:-1]}, {64})
        self.assertEqual([f.read_text() for f in self.locks], ['inhibit', 'inhibit'])
        self.assertEqual(sum(a == 0x10 for a, v in self.reg.writes), 1)
        self.assertGreaterEqual(self.clock.now, 12)

    def test_bad_boot_and_marker_cannot_write(self):
        for args in (dict(boot_id='other'), dict(marker=dict(boot_id=self.p['boot_id'], sha256='x'))):
            with self.assertRaises(ValueError): self.device(**args)
        self.assertEqual(self.reg.writes, [])

    def test_plan_rejects_modified_targets_mask_source_or_attendance(self):
        for key, value in [('route_sha256', '0' * 64), ('enabled_mask', 960),
                           ('historical_source_sha256', '0' * 64), ('onsite_observer', False),
                           ('camera_required', None), ('expected_pulse_us', [1540] * 10)]:
            p = plan(); p[key] = value
            with self.assertRaises(ValueError): validate_plan(p)

    def test_stale_or_nonoff_start(self):
        for address, value in [(0x20, 1), (8, 64), (0x10, 1), (0x24, 1), (0x0c, 1), (0x80, 1501)]:
            self.reg = FakeRegisters(); self.reg.values[address] = value
            with self.assertRaises(RuntimeError): self.device()
            self.assertEqual(self.reg.writes, [])

    def test_wrong_frame_or_multiple_axes_never_write(self):
        d = self.device(); d.begin()
        for p, mask in [(ROUTE[0], 960), ([1501] * 10, 64), (ROUTE[100], 64)]:
            with self.assertRaises(ValueError): d.commit(p, mask, allow_arm=True)
        self.assertEqual(self.reg.writes, [])

    def test_no_automatic_rearm_after_hold_loss(self):
        d = self.device(); d.begin(); d.commit(ROUTE[0], MASK, allow_arm=True)
        d.off(); self.clock.sleep(.04)
        before = len(self.reg.writes)
        with self.assertRaises(RuntimeError): d.commit(ROUTE[1], MASK)
        self.assertEqual(len(self.reg.writes), before)

    def test_single_use_and_no_fast_catchup(self):
        d = self.device(); d.begin()
        with self.assertRaises(RuntimeError): d.begin()
        d.commit(ROUTE[0], MASK, allow_arm=True)
        with self.assertRaises(RuntimeError): d.commit(ROUTE[1], MASK)
        d.off()
        self.reg = FakeRegisters()
        with self.assertRaises(FileExistsError): self.device().begin()

    def test_lock_change_and_cancel_stop_in_place(self):
        for stop in ('lock', 'cancel'):
            self.setUp()
            d = self.device(); rows = []
            def emit(row):
                rows.append(row)
                if row['event'] == 'frame' and row['index'] == 40:
                    if stop == 'lock': self.locks[0].write_text('changed')
                    else: (self.path / 'cancel').write_text('stop')
            with self.assertRaises(RuntimeError): run_check(d, emit, sleep=self.clock.sleep)
            self.assertFalse(rows[-1]['route_complete'])
            self.assertFalse(d.status()['armed'])
            self.assertNotEqual(d.status()['pulse_us'][6], 1500)

    def test_host_loss_and_log_failure_always_off(self):
        for fail in ('host', 'log'):
            self.setUp()
            d = self.device(); rows = []
            def emit(row):
                rows.append(row)
                if row['event'] == 'frame' and row['index'] == 45:
                    if fail == 'log': raise OSError('log unavailable')
                    def lost(): raise RuntimeError('Host lost')
                    self.clock.check = lost
            with self.assertRaises((RuntimeError, OSError)): run_check(d, emit, sleep=self.clock.sleep)
            self.assertFalse(d.status()['armed'])
            self.assertEqual(d.status()['enabled_mask'], 0)
            self.assertEqual(sum(a == 0x10 for a, v in self.reg.writes), 1)

    def test_late_schedule_aborts_without_return(self):
        d = self.device(); rows = []
        def emit(row):
            rows.append(row)
            if row['event'] == 'frame' and row['index'] == 50: self.clock.sleep(.2)
        with self.assertRaises(RuntimeError): run_check(d, emit, sleep=self.clock.sleep)
        self.assertFalse(rows[-1]['route_complete'])
        self.assertFalse(d.status()['armed'])

    def test_unknown_adoption_not_retried(self):
        self.reg.apply = False
        d = self.device(); rows = []
        with self.assertRaises(TimeoutError): run_check(d, rows.append, sleep=self.clock.sleep)
        self.assertEqual(sum(a == 0x18 for a, v in self.reg.writes), 1)
        self.assertFalse(d.status()['armed'])

    def test_host_protocol_begin_lease_stop_and_expiry(self):
        for bad in (b': # V20_STOP\n', b': # V20_LEASE ' + b'1' * 32 + b'\n',
                    b'\n', b'x' * 121):
            host = HostLease(1, '1' * 32, self.clock)
            with patch('v20_first_direction.select.select', return_value=([1], [], [])), \
                    patch('v20_first_direction.os.read', return_value=bad):
                with self.assertRaises(RuntimeError): host.check()
        host = HostLease(1, '1' * 32, self.clock)
        with patch('v20_first_direction.select.select', return_value=([1], [], [])), \
                patch('v20_first_direction.os.read', return_value=b': # V20_BEGIN ' + b'1' * 32 + b'\n'):
            host.check()
            self.assertTrue(host.begun)
            with self.assertRaises(RuntimeError): host.check()
        self.clock.sleep(1.51)
        with patch('v20_first_direction.select.select', return_value=([], [], [])):
            with self.assertRaises(RuntimeError): host.check()

    def test_board_ready_after_unterminated_shell_prompt(self):
        event = '@@V20STEP@@{"event":"ready"}'
        self.assertEqual(parse_event(event), {'event': 'ready'})
        self.assertEqual(parse_event('root@shadowdpupetalinux:~# ' + event), {'event': 'ready'})
        self.assertIsNone(parse_event('root@shadowdpupetalinux:~# '))
        with self.assertRaises(RuntimeError): parse_event('unexpected ' + event)

    def test_exact_interrupted_reference_and_single_microsecond_rejoin(self):
        self.p.update(interruption_reviewed=True, boot_id=INTERRUPTED_BOOT,
                      expected_sequence=14, expected_pulse_us=INTERRUPTED_PULSES,
                      route_sha256=digest(route(1501)))
        self.reg.values[0x20] = 14
        self.reg.values[0x98] = 1501
        d = self.device(); rows = []
        run_check(d, rows.append, sleep=self.clock.sleep)
        self.assertEqual(rows[0]['state']['pulse_us'], INTERRUPTED_PULSES)
        self.assertEqual(rows[0]['state']['sequence'], 15)
        self.assertEqual(rows[-1]['state']['sequence'], 316)
        self.assertTrue(rows[-1]['route_complete'])
        p = copy.deepcopy(self.p); p['expected_sequence'] = 15
        with self.assertRaises(ValueError): validate_plan(p)

    def test_clock_crosses_deadline_during_read_checks(self):
        d = self.device(); rows = []
        original_check = self.clock.check
        def check():
            self.clock.now += .0001
            original_check()
        self.clock.check = check
        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            self.clock.sleep(seconds)
        run_check(d, rows.append, sleep=sleep)
        self.assertTrue(rows[-1]['route_complete'])

    def test_accumulated_scheduler_delay_does_not_require_catchup(self):
        d = self.device(); rows = []
        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            self.clock.sleep(seconds + .001)
        run_check(d, rows.append, sleep=sleep)
        frames = rows[:-1]
        self.assertTrue(rows[-1]['route_complete'])
        self.assertGreater(frames[-1]['elapsed_s'], 12.15)
        self.assertLess(frames[-1]['elapsed_s'], 16)
        self.assertTrue(all(b['elapsed_s'] - a['elapsed_s'] >= .04 - 1e-8
                            for a, b in zip(frames, frames[1:])))

    def test_latest_off72_binding_starts_without_a_jump(self):
        self.p.update(interruption_reviewed=True, boot_id=INTERRUPTED_BOOT,
                      expected_sequence=72, expected_pulse_us=LATEST_PULSES,
                      route_sha256=digest(route(1524)))
        self.reg.values[0x20] = 72
        self.reg.values[0x98] = 1524
        d = self.device(); rows = []
        run_check(d, rows.append, sleep=self.clock.sleep)
        self.assertEqual(rows[0]['state']['pulse_us'], LATEST_PULSES)
        self.assertEqual(rows[-1]['state']['sequence'], 374)
        self.assertEqual(rows[-1]['state']['pulse_us'], MIDPOINT)
        self.assertEqual(max(x['state']['pulse_us'][6] for x in rows), 1540)
        self.assertEqual(max(abs(a['state']['pulse_us'][6]-b['state']['pulse_us'][6])
                             for a,b in zip(rows,rows[1:])), 1)

    def test_dry_run_reports_the_actual_bound_route_without_execution(self):
        p = plan()
        p.update(interruption_reviewed=True, boot_id=INTERRUPTED_BOOT, expected_sequence=72,
                 expected_pulse_us=LATEST_PULSES, route_sha256=digest(route(1524)))
        file = self.path / 'dry.json'; file.write_text(json.dumps(p))
        result = subprocess.run([sys.executable, str(ROOT / 'integrations/calibration/v20_first_direction.py'), str(file)],
                                capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertTrue(report['dry_run'])
        self.assertEqual(report['route_sha256'], p['route_sha256'])

    def test_camera_guard_rejects_stale_stalled_and_bad_jpeg(self):
        from PIL import Image
        folder = self.path / 'camera'; session = folder / 'session'; session.mkdir(parents=True)
        (folder / 'current.json').write_text(json.dumps(dict(directory=str(session.resolve()))))
        status = dict(state='streaming', frames=1, updated_unix_ms=100000)
        (session / 'status.json').write_text(json.dumps(status))
        Image.new('RGB', (4, 4)).save(session / 'latest.jpg', format='JPEG')
        camera = FreshCamera(folder, clock=lambda: 100, monotonic=self.clock)
        self.assertEqual(camera.sample()['frame'], 1)
        self.clock.sleep(1.51)
        with self.assertRaises(RuntimeError): camera.sample()
        status.update(frames=2, updated_unix_ms=98000)
        (session / 'status.json').write_text(json.dumps(status))
        with self.assertRaises(RuntimeError): camera.sample()
        status.update(updated_unix_ms=100000)
        (session / 'status.json').write_text(json.dumps(status))
        (session / 'latest.jpg').write_bytes(b'not a JPEG')
        with self.assertRaises(OSError): camera.sample()

    def test_user_stop_record_cannot_be_used_for_a_new_automatic_recheck(self):
        record = dict(route_complete=True, state=self.device().status(), boot_id=self.p['boot_id'])
        self.assertEqual(completed_camera_reference(record)['sequence'], 0)
        record['user_requested_remain_stopped'] = True
        with self.assertRaises(RuntimeError): completed_camera_reference(record)
        self.assertEqual(self.reg.writes, [])


if __name__ == '__main__': unittest.main()
