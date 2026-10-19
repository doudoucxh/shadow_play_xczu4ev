import copy,hashlib,json
from pathlib import Path
import sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'integrations/calibration'),str(ROOT/'tests')]
from fixed_v20_a02_closeup import *
from test_servo_commissioning import FakeRegisters
from test_v20_first_direction import Clock


def plan(ch=1):
    p=dict(schema=SCHEMA,session_id='a'*32,new_request_id='b'*32,boot_id=BOOT,channel=ch,
        expected_sequence=STARTS[ch],expected_pulse_us=MIDPOINT[:],route_sha256=digest(route(ch)),
        prior_log_path=PRIOR,prior_log_sha256=PRIOR_SHA,camera_required=True,onsite_observer=True,
        new_hardware_request=True,mechanism_visible=True)
    if ch!=1:p.update(prior_log_path=BOARD+'/axis-'+str(CHANNELS[CHANNELS.index(ch)-1])+'-'+'c'*32+'.board.jsonl',prior_log_sha256='d'*64)
    return p


class Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.path=Path(t.name)
        self.locks=[self.path/'lock'];self.locks[0].write_text('original lock')
        self.marker=dict(boot_id=BOOT,sha256=IMAGE,pins=list(PINS),design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS')

    def device(self,ch):
        reg=FakeRegisters();reg.values[0x20]=STARTS[ch];clock=Clock()
        d=A02DirectionsDevice(reg,plan(ch),clock,boot_id=BOOT,marker=self.marker,
            used_path=self.path/('used-'+str(ch)),motion_inhibit_paths=self.locks,
            cancel_path=self.path/'cancel',clock=clock)
        return d,reg,clock

    def test_exact_hands_supported_and_complete_stop(self):
        for ch in CHANNELS:
            d,r,c=self.device(ch);self.assertEqual(r.writes,[]);rows=[];run(d,rows.append,sleep=c.sleep)
            self.assertEqual(len(rows),227);self.assertTrue(rows[-1]['route_complete'])
            self.assertEqual(rows[-1]['state']['sequence'],STARTS[ch]+227)
            self.assertFalse(rows[-1]['state']['armed']);self.assertEqual(rows[-1]['state']['pulse_us'],MIDPOINT)
            self.assertEqual({row['state']['enabled_mask'] for row in rows[:-1]},{1023})
            self.assertTrue(all(row['state']['pulse_us'][:ch-1]+row['state']['pulse_us'][ch:]==[1500]*9 for row in rows[:-1]))
            self.assertEqual(max(row['state']['pulse_us'][ch-1] for row in rows[:-1]),1540)
            self.assertLessEqual(max(abs(a[ch-1]-b[ch-1]) for a,b in zip(route(ch),route(ch)[1:])),1)
            self.assertEqual(self.locks[0].read_text(),'original lock')

    def test_state_image_arbitrary_frames_replay_and_cancel(self):
        d,r,c=self.device(1);d.begin()
        with self.assertRaises(FileExistsError):self.device(1)[0].begin()
        with self.assertRaises(ValueError):d.commit(MIDPOINT,1,allow_arm=True)
        changed=MIDPOINT[:];changed[4]=1501
        with self.assertRaises(ValueError):d.commit(changed,1023,allow_arm=True)
        self.assertEqual(r.writes,[])
        d,r,c=self.device(5);rows=[]
        def emit(row):
            rows.append(row)
            if row.get('index')==40:(self.path/'cancel').write_text('stop')
        with self.assertRaises(RuntimeError):run(d,emit,sleep=c.sleep)
        self.assertFalse(d.status()['armed']);self.assertNotEqual(d.status()['pulse_us'],MIDPOINT)
        self.marker['pins'][3]='H13'
        with self.assertRaises(ValueError):self.device(6)

    def test_plan_rejects_old_and_nonhand_requests(self):
        for k,v in [('expected_sequence',681),('channel',3),('route_sha256','f'*64),('camera_required',False),('prior_log_sha256','f'*64)]:
            p=plan();p[k]=v
            with self.assertRaises(ValueError):validate_plan(p)
        with self.assertRaises(ValueError):route(True)

    def test_next_hand_requires_entire_actual_predecessor(self):
        d,r,c=self.device(1);rows=[];run(d,rows.append,sleep=c.sleep);p=plan(5)
        def encode(rows):return ('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
        raw=encode(rows);p['prior_log_sha256']=hashlib.sha256(raw).hexdigest();validate_plan(p);validate_prior(p,raw)
        for mode in ('missing','mask','incomplete','pulse'):
            bad=copy.deepcopy(rows)
            if mode=='missing':del bad[30]
            elif mode=='mask':bad[30]['state']['enabled_mask']=1
            elif mode=='incomplete':bad[-1]['route_complete']=False
            else:bad[30]['state']['pulse_us'][4]=1510
            raw=encode(bad);p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaises(ValueError):validate_prior(p,raw)


if __name__=='__main__':unittest.main()
