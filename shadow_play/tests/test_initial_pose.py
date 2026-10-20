import json
import queue
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'integrations/calibration'))
from initial_pose_model import (angles_to_pulses,validate_pulses,encode_profile,decode_profile,
                                DEFAULT_ANGLES,DEGREE_LIMITS)
from initial_pose_console import InitialPoseDevice,InitialPoseController
from initial_pose_session import InitialPoseSession
from servo_pwm_device import PwmDevice
from test_servo_commissioning import FakeRegisters
from initial_pose_gui import Worker


class InitialPoseTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.lock=Path(folder.name)/'lock';self.lock.write_text('retained incident')
        self.reg=FakeRegisters();self.device=InitialPoseDevice(self.reg,motion_inhibit_paths=[self.lock])
        self.controller=InitialPoseController(self.device)

    def request(self,**changes):
        payload=dict(pulse_us=[1500]*10,sequence=self.reg.read(0x20),observer_confirmed=True,initial_jump_acknowledged=True)
        payload.update(changes)
        return dict(transport_id=uuid.uuid4().hex,operation='initialize',payload=payload)

    def off(self):
        return self.controller.handle(dict(transport_id=uuid.uuid4().hex,operation='off',payload={}))

    def test_default_and_limits_profiles_and_bad_numbers(self):
        self.assertEqual(angles_to_pulses(DEFAULT_ANGLES),[1500]*10)
        for index,(lo,hi) in enumerate(DEGREE_LIMITS):
            for value in (lo,hi):
                angles=list(DEFAULT_ANGLES);angles[index]=value
                validate_pulses(angles_to_pulses(angles))
            for value in (lo-1,hi+1,float('nan'),float('inf'),True):
                angles=list(DEFAULT_ANGLES);angles[index]=value
                with self.assertRaises(ValueError):angles_to_pulses(angles)
        self.assertEqual(decode_profile(json.loads(json.dumps(encode_profile(DEFAULT_ANGLES)))),list(DEFAULT_ANGLES))
        for bad in ({},dict(schema='other',nominal_angles_deg=[135]*10)):
            with self.assertRaises(ValueError):decode_profile(bad)

    def test_readonly_start_and_generic_lock_still_blocks(self):
        self.controller.status();self.controller.tick();self.assertEqual(self.reg.writes,[])
        with self.assertRaises(ValueError):self.device.commit([1500]*10,1023,True)
        with self.assertRaises(RuntimeError):PwmDevice(self.reg,motion_inhibit_paths=[self.lock]).commit([1500]*10,1023,True)
        self.assertEqual(self.reg.writes,[])

    def test_exact_group_one_commit_and_preserved_locks(self):
        angles=[140,136,130,140,130,140,136,130,140,136]
        target=angles_to_pulses(angles)
        ack=self.controller.handle(self.request(pulse_us=target))
        self.assertTrue(ack['ok'],ack);self.assertEqual(ack['result']['pulse_us'],target)
        self.assertEqual(ack['result']['enabled_mask'],1023)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertEqual(self.lock.read_text(),'retained incident');self.assertIsNone(self.device.permit)

    def test_missing_confirmation_stale_sequence_and_invalid_group_never_arm(self):
        for changes in ({'observer_confirmed':False},{'initial_jump_acknowledged':False},{'sequence':99},
                {'sequence':True},{'pulse_us':[1500]*9},{'pulse_us':[1500.]*10},
                {'pulse_us':[500]*10},{'pulse_us':[True]*10},{'extra':1}):
            self.assertFalse(self.controller.handle(self.request(**changes))['ok'])
            self.assertIsNone(self.device.permit)
        self.assertEqual(self.reg.writes,[])

    def test_replay_does_not_move_and_live_group_blocks_new_target(self):
        request=self.request();self.assertTrue(self.controller.handle(request)['ok'])
        count=len(self.reg.writes)
        self.assertTrue(self.controller.handle(request)['ok']);self.assertEqual(len(self.reg.writes),count)
        self.assertFalse(self.controller.handle(self.request())['ok']);self.assertEqual(len(self.reg.writes),count)
        self.off();count=len(self.reg.writes)
        self.assertTrue(self.controller.handle(request)['ok']);self.assertEqual(len(self.reg.writes),count)
        self.assertFalse(self.device.status()['armed'])

    def test_timeout_never_retries_or_rearms(self):
        self.reg.apply=False
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertFalse(self.device.status()['armed']);self.assertIsNone(self.device.permit)
        self.reg.apply=True;count=len(self.reg.writes)
        self.assertFalse(self.controller.handle(self.request())['ok']);self.assertEqual(len(self.reg.writes),count)

    def test_lost_output_requires_explicit_stop(self):
        self.assertTrue(self.controller.handle(self.request())['ok'])
        self.device.off();self.controller.tick()
        self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertTrue(self.off()['ok']);self.assertTrue(self.controller.handle(self.request())['ok'])

    def test_lock_change_and_external_command_stop(self):
        self.assertTrue(self.controller.handle(self.request())['ok'])
        self.reg.values[0x80]=1600;self.controller.tick()
        self.assertFalse(self.device.status()['armed']);self.assertTrue(self.controller.output_lost)
        self.off();self.assertTrue(self.controller.handle(self.request())['ok'])
        self.lock.write_text('new stop');self.controller.tick()
        self.assertFalse(self.device.status()['armed']);self.off()
        self.assertFalse(self.controller.handle(self.request())['ok'])

    def test_startup_does_not_take_over_active_output(self):
        self.reg.values.update({0x10:1,8:1})
        with self.assertRaises(ValueError):InitialPoseController(self.device)
        self.assertEqual(self.reg.writes,[])

    def test_host_binds_current_sequence_checks_all_ten_and_stops_bad_ack(self):
        session=InitialPoseSession.__new__(InitialPoseSession)
        before=dict(sequence=12,armed=False,enabled_mask=0,pending=False,faults=0,pulse_us=[1500]*10)
        after=dict(before,sequence=13,armed=True,enabled_mask=1023)
        session.status=Mock(return_value=before);session._request=Mock(return_value=after);session.stop=Mock()
        self.assertEqual(session.initialize([1500]*10,True),after)
        self.assertEqual(session._request.call_args.args[1]['sequence'],12)
        for changes in ({'enabled_mask':511},{'sequence':14},{'pulse_us':[1500]*9},{'pending':True}):
            session._request.return_value=dict(after,**changes)
            with self.assertRaises(RuntimeError):session.initialize([1500]*10,True)
        self.assertEqual(session.stop.call_count,4)
        session._request.reset_mock()
        with self.assertRaises(ValueError):session.initialize([1500]*10,False)
        session._request.assert_not_called()

    def test_stop_before_queued_initialization_cancels_unsent_group(self):
        commands,events=queue.Queue(),queue.Queue();cancel=threading.Event();cancel.set()
        worker=Worker(commands,events,cancel);session=Mock();worker.session=session
        session.status.return_value=dict(armed=False,enabled_mask=0,pending=False,output_lost=False)
        commands.put(('initialize',[1500]*10));commands.put(('shutdown',None));worker.run()
        session.initialize.assert_not_called();session.close.assert_called_once()
        self.assertIn(('cancelled',None),list(events.queue))

    def test_worker_drops_session_on_output_loss_without_resending(self):
        commands,events=queue.Queue(),queue.Queue();worker=Worker(commands,events,threading.Event())
        session=Mock();worker.session=session;worker.active=True
        session.status.return_value=dict(armed=False,enabled_mask=0,pending=False,output_lost=True)
        commands.put((None,None));commands.put(('shutdown',None));worker.run()
        session.initialize.assert_not_called();session.close.assert_called_once()
        self.assertTrue(any(event=='error' for event,value in events.queue))

    def test_watchdog_fault_after_reconnect_is_reported_without_active_output(self):
        commands,events=queue.Queue(),queue.Queue();worker=Worker(commands,events,threading.Event())
        session=Mock();worker.session=session;worker.active=False
        session.status.return_value=dict(armed=False,enabled_mask=0,pending=False,faults=2,output_lost=False)
        commands.put((None,None));commands.put(('shutdown',None));worker.run()
        session.initialize.assert_not_called();session.close.assert_called_once()
        errors=[value for event,value in events.queue if event=='error']
        self.assertTrue(any('看门狗' in value and '0x02' in value and '重新连接不能清除' in value for value in errors))

    def test_host_latched_fault_does_not_send_reset_or_initialization(self):
        session=InitialPoseSession.__new__(InitialPoseSession)
        session.status=Mock(return_value=dict(sequence=1,armed=False,enabled_mask=0,pending=False,
            faults=2,pulse_us=[1500,1389]+[1500]*8,output_lost=False))
        session._request=Mock();session.stop=Mock()
        with self.assertRaisesRegex(RuntimeError,'看门狗超时.*0x02'):
            session.initialize([1500]*10,True)
        session._request.assert_not_called();session.stop.assert_not_called()


if __name__=='__main__':unittest.main()
