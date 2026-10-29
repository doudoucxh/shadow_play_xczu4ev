"""Protocol vectors and teach/replay failure behavior, with no hardware I/O."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from shadow_play.bus_servo import protocol
from shadow_play.bus_servo.device import SimulationDevice, WireBus
from shadow_play.bus_servo.model import Profile, new_recording, validate_recording, playback_plan, save_recording
from shadow_play.bus_servo.service import Controller
from shadow_play.bus_servo.session import TeachingSession
from shadow_play.bus_servo.provision import assign_id
from shadow_play.bus_servo.load_candidate import verify, digest

PROFILE=Path(__file__).resolve().parents[1]/'config/bus_servo.json'


def recording(profile, simulation=True):
    r=new_recording(profile,[1,7],simulation,10)
    for i,p in enumerate((1500,1510,1520,1510,1500)):
        r['samples'].append({'t':i*.1,'positions':{'1':p,'7':3000-p},'axis_t':{'1':i*.1,'7':i*.1}})
    r['complete']=True
    return r


class ProtocolTests(unittest.TestCase):
    def test_manual_ascii_vectors(self):
        self.assertEqual(protocol.move(3,1800,1000),b'#003P1800T1000!')
        self.assertEqual(protocol.command(0,'RAD'),b'#000PRAD!')
        self.assertEqual(protocol.command(10,'ULK'),b'#010PULK!')
        self.assertEqual(protocol.parse_reply(b'#003P1500!',3,'position'),1500)
        self.assertEqual(protocol.parse_reply(b'#000PSERVO.C(310.3)!',0,'version'),'SERVO.C(310.3)')

    def test_bad_echo_ids_frames_ranges(self):
        for data in (b'#003PRAD!',b'#004P1500!',b'#003P1500!#003P1500!',b'#003P2501!',b'#003PERR:3!',b'#003P1500',b'#003POK!'):
            with self.subTest(data=data),self.assertRaises((ValueError,protocol.ProtocolError)):
                protocol.parse_reply(data,3,'position')
        for p in (True,499,2501,1500.0):
            with self.assertRaises(ValueError):protocol.move(1,p,1000)
        with self.assertRaises(ValueError):protocol.command(255,'PID0')

    def test_health_checksum_protection_and_echo(self):
        self.assertEqual(protocol.health_request(1),bytes.fromhex('ff ff 01 04 02 48 01 af'))
        good=bytes.fromhex('ff ff 01 03 00 00 fb')
        self.assertEqual(protocol.parse_health(good,1),0)
        for bad in (good[:-1]+b'\x00',protocol.health_request(1),bytes.fromhex('ff ff 01 03 00 09 f2')):
            with self.assertRaises(protocol.ProtocolError):protocol.parse_health(bad,1)

    def test_no_transmit_on_stale_or_faulted_bus(self):
        class Registers:
            def __init__(self,value):self.value=value;self.writes=[]
            def read(self,offset):return self.value if offset==0x100 else 0
            def write(self,*args):self.writes.append(args)
        import threading
        for value in (1,0x100,0x1000000):
            r=Registers(value);bus=WireBus(r,0x100,threading.Lock())
            with self.assertRaises(protocol.ProtocolError):bus.exchange(b'#001PRAD!')
            self.assertEqual(r.writes,[])


class ModelTests(unittest.TestCase):
    def setUp(self):self.profile=Profile.load(PROFILE)

    def test_mapping_roundtrip_and_duplicate_id(self):
        self.assertEqual(self.profile.axes[6].bus,'person')
        self.assertEqual(self.profile.axes[7].bus,'tiger')
        self.assertEqual(self.profile.axes[1].position(135),1500)
        for p in range(600,2400):
            self.assertEqual(self.profile.axes[1].position(self.profile.axes[1].degrees(p)),p)
        d=copy.deepcopy(self.profile.data);d['axes'][1]['id']=1
        with self.assertRaises(ValueError):Profile(d)

    def test_recording_validation(self):
        r=recording(self.profile)
        validate_recording(r,self.profile)
        with self.assertRaises(ValueError):validate_recording(r,self.profile,live=True)
        for mutation in ('nan','missing','order','incomplete','profile'):
            bad=copy.deepcopy(r)
            if mutation=='nan':bad['samples'][2]['t']=float('nan')
            elif mutation=='missing':del bad['samples'][2]['positions']['7']
            elif mutation=='order':bad['samples'][2]['t']=0
            elif mutation=='incomplete':bad['complete']=False
            else:bad['profile_sha256']='wrong'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_recording(bad,self.profile)

    def test_subset_speed_and_no_overwrite(self):
        r=recording(self.profile);plan=playback_plan(r,self.profile,[1],.5)
        self.assertEqual(set(plan[0][1]),{'1'});self.assertEqual(plan[0][2],200)
        with self.assertRaises(ValueError):playback_plan(r,self.profile,[2],.5)
        r['samples'][1]['positions']['1']=2000
        with self.assertRaises(ValueError):playback_plan(r,self.profile,[1],1)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'take.json';save_recording(p,r)
            with self.assertRaises(FileExistsError):save_recording(p,r)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile.load(PROFILE);self.device=SimulationDevice(self.profile)
        self.controller=Controller(self.profile,self.device,False)

    def request(self,seq,op,**payload):return self.controller.execute({'seq':seq,'op':op,'payload':payload})

    def test_connection_never_moves_or_releases(self):
        result=self.request(1,'hello');self.assertTrue(result['simulation'])
        self.assertEqual(self.device.motions,{})
        self.assertEqual(self.device.released,set())

    def test_duplicate_request_does_not_execute(self):
        self.request(1,'move',targets={'1':1510},duration_ms=1000,attended=True)
        original=dict(self.device.motions)
        with self.assertRaises(ValueError):self.request(1,'move',targets={'1':1520},duration_ms=1000,attended=True)
        self.assertEqual(original,self.device.motions)

    def test_validate_entire_group_before_moving(self):
        with self.assertRaises(ValueError):self.request(1,'move',targets={'1':1510,'7':3000},duration_ms=1000,attended=True)
        self.assertEqual(self.device.motions,{})
        with self.assertRaises(ValueError):self.request(2,'move',targets={'1':2400},duration_ms=20,attended=True)
        self.assertEqual(self.device.motions,{})

    def test_live_not_enabled_by_attended_flag_alone(self):
        self.device.simulation=False
        with self.assertRaises(RuntimeError):self.request(1,'release',numbers=[1],attended=True)
        self.assertEqual(self.device.released,set())

    def test_electrical_gate_precedes_hardware_access(self):
        from shadow_play.bus_servo import service
        unconfirmed=Profile(dict(Profile.load(PROFILE).data,electrical_3v3_verified=False))
        with patch('sys.argv',['service','--profile',str(PROFILE),'--manifest','absent.json']), \
                patch.object(service.Profile,'load',return_value=unconfirmed), \
                patch.object(service,'Mmio') as mmio, patch('sys.stderr'):
            with self.assertRaises(SystemExit):service.main()
        mmio.assert_not_called()


class CommissioningTests(unittest.TestCase):
    def test_id_change_checks_new_address_and_never_retries(self):
        class Bus:
            def __init__(self,ack):self.requests=[];self.replies=iter([b'#000PSERVO.C(310.3)!',ack,b'#006PSERVO.C(310.3)!'])
            def exchange(self,data):self.requests.append(data);return next(self.replies)
        bus=Bus(b'#006POK!')
        self.assertEqual(assign_id(bus,0,6)['motion_commands_sent'],0)
        self.assertEqual(bus.requests,[b'#000PVER!',b'#000PID6!',b'#006PVER!'])
        bus=Bus(b'#000POK!')
        with self.assertRaises(protocol.ProtocolError):assign_id(bus,0,6)
        self.assertEqual(bus.requests,[b'#000PVER!',b'#000PID6!'])

    def test_candidate_identity_hash_and_all_timing_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'candidate.bin';image.write_bytes(b'offline fixture')
            manifest={'identity':'BS10','register_base':0xA0060000,'checks':'passed','sha256':digest(image),
                      'pins':{'person':'E14','tiger':'E15'},'clock_hz':100000000,'baudrate':115200,
                      'legacy_pwm_connected':False,'wns_ns':.8,'whs_ns':.01,'wpws_ns':.1}
            verify(image,manifest)
            for key,value in [('sha256','bad'),('pins',{'person':'E15','tiger':'E14'}),('wns_ns',float('inf')),
                              ('whs_ns',-.01),('wpws_ns',float('nan')),('legacy_pwm_connected',True)]:
                with self.subTest(key=key),self.assertRaises(ValueError):verify(image,dict(manifest,**{key:value}))

    def test_transport_wrong_sequence_does_not_resend(self):
        from shadow_play.bus_servo.transport import RemoteDevice
        class Port:
            def __init__(self):self.writes=[]
            def write(self,data):self.writes.append(data)
        d=RemoteDevice.__new__(RemoteDevice);d.sequence=0;d.port=Port();d.failed=False
        d._receive=lambda deadline:{'seq':2,'ok':True,'result':{}}
        with self.assertRaises(RuntimeError):d.request('move',{'targets':{'1':1510}})
        with self.assertRaises(RuntimeError):d.request('stop')
        self.assertEqual(len(d.port.writes),1)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile.load(PROFILE);self.tmp=tempfile.TemporaryDirectory()
        self.device=SimulationDevice(self.profile)
        self.session=TeachingSession(self.profile,self.device,self.tmp.name)
    def tearDown(self):self.session.close();self.tmp.cleanup()

    def test_hand_record_actual_feedback_and_reload(self):
        now=[10.0];s=self.session;s.clock=lambda:now[0]
        with patch('shadow_play.bus_servo.device.time.monotonic',side_effect=lambda:now[0]):
            s.start_recording([1,7],20)
            self.assertEqual(self.device.released,{1,7})
            s.tick([1,7]);now[0]+=.1
            self.device.drag({'1':1510,'7':1490});s.tick([1,7])
            p=s.finish_recording();r=json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(r['samples'][-1]['positions'],{'1':1510,'7':1490})
        validate_recording(r,self.profile)
        self.assertTrue(p.with_suffix('.jsonl').exists())

    def test_stop_preserves_incomplete_take(self):
        s=self.session;s.start_recording([1]);s.tick([1]);s.stop()
        self.assertFalse(s.record['complete']);self.assertTrue(s.last_path.exists())
        with self.assertRaises(ValueError):s.start_playback(s.record,[1])

    def test_storage_failure_cannot_skip_stop(self):
        s=self.session;s.start_recording([1]);s.tick([1])
        with patch('shadow_play.bus_servo.session.save_recording',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):s.stop()
        self.assertEqual(self.device.released,set(range(1,11)))
        self.assertIsNone(s.journal)
        self.assertFalse(s.recording)

    def test_control_axes_independent_of_recording_axes(self):
        s=self.session;s.start_recording([1,7],20,teaching=False);s.tick([1,7])
        s.set_angles([2],{'2':136},2000)
        time.sleep(.055);s.tick([2]);s.finish_recording()
        self.assertEqual(s.record['selected'],[1,7])
        self.assertEqual(set(s.record['samples'][-1]['positions']),{'1','7'})
        self.assertIn(2,self.device.motions)
        self.assertEqual(self.device.released,set())

    def test_no_jump_to_first_frame(self):
        r=recording(self.profile);self.device.positions[1]=1600
        with self.assertRaises(ValueError):self.session.start_playback(r,[1])
        self.assertEqual(self.device.motions,{})

    def test_late_playback_never_bursts(self):
        t=[0.0];s=self.session;s.clock=lambda:t[0]
        s.start_playback(recording(self.profile),[1],.5)
        t[0]=.3
        with self.assertRaises(TimeoutError):s.tick([1])
        self.assertEqual(self.device.motions,{})

    def test_complete_playback_and_unselected_axis_unchanged(self):
        r=recording(self.profile)
        self.session.start_playback(r,[1],.5)
        deadline=time.monotonic()+2
        while self.session.playing and time.monotonic()<deadline:
            self.session.tick([1]);time.sleep(.005)
        self.assertFalse(self.session.playing)
        self.assertEqual(self.device.positions[7],1500)
        self.assertLessEqual(abs(self.device.positions[1]-1500),1)


if __name__=='__main__':unittest.main()
