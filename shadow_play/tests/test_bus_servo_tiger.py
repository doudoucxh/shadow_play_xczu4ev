"""Tiger four-port routing and teaching integration; no physical serial I/O."""
import copy
import hashlib
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import BusDevice, Mmio, SimulationDevice
from shadow_play.bus_servo.editing import EditProject, compile_project
from shadow_play.bus_servo.layouts import get_layout, manifest_layout
from shadow_play.bus_servo.load_candidate import verify, digest
from shadow_play.bus_servo.model import Profile, validate_recording
from shadow_play.bus_servo.service import Controller
from shadow_play.bus_servo.session import TeachingSession

ROOT = Path(__file__).resolve().parents[1]
TIGER = ROOT/'config/bus_servo_tiger_four.json'


def manifest(layout):
    return dict(identity=layout.identity, layout=layout.name, pins=layout.pins,
                register_base=0xA0060000, clock_hz=100000000, baudrate=115200,
                checks='passed', legacy_pwm_connected=False, wns_ns=.8, whs_ns=.01, wpws_ns=.1)


class Registers:
    def __init__(self, layout):
        self.layout = layout
        self.lease = 0
        self.writes = []
    def read(self, address):
        return self.lease if address == 0x10 else 0
    def write(self, address, value):
        self.writes.append((address, value))
        if address == 0x10: self.lease = 1
        if address == 0x0c: self.lease = 0
    def close(self): pass


class ServoWire:
    def __init__(self, registers, offset, lock):
        self.offset = offset
        self.ident = 6 + offset // 256
        self.requests = []
    def exchange(self, data, expects_reply=True, reply_length=None):
        self.requests.append(data)
        n = self.ident
        if data[:2] == b'\xff\xff':
            assert data[2] == n, 'Health request crossed to the wrong connector'
            frame = bytes([n, 3, 0, 0])
            return b'\xff\xff' + frame + bytes([(~sum(frame)) & 255])
        assert data.startswith(f'#{n:03d}P'.encode()), 'Wrong ID on physical connector'
        if not expects_reply: return b''
        prefix = f'#{n:03d}P'
        if data.endswith(b'VER!'): return (prefix+'SERVO.C(310.3)!').encode()
        if data.endswith(b'MOD!'): return (prefix+'MOD1!').encode()
        if data.endswith(b'RAD!'): return (prefix+'1500!').encode()
        if data.endswith(b'ULK!'): return (prefix+'OK!').encode()
        raise AssertionError(data)


