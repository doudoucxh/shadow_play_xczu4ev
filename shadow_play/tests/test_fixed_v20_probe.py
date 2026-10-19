import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'integrations/calibration'),str(ROOT/'tests'),str(ROOT/'tools')]
from fixed_v20_probe import (FixedV20ProbeDevice,BOOT,IMAGE,BOARD,REFERENCE,REFERENCE_SHA,
    SCHEMA,CLOSE_SCHEMA,route,validate_plan,validate_prior,run,MIDPOINT,digest)
from servo_pwm_device import PINS
from test_servo_commissioning import FakeRegisters
from test_v20_first_direction import Clock
from run_fixed_v20_probe import DualCamera


def plan(channel=7):
    return dict(schema=SCHEMA,session_id='a'*32,new_request_id='b'*32,boot_id=BOOT,channel=channel,
        expected_sequence={7:0,8:227}[channel],expected_pulse_us=MIDPOINT[:],route_sha256=digest(route(channel)),
        prior_log_path=REFERENCE if channel==7 else BOARD+'/axis-7-'+'c'*32+'.board.jsonl',
        prior_log_sha256=REFERENCE_SHA if channel==7 else 'd'*64,camera_required=True,
        onsite_observer=True,new_hardware_request=True,mechanism_visible=True)


class Tests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.path=Path(temp.name)
        self.locks=[self.path/'global',self.path/'local']
        for p in self.locks:p.write_text('locked')
        self.reg=FakeRegisters();self.clock=Clock();self.p=plan()
        self.marker=dict(boot_id=BOOT,sha256=IMAGE,pins=list(PINS),design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS')

    def device(self,**kwargs):
        options=dict(boot_id=BOOT,marker=self.marker,used_path=self.path/'used',
            motion_inhibit_paths=self.locks,cancel_path=self.path/'cancel',clock=self.clock)
        options.update(kwargs)
        return FixedV20ProbeDevice(self.reg,self.p,self.clock,**options)

    def test_exact_finite_axis_masks_and_shutdown(self):
        for channel in (7,8):
            self.p=plan(channel);self.reg=FakeRegisters();self.clock=Clock()
            self.reg.values[0x20]=self.p['expected_sequence']
            d=self.device(used_path=self.path/str(channel));self.assertEqual(self.reg.writes,[])
            with self.assertRaises(RuntimeError):d._check_motion_allowed()
            rows=[];run(d,rows.append,sleep=self.clock.sleep)
            self.assertEqual(len(rows),227)
            self.assertEqual({r['state']['enabled_mask'] for r in rows[:-1]},{1<<(channel-1)})
            self.assertTrue(all(r['state']['pulse_us'][:channel-1]+r['state']['pulse_us'][channel:]==[1500]*9 for r in rows[:-1]))
            self.assertEqual(max(q[channel-1] for q in route(channel)),1540)
            self.assertLessEqual(max(abs(a[channel-1]-b[channel-1]) for a,b in zip(route(channel),route(channel)[1:])),1)
            self.assertFalse(rows[-1]['state']['armed']);self.assertEqual(rows[-1]['state']['pulse_us'],MIDPOINT)
            self.assertEqual(rows[-1]['state']['sequence'],self.p['expected_sequence']+227)
            self.assertEqual([p.read_text() for p in self.locks],['locked','locked'])

    def test_old_image_or_wrong_pins_boot_and_state_write_nothing(self):
        for key,value in [('sha256','824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'),
                          ('pins',list(PINS[:3])+['H13']+list(PINS[4:])),('boot_id','other'),('design_checks','unchecked')]:
            marker=dict(self.marker);marker[key]=value
            with self.assertRaises(ValueError):self.device(marker=marker)
        for address,value in [(8,64),(0x10,1),(0xc,1),(0x20,1),(0x24,1),(0x80,1499)]:
            self.reg=FakeRegisters();self.reg.values[address]=value
            with self.assertRaises(RuntimeError):self.device()
            self.assertEqual(self.reg.writes,[])

    def test_real_initial_reference_and_strict_new_plan(self):
        raw=(ROOT/'config/fixed_v20_start_reference_20261019.json').read_bytes()
        validate_prior(self.p,raw)
        with self.assertRaises(ValueError):validate_prior(self.p,raw+b' ')
        for key,value in [('expected_sequence',12665),('camera_required',False),('route_sha256','e'*64),('channel',9),('prior_log_sha256','e'*64)]:
            p=copy.deepcopy(self.p);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        with self.assertRaises(ValueError):route(True)

    def test_axis8_requires_actual_complete_new_axis7_chain(self):
        rows=[];run(self.device(),rows.append,sleep=self.clock.sleep)
        p=plan(8)
        def encode(rows):return ('\n'.join(json.dumps(r) for r in rows)+'\n').encode()
        raw=encode(rows);p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        validate_plan(p);validate_prior(p,raw)
        for key in ('missing','wrong_mask','wrong_end'):
            changed=copy.deepcopy(rows)
            if key=='missing':del changed[30]
            elif key=='wrong_mask':changed[30]['state']['enabled_mask']=128
            else:changed[-1]['state']['sequence']=226
            raw=encode(changed);p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaises(ValueError):validate_prior(p,raw)

    def test_cancel_is_in_place_and_once_marker_precedes_motion(self):
        d=self.device();d.begin();self.assertEqual(self.reg.writes,[])
        with self.assertRaises(FileExistsError):self.device().begin()
        d=self.device(used_path=self.path/'second');rows=[]
        def emit(row):
            rows.append(row)
            if row.get('index')==40:(self.path/'cancel').write_text('stop')
        with self.assertRaises(RuntimeError):run(d,emit,sleep=self.clock.sleep)
        self.assertFalse(d.status()['armed']);self.assertNotEqual(d.status()['pulse_us'][6],1500)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)

    def test_dual_camera_rejects_session_change_and_either_failed_view(self):
        camera=DualCamera.__new__(DualCamera);camera.root=self.path;camera.session='same'
        camera.front=Mock();camera.rear=Mock()
        pointer=self.path/'current.json';pointer.write_text(json.dumps(dict(directory='changed')))
        with self.assertRaises(RuntimeError):camera.sample()
        camera.front.sample.assert_not_called();camera.rear.sample.assert_not_called()
        pointer.write_text(json.dumps(dict(directory='same')))
        camera.front.sample.side_effect=RuntimeError('stale front')
        with self.assertRaises(RuntimeError):camera.sample()
        camera.front.sample.side_effect=None;camera.rear.sample.side_effect=RuntimeError('stale rear')
        with self.assertRaises(RuntimeError):camera.sample()

    def test_new_close_view_has_new_exact_predecessor_and_no_old_marker_reuse(self):
        self.p=plan(8);self.p.update(schema=CLOSE_SCHEMA,expected_sequence=454,
            prior_log_path=BOARD+'/axis-8-adf3ab8f37c5411ab624d3816346211c.board.jsonl',
            prior_log_sha256='0e077d447a09c1e7cf27dd932560f34e562589983107b64884035a4112cfe15b')
        validate_plan(self.p)
        for key,value in [('expected_sequence',227),('channel',7),('prior_log_sha256','e'*64)]:
            p=copy.deepcopy(self.p);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        self.reg.values[0x20]=454;rows=[]
        run(self.device(),rows.append,sleep=self.clock.sleep)
        self.assertEqual(rows[-1]['state']['sequence'],681)
        self.assertEqual({r['state']['enabled_mask'] for r in rows[:-1]},{128})
        self.assertFalse(rows[-1]['state']['armed'])


if __name__=='__main__':unittest.main()
