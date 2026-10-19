import sys,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/calibration'));sys.path.insert(0,str(ROOT/'tools'))
from attended_angle_console import AttendedAngleDevice,AttendedAngleController
from attended_angle_gui import AttendedAngleSession
from servo_pwm_device import PwmDevice
from servo_manual_session import angle_to_pulse
from test_servo_commissioning import FakeRegisters

class AngleTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.lock=Path(folder.name)/'lock';self.lock.write_text('retained incident')
        self.reg=FakeRegisters();self.device=AttendedAngleDevice(self.reg,motion_inhibit_paths=[self.lock])
        self.now=0;self.controller=AttendedAngleController(self.device,clock=lambda:self.now)
    def request(self,channel=1,pulse=1500,**changes):
        p=dict(channel=channel,pulse_us=pulse,observer_confirmed=True,initial_jump_acknowledged=True,sequence=self.reg.read(0x20));p.update(changes)
        return dict(transport_id=uuid.uuid4().hex,operation='move',payload=p)
    def test_start_readonly_and_endpoints_for_all_channels(self):
        self.controller.status();self.assertEqual(self.reg.writes,[])
        for channel in range(1,11):
            for angle in (0,135,270):
                before=self.device.status()['pulse_us'];pulse=angle_to_pulse(angle)
                ack=self.controller.handle(self.request(channel,pulse));self.assertTrue(ack['ok'],ack)
                expected=before[:];expected[channel-1]=pulse
                self.assertEqual(ack['result']['pulse_us'],expected);self.assertEqual(ack['result']['enabled_mask'],1<<(channel-1))
            self.controller.handle(dict(transport_id=uuid.uuid4().hex,operation='off',payload={}))
        self.assertEqual(self.lock.read_text(),'retained incident')
    def test_no_generic_motion_unlock(self):
        with self.assertRaises(ValueError):self.device.commit([1500]*10,1,True)
        with self.assertRaises(RuntimeError):PwmDevice(self.reg,motion_inhibit_paths=[self.lock]).commit([1500]*10,1,True)
        self.assertEqual(self.reg.writes,[])
    def test_bad_targets_acknowledgements_and_stale_state_never_arm(self):
        for changes in ({'channel':True},{'channel':11},{'pulse_us':499},{'pulse_us':2501},{'pulse_us':1500.0},
                        {'observer_confirmed':False},{'initial_jump_acknowledged':False},{'sequence':99},{'extra':1}):
            self.assertFalse(self.controller.handle(self.request(**changes))['ok'])
            self.assertIsNone(self.device.permit)
        # A stale request may issue OFF as cleanup, but never ARM or COMMIT.
        self.assertFalse(any(a in (0x10,0x18) for a,v in self.reg.writes))
    def test_same_channel_updates_hold_and_switch_rejected(self):
        self.assertTrue(self.controller.handle(self.request())['ok']);self.reg.writes.clear()
        self.assertTrue(self.controller.handle(self.request(pulse=1600))['ok'])
        self.assertFalse(any(a in (0x0c,0x10) for a,v in self.reg.writes))
        self.assertFalse(self.controller.handle(self.request(channel=2))['ok'])
        self.now=3600;self.controller.tick();self.assertTrue(self.device.status()['armed'])
        self.assertIsNone(self.controller.status()['center_hold_seconds'])
    def test_replay_and_lock_change(self):
        req=self.request();self.assertTrue(self.controller.handle(req)['ok']);writes=len(self.reg.writes)
        self.assertTrue(self.controller.handle(req)['ok']);self.assertEqual(len(self.reg.writes),writes)
        self.lock.write_text('new stop');self.controller.tick();self.assertFalse(self.device.status()['armed'])
        self.assertFalse(self.controller.handle(self.request())['ok'])
    def test_timeout_cleans_permit_and_stops(self):
        self.reg.apply=False;self.assertFalse(self.controller.handle(self.request())['ok'])
        self.assertFalse(self.device.status()['armed']);self.assertIsNone(self.device.permit)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
    def test_host_sequence_and_wrong_ack_stop(self):
        session=AttendedAngleSession.__new__(AttendedAngleSession)
        before=dict(sequence=14,pulse_us=[1500]*10,armed=False,enabled_mask=0,pending=False,faults=0)
        session.status=Mock(return_value=before)
        accepted=dict(before,sequence=15,pulse_us=[1500,1600]+[1500]*8,armed=True,enabled_mask=2)
        session._request=Mock(return_value=accepted);session.stop=Mock()
        self.assertEqual(session.move(2,1600,True),accepted)
        operation,payload=session._request.call_args.args
        self.assertEqual(operation,'move');self.assertEqual(payload['sequence'],14)
        session._request.return_value=dict(accepted,enabled_mask=1)
        with self.assertRaises(RuntimeError):session.move(2,1600,True)
        session.stop.assert_called_once()

    def test_manual_capability_reports_existing_lock_without_enabling_motion(self):
        state=self.controller.status()
        self.assertTrue(state['incident_lock_retained'])
        self.assertTrue(state['manual_diagnostics_available'])
        self.assertEqual(state['manual_command_policy'],'attended-single-axis')
        self.assertEqual(state['manual_channel_range'],[1,10])
        self.assertEqual(self.reg.writes,[])
        self.lock.write_text('new stop')
        self.assertFalse(self.controller.status()['manual_diagnostics_available'])

    def test_host_requires_installed_manual_capability(self):
        session=AttendedAngleSession.__new__(AttendedAngleSession)
        state=self.controller.status()
        self.assertTrue(session.valid_service(state))
        for key,value in [('manual_command_policy','unloaded'),('manual_diagnostics_available',False),
                          ('manual_channel_range',[1,6]),('service','unloaded-manual-v2')]:
            changed=dict(state);changed[key]=value
            self.assertFalse(session.valid_service(changed))

if __name__=='__main__':unittest.main()