class TigerProfileTests(unittest.TestCase):
    def setUp(self): self.profile = Profile.load(TIGER)

    def test_axes_are_tiger_numbers_and_fixed_physical_ports(self):
        p = self.profile
        self.assertEqual(p.layout.numbers, [7,8,9,10])
        self.assertEqual(p.layout.pins, dict(tiger7='D14',tiger8='D15',tiger9='F13',tiger10='G13'))
        self.assertEqual(p.layout.offsets, dict(tiger7=0x100,tiger8=0x200,tiger9=0x300,tiger10=0x400))
        self.assertEqual([a.ident for a in p.select([7,8,9,10])], [7,8,9,10])
        self.assertFalse(any(p.data[k] for k in ('hardware_verified','mechanical_limits_verified')))
        with self.assertRaises(ValueError): p.select([1])

    def test_wrong_axis_bus_pin_or_layout_rejected(self):
        for key in ('missing','extra','bus','pin','layout'):
            d = copy.deepcopy(self.profile.data)
            if key == 'missing': d['axes'].pop()
            elif key == 'extra': d['axes'].append(dict(d['axes'][0],number=1,bus='person'))
            elif key == 'bus': d['axes'][0]['bus']='tiger'
            elif key == 'pin': d['pins']['tiger7']='E14'
            else: d['layout']='unknown'
            with self.subTest(key=key), self.assertRaises(ValueError): Profile(d)

    def test_old_dual_fingerprint_and_example_preserved(self):
        p = Profile.load(ROOT/'config/bus_servo.json')
        fields={k:p.data[k] for k in ('axes','pins','baudrate')}
        old=hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(p.fingerprint,old)
        self.assertEqual(p.layout.identity,'BS10')
        data=json.loads((ROOT/'examples/bus_servo_editing/simulation.project.json').read_text(encoding='utf-8'))
        project=EditProject(p,data=data)
        record=compile_project(project.data,p)
        validate_recording(record,p)
        with self.assertRaises(ValueError): validate_recording(record,self.profile)

    def test_image_identity_and_pin_map_cannot_be_mixed(self):
        m=manifest(self.profile.layout)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'candidate.bin'; path.write_bytes(b'offline')
            m['sha256']=digest(path)
            self.assertEqual(verify(path,m).identity,'BT04')
            for change in (dict(identity='BS10'),dict(layout='dual'),dict(pins={'person':'E14','tiger':'E15'})):
                with self.assertRaises(ValueError): verify(path,dict(m,**change))

    def test_mismatched_layout_is_rejected_before_mmio_open(self):
        m=manifest(self.profile.layout)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'release.json'; path.write_text(json.dumps(m))
            marker=Path(temp)/'loaded.json'; marker.write_text(json.dumps(m))
            with patch.dict('sys.modules',{'fcntl':types.SimpleNamespace()}), patch('os.open') as opened:
                with self.assertRaisesRegex(RuntimeError,'different FPGA'):
                    Mmio(path,str(marker),expected_layout='dual')
                opened.assert_not_called()

    def test_ps_console_selects_independent_tiger_bundle(self):
        from shadow_play.bus_servo.transport import RemoteDevice
        class Port:
            writes=[]
            def __init__(self,**kwargs):
                self.responses=iter([b'shadowdpupetalinux:~# ',
                                     b'@@BUS10@@{"ready":true,"service":"bus-teach-v1"}\n'])
                self.is_open=False
            def open(self):self.is_open=True
            def close(self):self.is_open=False
            def read(self,count):return next(self.responses,b'')
            def read_all(self):return b''
            def write(self,data):self.writes.append(data)
        with patch.dict('sys.modules',{'serial':types.SimpleNamespace(Serial=Port)}):
            d=RemoteDevice(self.profile,'mock-only')
            self.assertIn(b'cd /run/media/mmcblk0p2/piying/bus-servo-tiger-four-v1 && sh start_console.sh; stty echo\r',d.port.writes)
            self.assertFalse(any(b'P1500' in data for data in d.port.writes))
            d.failed=True;d.close()


class TigerRoutingTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile.load(TIGER)
        self.reg=Registers(self.profile.layout)
        self.mock=patch('shadow_play.bus_servo.device.WireBus',ServoWire); self.mock.start()
        self.device=BusDevice(self.profile,self.reg)
    def tearDown(self):
        self.device.close(); self.mock.stop()

    def test_connect_reads_only_four_correct_ports_without_motion(self):
        self.assertEqual(set(self.device.connect()),{7,8,9,10})
        self.assertEqual(self.reg.writes,[])
        for n in range(7,11):
            requests=self.device.buses[f'tiger{n}'].requests
            self.assertEqual(len(requests),4)
            self.assertEqual(requests[0],f'#{n:03d}PVER!'.encode())
            self.assertEqual(requests[-1],f'#{n:03d}PRAD!'.encode())

    def test_selected_axis_moves_only_its_connector(self):
        self.device.move({'9':1510},1000)
        self.assertEqual(self.device.buses['tiger9'].requests,[b'#009P1510T1000!'])
        self.assertEqual(sum(len(b.requests) for b in self.device.buses.values()),1)
        result=self.device.stop()
        self.assertEqual(set(result['reply_hex']),{'tiger7','tiger8','tiger9','tiger10'})
        self.assertFalse(result['physical_stop_verified'])

    def test_controller_rejects_person_axis_before_any_packet(self):
        c=Controller(self.profile,self.device,True)
        self.profile.data.update(hardware_verified=True,electrical_3v3_verified=True,mechanical_limits_verified=True)
        with self.assertRaises(ValueError):
            c.execute({'seq':1,'op':'move','payload':{'targets':{'1':1500},'duration_ms':1000,'attended':True}})
        self.assertEqual(self.reg.writes,[])
        self.assertFalse(any(b.requests for b in self.device.buses.values()))

    def test_electrical_gate_still_precedes_hardware_access(self):
        from shadow_play.bus_servo import service
        pending = Profile(copy.deepcopy(self.profile.data))
        pending.data['electrical_3v3_verified'] = False
        with patch('sys.argv',['service','--profile',str(TIGER),'--manifest','absent.json']), \
                patch.object(service.Profile,'load',return_value=pending), \
                patch.object(service,'Mmio') as mmio,patch('sys.stderr'):
            with self.assertRaises(SystemExit): service.main()
        mmio.assert_not_called()

    def test_electrical_confirmation_alone_keeps_motion_blocked(self):
        c=Controller(self.profile,self.device,False)
        self.assertTrue(self.profile.data['electrical_3v3_verified'])
        self.assertEqual(self.profile.data['electrical_verification']['basis'],'user_report')
        for seq,op,payload in ((1,'move',{'targets':{'7':1510},'duration_ms':1000,'attended':True}),
                               (2,'release',{'numbers':[7],'attended':True})):
            with self.assertRaises(RuntimeError):
                c.execute({'seq':seq,'op':op,'payload':payload})
        self.assertEqual(self.reg.writes,[])
        self.assertFalse(any(b.requests for b in self.device.buses.values()))


class TigerTeachingTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile.load(TIGER)
        self.tmp=tempfile.TemporaryDirectory()
        self.device=SimulationDevice(self.profile)
        self.session=TeachingSession(self.profile,self.device,self.tmp.name)
    def tearDown(self): self.session.close();self.tmp.cleanup()

    def test_continuous_recording_keeps_logical_7_to_10(self):
        s=self.session;s.start_recording([7,8,9,10],20)
        s.tick([7,8,9,10]);time.sleep(.055)
        self.device.drag({'7':1510,'8':1490,'9':1502,'10':1498})
        s.tick([7,8,9,10]);s.finish_recording()
        validate_recording(s.record,self.profile)
        self.assertEqual(s.record['selected'],[7,8,9,10])
        self.assertEqual(set(s.record['samples'][-1]['positions']),{'7','8','9','10'})

    def test_pose_edit_and_replay_for_tiger_subset(self):
        s=self.session
        self.device.release([7,10])
        project=EditProject(self.profile,[7,10])
        project.add_pose(s.capture_pose([7,10]),hold_s=.02)
        self.device.drag({'7':1505,'10':1495})
        project.add_pose(s.capture_pose([7,10]),transition_s=.1,hold_s=.02)
        record=compile_project(project.data,self.profile);validate_recording(record,self.profile)
        with self.assertRaises(ValueError):validate_recording(record,self.profile,live=True)
        self.device.drag({'7':1500,'10':1500})
        s.start_playback(record,[7,10],1)
        deadline=time.monotonic()+3
        while s.playing and time.monotonic()<deadline:
            s.tick([7,10]);time.sleep(.005)
        self.assertFalse(s.playing)
        self.assertEqual(self.device.positions[8],1500)
        self.assertEqual(self.device.positions[9],1500)
        self.assertLessEqual(abs(self.device.positions[7]-1505),1)

    def test_worker_connect_and_clear_selection_never_poll_person(self):
        from shadow_play.bus_servo.gui import Worker
        class ObservedDevice(SimulationDevice):
            reads=[]
            def read(self,numbers):
                self.reads.append(list(numbers));return super().read(numbers)
        commands=queue.Queue();events=queue.Queue();stop=threading.Event()
        with patch('shadow_play.bus_servo.gui.SimulationDevice',ObservedDevice):
            w=Worker(commands,events,stop);w.start()
            try:
                commands.put(('connect',(self.profile,True,'unused')))
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    kind,value=events.get(timeout=2)
                    self.assertNotEqual(kind,'error',value)
                    if kind=='feedback':break
                else:self.fail('No initial feedback')
                commands.put(('select',[]))
                time.sleep(.03)
            finally:
                commands.put(('shutdown',None));w.join(timeout=2)
            self.assertFalse(w.is_alive())
        self.assertTrue(ObservedDevice.reads)
        self.assertTrue(all(set(ns)<=set([7,8,9,10]) and ns for ns in ObservedDevice.reads))


if __name__=='__main__':unittest.main()
