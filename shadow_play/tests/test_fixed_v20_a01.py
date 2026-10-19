import copy
from pathlib import Path
import sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'integrations/calibration'),str(ROOT/'tests')]
from fixed_v20_a01 import (A01Device,BOOT,IMAGE,SCHEMA,PRIOR,PRIOR_SHA,frames,
    validate_plan,validate_source,validate_prior,MIDPOINT,digest,run)
from servo_pwm_device import PINS
from test_servo_commissioning import FakeRegisters
from test_v20_first_direction import Clock


def plan():
    return dict(schema=SCHEMA,session_id='a'*32,new_request_id='b'*32,boot_id=BOOT,
        channel='tiger4',expected_sequence=910,expected_pulse_us=MIDPOINT[:],
        route_sha256=digest(frames()),prior_log_path=PRIOR,prior_log_sha256=PRIOR_SHA,
        camera_required=True,onsite_observer=True,new_hardware_request=True,mechanism_visible=True)


class Tests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.path=Path(temp.name)
        self.locks=[self.path/'global',self.path/'local']
        for p in self.locks:p.write_text('locked')
        self.reg=FakeRegisters();self.reg.values[0x20]=910;self.clock=Clock();self.p=plan()

    def device(self,**kwargs):
        options=dict(boot_id=BOOT,marker=dict(boot_id=BOOT,sha256=IMAGE,pins=list(PINS),
            design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS'),used_path=self.path/'used',
            motion_inhibit_paths=self.locks,cancel_path=self.path/'cancel',clock=self.clock)
        options.update(kwargs)
        return A01Device(self.reg,self.p,self.clock,**options)

    def test_only_sourced_bounded_tiger_frames_and_complete_shutdown(self):
        validate_source((ROOT/'config/fixed_v20_a01_candidate_20261019.json').read_bytes())
        q=frames();self.assertEqual(len(q),631);self.assertEqual(q[0],MIDPOINT);self.assertEqual(q[-1],MIDPOINT)
        self.assertTrue(all(p[:6]==[1500]*6 and all(abs(x-1500)<=40 for x in p[6:]) for p in q))
        self.assertLessEqual(max(abs(x-y) for a,b in zip(q,q[1:]) for x,y in zip(a,b)),1)
        d=self.device();self.assertEqual(self.reg.writes,[]);rows=[]
        run(d,rows.append,sleep=self.clock.sleep)
        self.assertEqual(len(rows),632);self.assertEqual(rows[-1]['state']['sequence'],1542)
        self.assertEqual({r['state']['enabled_mask'] for r in rows[:-1]},{1023})
        self.assertFalse(rows[-1]['state']['armed']);self.assertEqual(rows[-1]['state']['pulse_us'],MIDPOINT)
        self.assertEqual([p.read_text() for p in self.locks],['locked','locked'])

    def test_current_source_state_and_route_required(self):
        for key,value in [('expected_sequence',683),('channel',8),('prior_log_sha256','d'*64),
                          ('camera_required',False),('route_sha256','e'*64)]:
            p=copy.deepcopy(self.p);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        with self.assertRaises(ValueError):validate_prior(b'old record')
        with self.assertRaises(ValueError):validate_source(b'changed data')
        self.reg.values[0x20]=911
        with self.assertRaises(RuntimeError):self.device()
        self.assertEqual(self.reg.writes,[])

    def test_no_arbitrary_frame_mask_or_rearm(self):
        d=self.device();d.begin()
        with self.assertRaises(FileExistsError):self.device().begin()
        changed=d.frames[0][:];changed[0]=1510
        with self.assertRaises(ValueError):d.commit(changed,1023,allow_arm=True)
        with self.assertRaises(ValueError):d.commit(d.frames[0],960,allow_arm=True)
        self.assertEqual(self.reg.writes,[])
        d.commit(d.frames[0],1023,allow_arm=True);d.off();self.clock.sleep(.04)
        before=len(self.reg.writes)
        with self.assertRaises(RuntimeError):d.commit(d.frames[1],1023)
        self.assertEqual(len(self.reg.writes),before)

    def test_cancel_stops_in_place_without_fallback_route(self):
        d=self.device();rows=[]
        def emit(row):
            rows.append(row)
            if row.get('index')==200:(self.path/'cancel').write_text('stop')
        with self.assertRaises(RuntimeError):run(d,emit,sleep=self.clock.sleep)
        self.assertFalse(d.status()['armed']);self.assertNotEqual(d.status()['pulse_us'],MIDPOINT)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)


if __name__=='__main__':unittest.main()
