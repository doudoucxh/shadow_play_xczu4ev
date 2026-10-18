import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/calibration'))
sys.path.insert(0,str(ROOT/'tests'))
from test_servo_commissioning import FakeRegisters
from test_v20_first_direction import Clock
from other_axes_check import (OtherAxesDevice,ORDER,BOOT,BOARD,FIRST_LOG,FIRST_SHA,
    SCHEMA,IMAGE,MIDPOINT,FRAME_COUNT,digest,route,run,validate_plan,validate_prior)
from other_axes_check import LARGER_SCHEMA,LARGER_ORDER,LARGER_BOARD,LARGER_LOG,LARGER_SHA,profile
from other_axes_check import OPPOSITE_SCHEMA,OPPOSITE_ORDER,OPPOSITE_BOARD,OPPOSITE_LOG,OPPOSITE_SHA
from other_axes_check import EXTENDED_SCHEMA,EXTENDED_ORDER,EXTENDED_BOARD,EXTENDED_LOG,EXTENDED_SHA


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.locks=[self.path/'global',self.path/'local']
        for p in self.locks:p.write_text('locked')
        self.clock=Clock();self.reg=FakeRegisters()
        self.p=self.plan(9);self.reg.values[0x20]=1280

    def plan(self,channel):
        index=ORDER.index(channel)
        return dict(schema=SCHEMA,session_id='a'*32,new_request_id='b'*32,boot_id=BOOT,
            channel=channel,expected_sequence=1280+index*(FRAME_COUNT+1),expected_pulse_us=MIDPOINT,
            route_sha256=digest(route(channel)),prior_log_path=FIRST_LOG if index==0 else BOARD+'/axis-'+str(ORDER[index-1])+'-'+'c'*32+'.board.jsonl',
            prior_log_sha256=FIRST_SHA if index==0 else 'd'*64,camera_required=True,onsite_observer=True,
            new_hardware_request=True,mechanism_visible=True)

    def device(self,**kw):
        args=dict(boot_id=BOOT,marker=dict(boot_id=BOOT,sha256=IMAGE),used_path=self.path/'used',
                  cancel_path=self.path/'cancel',motion_inhibit_paths=self.locks,clock=self.clock)
        args.update(kw)
        return OtherAxesDevice(self.reg,self.p,self.clock,**args)

    def test_every_allowed_axis_is_small_and_independent(self):
        for channel in ORDER:
            with self.subTest(channel=channel):
                self.p=self.plan(channel);self.reg=FakeRegisters();self.reg.values[0x20]=self.p['expected_sequence'];self.clock=Clock()
                d=self.device(used_path=self.path/('used-'+str(channel)));rows=[]
                with self.assertRaises(RuntimeError):d._check_motion_allowed()
                self.assertEqual(self.reg.writes,[])
                run(d,rows.append,sleep=self.clock.sleep)
                frames=rows[:-1]
                self.assertEqual(len(frames),151)
                self.assertEqual({r['state']['enabled_mask'] for r in frames},{1<<(channel-1)})
                self.assertTrue(all(r['state']['pulse_us'][:channel-1]+r['state']['pulse_us'][channel:]==[1500]*9 for r in frames))
                self.assertEqual(max(abs(r['state']['pulse_us'][channel-1]-1500) for r in frames),24)
                self.assertLessEqual(max(abs(a['state']['pulse_us'][channel-1]-b['state']['pulse_us'][channel-1]) for a,b in zip(frames,frames[1:])),1)
                self.assertEqual(rows[-1]['state']['pulse_us'],MIDPOINT)
                self.assertEqual(rows[-1]['state']['sequence'],self.p['expected_sequence']+152)
                self.assertFalse(rows[-1]['state']['armed'])
                self.assertEqual([p.read_text() for p in self.locks],['locked','locked'])

    def test_8_and_arbitrary_routes_source_or_missing_observation_reject(self):
        with self.assertRaises(ValueError):route(8)
        for key,value in [('schema','old'),('expected_sequence',676),('prior_log_sha256','e'*64),
                          ('mechanism_visible',False),('onsite_observer',False),('camera_required',False),('route_sha256','e'*64)]:
            p=dict(self.p);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        self.assertEqual(self.reg.writes,[])

    def test_stale_image_nonoff_or_changed_commands_never_writes(self):
        with self.assertRaises(ValueError):self.device(boot_id='other')
        with self.assertRaises(ValueError):self.device(marker=dict(boot_id=BOOT,sha256='bad'))
        for address,value in [(0x20,1281),(8,1),(0x10,1),(0x24,1),(0xc,1),(0x80,1501)]:
            self.reg=FakeRegisters();self.reg.values[0x20]=1280;self.reg.values[address]=value
            with self.assertRaises(RuntimeError):self.device()
            self.assertEqual(self.reg.writes,[])

    def test_only_exact_next_frame_mask_and_no_rearm(self):
        d=self.device();d.begin()
        with self.assertRaises(ValueError):d.commit(d.frames[0],1023,allow_arm=True)
        with self.assertRaises(ValueError):d.commit(d.frames[50],d.target_mask,allow_arm=True)
        d.commit(d.frames[0],d.target_mask,allow_arm=True)
        with self.assertRaises(RuntimeError):d.commit(d.frames[1],d.target_mask)
        d.off();self.clock.sleep(.04);before=len(self.reg.writes)
        with self.assertRaises(RuntimeError):d.commit(d.frames[1],d.target_mask)
        self.assertEqual(len(self.reg.writes),before)

    def test_consumed_before_motion_and_unknown_adoption_no_retry(self):
        d=self.device();d.begin()
        with self.assertRaises(FileExistsError):self.device().begin()
        self.assertEqual(self.reg.writes,[])
        self.reg.apply=False;rows=[]
        with self.assertRaises(TimeoutError):
            run(self.device(used_path=self.path/'second'),rows.append,sleep=self.clock.sleep)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertFalse(self.reg.status()['armed']) if hasattr(self.reg,'status') else self.assertEqual(self.reg.values[0x10],0)

    def test_loss_cancel_lock_and_logging_stop_without_return_or_next_axis(self):
        for cause in ['host','cancel','lock','log']:
            with self.subTest(cause=cause):
                self.setUp();d=self.device();rows=[]
                def emit(row):
                    rows.append(row)
                    if row.get('event')=='frame' and row['index']==40:
                        if cause=='cancel':(self.path/'cancel').write_text('stop')
                        elif cause=='lock':self.locks[0].write_text('changed')
                        elif cause=='log':raise OSError('log failed')
                        else:
                            def lost():raise RuntimeError('lost')
                            self.clock.check=lost
                with self.assertRaises((RuntimeError,OSError)):run(d,emit,sleep=self.clock.sleep)
                self.assertFalse(d.status()['armed'])
                self.assertNotEqual(d.status()['pulse_us'][8],1500)
                self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)

    def test_next_axis_requires_complete_actual_previous_route(self):
        rows=[];run(self.device(),rows.append,sleep=self.clock.sleep)
        p=self.plan(10)
        def encode(rows):return ('\n'.join(json.dumps(x) for x in rows)+'\n').encode()
        raw=encode(rows);p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        validate_plan(p);validate_prior(p,raw)
        with self.assertRaises(ValueError):validate_prior(p,raw+b' ')
        for mutate in ['incomplete','wrong_mask','wrong_sequence','wrong_final']:
            changed=json.loads(json.dumps(rows))
            if mutate=='incomplete':del changed[40]
            elif mutate=='wrong_mask':changed[40]['state']['enabled_mask']=128
            elif mutate=='wrong_sequence':changed[40]['state']['sequence']+=1
            else:changed[-1]['route_complete']=False
            raw=encode(changed);p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaises(ValueError):validate_prior(p,raw)

    def larger_plan(self,channel):
        cfg=profile(True);index=LARGER_ORDER.index(channel);p=self.plan(channel)
        p.update(schema=LARGER_SCHEMA,larger_amplitude_acknowledged=True,
                 expected_sequence=2648+index*227,route_sha256=digest(route(channel,True)),
                 prior_log_path=LARGER_LOG if index==0 else LARGER_BOARD+'/axis-'+str(LARGER_ORDER[index-1])+'-'+'c'*32+'.board.jsonl',
                 prior_log_sha256=LARGER_SHA if index==0 else 'd'*64)
        return p

    def test_40us_profile_has_exact_limits_and_new_source_on_each_axis(self):
        for channel in LARGER_ORDER:
            self.p=self.larger_plan(channel);self.reg=FakeRegisters();self.clock=Clock()
            self.reg.values[0x20]=self.p['expected_sequence'];rows=[]
            run(self.device(used_path=self.path/('large-'+str(channel))),rows.append,sleep=self.clock.sleep)
            self.assertEqual(len(rows[:-1]),226)
            self.assertEqual(max(abs(r['state']['pulse_us'][channel-1]-1500) for r in rows[:-1]),40)
            self.assertLessEqual(max(abs(a[channel-1]-b[channel-1]) for a,b in zip(route(channel,True),route(channel,True)[1:])),1)
            self.assertEqual(rows[-1]['state']['sequence'],self.p['expected_sequence']+227)
            self.assertFalse(rows[-1]['state']['armed'])

    def test_40us_requires_new_authorization_and_rejects_old_source(self):
        p=self.larger_plan(3);validate_plan(p)
        for key,value in [('larger_amplitude_acknowledged',False),('prior_log_path',FIRST_LOG),
                          ('prior_log_sha256',FIRST_SHA),('expected_sequence',1280),('route_sha256',digest(route(3)))]:
            changed=dict(p);changed[key]=value
            with self.assertRaises(ValueError):validate_plan(changed)
        self.assertEqual(self.reg.writes,[])

    def test_40us_next_source_cannot_be_a_completed_24us_route(self):
        self.p=self.larger_plan(3);self.reg.values[0x20]=2648
        rows=[];run(self.device(),rows.append,sleep=self.clock.sleep)
        p=self.larger_plan(6);raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode()
        p['prior_log_sha256']=hashlib.sha256(raw).hexdigest();validate_prior(p,raw)
        rows[40]['state']['pulse_us'][2]=1524
        raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):validate_prior(p,raw)

    def test_24us_route_digests_remain_identical_to_executed_records(self):
        record=json.loads((ROOT/'config/other_axes_check_result_20261019.json').read_text(encoding='utf-8'))
        self.assertTrue(all(digest(route(c['channel']))==c['plan']['route_sha256'] for c in record['checks']))

    def opposite_plan(self,channel):
        index=OPPOSITE_ORDER.index(channel);p=self.larger_plan(channel)
        p.update(schema=OPPOSITE_SCHEMA,continued_diagnostics_requested=True,
                 expected_sequence=4691+index*227,route_sha256=digest(route(channel,True,True)),
                 prior_log_path=OPPOSITE_LOG if index==0 else OPPOSITE_BOARD+'/axis-'+str(OPPOSITE_ORDER[index-1])+'-'+'c'*32+'.board.jsonl',
                 prior_log_sha256=OPPOSITE_SHA if index==0 else 'd'*64)
        return p

    def test_opposite_single_axis_routes_and_exact_new_completion(self):
        for channel in OPPOSITE_ORDER:
            self.p=self.opposite_plan(channel);self.reg=FakeRegisters();self.clock=Clock()
            self.reg.values[0x20]=self.p['expected_sequence'];rows=[]
            run(self.device(used_path=self.path/('opposite-'+str(channel))),rows.append,sleep=self.clock.sleep)
            self.assertEqual(len(rows[:-1]),226)
            self.assertEqual(rows[100]['state']['pulse_us'][channel-1],1540 if channel==10 else 1460)
            self.assertEqual({r['state']['enabled_mask'] for r in rows[:-1]},{1<<(channel-1)})
            self.assertTrue(all(r['state']['pulse_us'][:channel-1]+r['state']['pulse_us'][channel:]==[1500]*9 for r in rows[:-1]))
            self.assertEqual(rows[-1]['state']['sequence'],self.p['expected_sequence']+227)
            self.assertFalse(rows[-1]['state']['armed'])
            self.assertEqual(rows[-1]['state']['pulse_us'],MIDPOINT)

    def test_opposite_cannot_reuse_previous_40us_authorization_or_source(self):
        p=self.opposite_plan(1);validate_plan(p)
        for key,value in [('continued_diagnostics_requested',False),('prior_log_path',LARGER_LOG),
                          ('prior_log_sha256',LARGER_SHA),('expected_sequence',2648),('route_sha256',digest(route(1,True)))]:
            changed=dict(p);changed[key]=value
            with self.assertRaises(ValueError):validate_plan(changed)
        self.assertEqual(self.reg.writes,[])

    def test_opposite_prior_requires_complete_opposite_route(self):
        self.p=self.opposite_plan(1);self.reg.values[0x20]=4691
        rows=[];run(self.device(),rows.append,sleep=self.clock.sleep)
        p=self.opposite_plan(4)
        raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        validate_prior(p,raw)
        rows[75]['state']['pulse_us'][0]=1540
        raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):validate_prior(p,raw)

    def test_previous_40us_digests_stay_identical(self):
        record=json.loads((ROOT/'config/other_axes_40us_result_20261019.json').read_text(encoding='utf-8'))
        self.assertTrue(all(digest(route(c['channel'],True))==c['plan']['route_sha256'] for c in record['checks']))

    def extended_plan(self,channel):
        index=EXTENDED_ORDER.index(channel);p=self.larger_plan(channel)
        p.update(schema=EXTENDED_SCHEMA,extended_amplitude_acknowledged=True,
                 expected_sequence=6734+index*277,route_sha256=digest(route(channel,extended=True)),
                 prior_log_path=EXTENDED_LOG if index==0 else EXTENDED_BOARD+'/axis-'+str(EXTENDED_ORDER[index-1])+'-'+'c'*32+'.board.jsonl',
                 prior_log_sha256=EXTENDED_SHA if index==0 else 'd'*64)
        return p

    def test_extended_five_routes_bounded_independent_and_slow(self):
        for channel in EXTENDED_ORDER:
            self.p=self.extended_plan(channel);self.reg=FakeRegisters();self.clock=Clock()
            self.reg.values[0x20]=self.p['expected_sequence'];rows=[]
            d=self.device(used_path=self.path/('extended-'+str(channel)))
            run(d,rows.append,sleep=self.clock.sleep)
            frames=rows[:-1];self.assertEqual(len(frames),276)
            self.assertEqual(frames[100]['state']['pulse_us'][channel-1],1556 if channel==10 else 1444)
            self.assertEqual({r['state']['enabled_mask'] for r in frames},{1<<(channel-1)})
            self.assertTrue(all(r['state']['pulse_us'][:channel-1]+r['state']['pulse_us'][channel:]==[1500]*9 for r in frames))
            self.assertEqual(max(abs(a['state']['pulse_us'][channel-1]-b['state']['pulse_us'][channel-1]) for a,b in zip(frames,frames[1:])),1)
            self.assertEqual(d.profile['deadline_s'],14)
            self.assertEqual(rows[-1]['state']['sequence'],self.p['expected_sequence']+277)
            self.assertFalse(rows[-1]['state']['armed']);self.assertEqual(rows[-1]['state']['pulse_us'],MIDPOINT)

    def test_extended_rejects_other_channels_old_request_and_changed_route(self):
        p=self.extended_plan(1);validate_plan(p)
        for ch in (2,3,6,7,8):
            with self.assertRaises(ValueError):route(ch,extended=True)
        for key,value in [('extended_amplitude_acknowledged',False),('expected_sequence',4691),
                          ('prior_log_path',OPPOSITE_LOG),('prior_log_sha256',OPPOSITE_SHA),
                          ('route_sha256',digest(route(1,True,True)))]:
            bad=dict(p);bad[key]=value
            with self.assertRaises(ValueError):validate_plan(bad)
        self.assertEqual(self.reg.writes,[])

    def test_extended_prior_requires_all_276_frames(self):
        self.p=self.extended_plan(1);self.reg.values[0x20]=6734
        rows=[];run(self.device(),rows.append,sleep=self.clock.sleep)
        p=self.extended_plan(4)
        raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        validate_prior(p,raw)
        del rows[100]
        raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();p['prior_log_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):validate_prior(p,raw)

    def test_previous_opposite_route_digests_stay_identical(self):
        record=json.loads((ROOT/'config/other_axes_direction_result_20261019.json').read_text(encoding='utf-8'))
        self.assertTrue(all(digest(route(c['channel'],True,True))==c['plan']['route_sha256'] for c in record['checks']))


if __name__=='__main__':unittest.main()
