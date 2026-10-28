"""Ten separate signal ports, layout isolation, and bus-to-bus loading guards."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import BusDevice, SimulationDevice
from shadow_play.bus_servo.layouts import get_layout, manifest_layout
from shadow_play.bus_servo.model import Profile, validate_recording
from shadow_play.bus_servo.service import Controller
from shadow_play.bus_servo.session import TeachingSession
from shadow_play.bus_servo.switch_candidate import idle_state, validate_source
from shadow_play.tests.test_bus_servo_tiger import Registers, ServoWire, manifest, TIGER

TEN=Path(__file__).resolve().parents[1]/'config/bus_servo_ten_port.json'


class TenWire(ServoWire):
    def __init__(self, reg, offset, lock):
        super().__init__(reg, offset, lock)
        self.ident=offset//256


class TenPortTests(unittest.TestCase):
    def setUp(self):
        self.p=Profile.load(TEN)
        self.reg=Registers(self.p.layout)
        self.wires=patch('shadow_play.bus_servo.device.WireBus',TenWire);self.wires.start()
        self.d=BusDevice(self.p,self.reg)
    def tearDown(self):self.d.close();self.wires.stop()

    def test_all_ten_ids_read_from_corresponding_ports(self):
        self.assertEqual(set(self.d.connect()),set(range(1,11)))
        for n in range(1,11):
            packets=self.d.buses[f'servo{n}'].requests
            self.assertEqual(len(packets),4)
            self.assertEqual(packets[0],f'#{n:03d}PVER!'.encode())
            self.assertEqual(packets[-1],f'#{n:03d}PRAD!'.encode())
        self.assertEqual(self.reg.writes,[])

    def test_tiger_subset_now_uses_original_ports_seven_to_ten(self):
        self.d.connect([7,10]);self.d.release([7,10])
        for n in range(1,11):
            packets=self.d.buses[f'servo{n}'].requests
            if n in (7,10):self.assertEqual(packets[-1],f'#{n:03d}PULK!'.encode())
            else:self.assertEqual(packets,[])
        self.assertEqual(self.p.layout.pins['servo7'],'J14')
        self.assertEqual(self.p.layout.pins['servo10'],'E15')
        self.assertEqual(self.reg.writes,[])

    def test_person_only_does_not_query_tiger(self):
        self.d.connect(list(range(1,7)))
        for n in range(7,11):self.assertEqual(self.d.buses[f'servo{n}'].requests,[])

    def test_readiness_does_not_enable_positioning(self):
        c=Controller(self.p,self.d,allow_release=True)
        hello=c.execute(dict(seq=1,op='hello',payload={}))
        self.assertTrue(hello['release_allowed']);self.assertFalse(hello['motion_allowed'])
        self.assertEqual(hello['positions'],{})
        with self.assertRaises(RuntimeError):c.execute(dict(seq=2,op='move',payload={'targets':{'1':1510},'duration_ms':2000,'attended':True}))
        self.assertFalse(any(b.requests for b in self.d.buses.values()))

    def test_layout_and_profile_cannot_mix_with_tiger_or_dual(self):
        for layout in ('dual','tiger-four-port'):
            with self.assertRaises(ValueError):BusDevice(self.p,Registers(get_layout(layout)))
            m=manifest(self.p.layout);m['pins']=get_layout(layout).pins
            with self.assertRaises(ValueError):manifest_layout(m)
        data=copy.deepcopy(self.p.data);data['axes'][6]['bus']='servo1'
        with self.assertRaises(ValueError):Profile(data)

    def test_ten_axis_hand_teaching_keeps_recording_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=SimulationDevice(self.p);s=TeachingSession(self.p,d,tmp)
            now=[1.0]
            s.clock=lambda:now[0]
            original=d.read
            def read(numbers):
                return {n:dict(p=r['p'],at=now[0]) for n,r in original(numbers).items()}
            d.read=read
            try:
                numbers=list(range(1,11));s.start_recording(numbers)
                self.assertEqual(d.released,set(numbers))
                s.tick(numbers);now[0]+=.2
                d.drag({str(n):1500+n for n in numbers});s.tick(numbers)
                s.finish_recording()
                validate_recording(s.record,self.p)
                with self.assertRaises(ValueError):validate_recording(s.record,Profile.load(TIGER))
                self.assertEqual(set(s.record['samples'][1]['positions']),set(map(str,numbers)))
            finally:s.close()


class BusSwitchTests(unittest.TestCase):
    def state(self,layout):
        return {0:layout.word,4:1,8:0,16:0,0x18:100000000,0x1c:115200,0x24:len(layout.buses),**{v:0 for v in layout.offsets.values()}}

    def test_both_bus_layouts_validate_with_read_only_offsets(self):
        for name in ('dual','tiger-four-port','ten-port'):
            l=get_layout(name);values=self.state(l);reads=[]
            def read(off):reads.append(off);return values[off]
            idle_state(read,l)
            self.assertFalse(any(off%256 in (4,8,12) for off in reads if off>=256))

    def test_tenth_fifo_lease_fault_and_identity_each_prevent_switch(self):
        l=get_layout('ten-port')
        for off,value in ((0,0x42543034),(8,1),(16,1),(0x24,4),(0xa00,0x100),(0xa00,1),(0xa00,0x1000000)):
            values=self.state(l);values[off]=value
            with self.subTest(off=off,value=value),self.assertRaises(RuntimeError):idle_state(values.__getitem__,l)

    def test_marker_must_match_boot_source_hash_and_physical_layout(self):
        source=manifest(get_layout('tiger-four-port'));source['sha256']='a'*64
        marker=dict(source,boot_id='boot-one')
        self.assertEqual(validate_source(marker,source,'boot-one','a'*64).name,'tiger-four-port')
        for patch_values in ({'boot_id':'boot-two'},{'sha256':'b'*64},{'pins':get_layout('ten-port').pins}):
            with self.assertRaises((RuntimeError,ValueError)):
                validate_source(dict(marker,**patch_values),source,'boot-one','a'*64)

    def test_offline_switch_never_opens_hardware_and_execute_requires_confirmation(self):
        from shadow_play.bus_servo.switch_candidate import main
        from shadow_play.bus_servo.load_candidate import digest
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);image=folder/'image.bin';image.write_bytes(b'test image')
            target=manifest(get_layout('ten-port'));target['sha256']=digest(image)
            source=manifest(get_layout('tiger-four-port'));source['sha256']='a'*64
            new=folder/'new.json';old=folder/'old.json'
            new.write_text(json.dumps(target));old.write_text(json.dumps(source))
            argv=['switch','--image',str(image),'--manifest',str(new),'--previous-manifest',str(old)]
            with patch('sys.argv',argv),patch('os.open') as opened,patch('builtins.print'):
                main();opened.assert_not_called()
            with patch('sys.argv',argv+['--execute']),patch('os.open') as opened:
                with self.assertRaisesRegex(ValueError,'power-off'):main()
                opened.assert_not_called()


if __name__=='__main__':unittest.main()
