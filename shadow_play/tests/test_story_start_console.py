import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from attended_recovery_review import STORY_START, review
from story_start_console import Controller
from test_servo_commissioning import FakeRegisters


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.locks = [self.root/'a', self.root/'b']
        for p in self.locks: p.write_text('incident')
        self.now = 0
        self.reg = FakeRegisters()
        self.events = []
        self.c = Controller(self.reg, 'boot', self.events.append, clock=lambda: self.now,
                            motion_inhibit_paths=self.locks, cancel_path=self.root/'cancel')
        self.plan = dict(operator_authorized=True, observer_ready=True,
                         linkage_clearance_reviewed=True, board_boot_id='boot', expected_sequence=0,
                         start=dict(basis='observed_commanded_pose_unchanged',
                                    axes_moved_since_verification=False,
                                    evidence='simulation only', pulses_us=list(STORY_START)),
                         route=dict(loaded_path_reviewed=True, frame_period_ms=20,
                                    target_id='story_start_v3', frames_us=[list(STORY_START)]*2))

    def call(self, op, payload=None, ident=None):
        return self.c.handle(dict(transport_id=ident or uuid.uuid4().hex,
                                 operation=op, payload=payload or {}))

    def load(self):
        data = json.dumps(self.plan).encode()
        self.assertTrue(self.call('upload_begin', {'bytes':len(data)})['ok'])
        self.assertTrue(self.call('upload_chunk', {'offset':0, 'base64':base64.b64encode(data).decode()})['ok'])
        return self.call('upload_end')

    def active(self):
        self.reg.values.update({8:1023, 0x10:1})
        for i, p in enumerate(STORY_START): self.reg.values[0x80+i*4] = p

    def test_connect_and_load_do_not_move_or_arm(self):
        self.call('hello'); self.call('heartbeat'); self.load()
        self.assertFalse(self.c.status()['ready'])
        self.assertFalse(self.call('start')['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_off_available_without_plan_and_never_enables(self):
        self.active()
        self.assertTrue(self.call('off')['ok'])
        self.assertFalse(self.reg.read(0x10))
        self.assertFalse(any(a in (0x18,0x10) for a,v in self.reg.writes))

    def test_valid_route_stops_and_cannot_repeat(self):
        self.active(); self.load()
        ident = uuid.uuid4().hex
        first = self.call('start', ident=ident)
        self.assertTrue(first['ok'])
        self.assertEqual(self.call('start', ident=ident), first)
        self.assertFalse(self.call('start')['ok'])
        # Duplicate start must not stop or restart the active route.
        self.assertTrue(self.c.running)
        for _ in range(110):
            self.now += .01; self.call('heartbeat'); self.c.tick()
        self.assertFalse(self.c.running)
        self.assertEqual(self.events[-1]['reason'], 'route_complete')
        self.assertFalse(self.reg.read(0x10))
        self.assertFalse(self.call('start')['ok'])
        self.assertTrue(all(p.read_text()=='incident' for p in self.locks))

    def test_lease_loss_stops_before_motion(self):
        self.active(); self.load(); self.call('start')
        self.now += .8; self.c.tick()
        self.assertFalse(self.reg.read(0x10))
        self.assertFalse(any(a == 0x18 for a,v in self.reg.writes))

    def test_stale_boot_and_sequence_rejected(self):
        self.active(); self.plan['board_boot_id']='old'; self.load()
        self.assertFalse(self.call('start')['ok'])
        self.plan['board_boot_id']='boot'; self.plan['expected_sequence']=1; self.load()
        self.assertFalse(self.call('start')['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_no_force_arm_unlock_or_unreviewed_route(self):
        for op in ('force','initialize','arm','unlock'):
            self.assertFalse(self.call(op)['ok'])
        self.plan['start']['basis']='visual_estimate'
        self.assertFalse(self.load()['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_reordered_upload_rejected(self):
        self.call('upload_begin', {'bytes':3})
        self.assertFalse(self.call('upload_chunk', {'offset':1,'base64':'YWJj'})['ok'])

    def test_targets_do_not_confuse_center_and_story(self):
        self.assertEqual(review(self.plan)['reasons'], [])
        self.plan['route']['target_id']='assembly_center'
        self.assertIn('assembly_center_is_1500us', review(self.plan)['reasons'])
        for value in (None, [], 42):
            self.assertTrue(review(value)['reasons'])
        self.plan['route']=None
        self.assertTrue(review(self.plan)['reasons'])

    def test_reject_route_outside_existing_axis_inset(self):
        point=list(STORY_START); point[1]=1188
        self.plan['route']['frames_us']=[list(STORY_START), point, list(STORY_START)]
        self.assertIn('axis_inset_limit_exceeded', review(self.plan)['reasons'])
        self.assertFalse(self.load()['ok'])
        self.assertEqual(self.reg.writes, [])

    def test_limits_match_existing_button_configuration(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
        from servo_button_jog import load_button_limits
        from attended_recovery_review import PULSE_LIMITS
        limits=load_button_limits()
        self.assertEqual(tuple(limits[i] for i in range(1,11)), PULSE_LIMITS)

    def test_reviewed_hold_is_bounded_and_never_arms(self):
        self.active(); self.load()
        self.assertTrue(self.c.holding)
        for _ in range(151):
            self.now += .1; self.call('heartbeat'); self.c.tick()
        self.assertFalse(self.reg.read(0x10))
        self.assertEqual(self.events[-1]['reason'], 'reviewed_handoff_expired')
        self.assertFalse(any(a == 0x10 for a,v in self.reg.writes))


if __name__ == '__main__': unittest.main()
