import hashlib
import json
import io
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/calibration'))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))
from test_servo_commissioning import FakeRegisters
from test_v20_first_direction import Clock
from v20_first_direction import validate_plan as validate_axis7
from v20_head_lift import HeadLiftDevice, FRAMES, MASK, IMAGE, SCHEMA, SOURCE_SHA, digest, run, validate_plan, validate_prior
from v20_head_lift import PHONE_SCHEMA, PHONE_LOG, PHONE_LOG_SHA
from run_v20_head_lift import PhoneCamera


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.locks = [self.path / 'global', self.path / 'local']
        for p in self.locks: p.write_text('locked')
        self.reg = FakeRegisters(); self.reg.values[0x20] = 676
        self.clock = Clock()
        self.p = dict(schema=SCHEMA, session_id='a' * 32, new_request_id='b' * 32,
            boot_id='8b5372c2-00de-459e-ad96-371ec5ea0ef9', expected_sequence=676,
            expected_pulse_us=[1500] * 10, route_sha256=digest(FRAMES), historical_source_sha256=SOURCE_SHA,
            camera_required=True, onsite_observer=True, new_hardware_request=True,
            prior_log_path='/run/media/mmcblk0p2/piying/v20-first-direction-20261018-r4/run-' + 'c' * 32 + '.board.jsonl',
            prior_log_sha256='d' * 64)

    def device(self, **kw):
        args = dict(boot_id=self.p['boot_id'], marker=dict(boot_id=self.p['boot_id'], sha256=IMAGE),
                    used_path=self.path / 'used', motion_inhibit_paths=self.locks,
                    cancel_path=self.path / 'cancel', clock=self.clock)
        args.update(kw)
        return HeadLiftDevice(self.reg, self.p, self.clock, **args)

    def test_complete_single_axis_and_normal_lock_retained(self):
        d = self.device()
        self.assertEqual(self.reg.writes, [])
        with self.assertRaises(RuntimeError): d._check_motion_allowed()
        rows = []; run(d, rows.append, sleep=self.clock.sleep)
        self.assertTrue(rows[-1]['route_complete'])
        self.assertEqual(rows[-1]['state']['sequence'], 978)
        self.assertEqual(rows[-1]['state']['pulse_us'], [1500] * 10)
        self.assertFalse(rows[-1]['state']['armed'])
        frames = [r for r in rows if r['event'] == 'frame']
        self.assertEqual(len(frames), 301)
        self.assertEqual({r['state']['enabled_mask'] for r in frames}, {128})
        self.assertEqual(max(r['state']['pulse_us'][7] for r in frames), 1540)
        self.assertTrue(all(r['state']['pulse_us'][:7] + r['state']['pulse_us'][8:] == [1500]*9 for r in frames))
        self.assertEqual(max(abs(a[7]-b[7]) for a,b in zip(FRAMES,FRAMES[1:])), 1)
        self.assertEqual([p.read_text() for p in self.locks], ['locked','locked'])

    def test_cannot_repurpose_old_axis7_plan_or_old_stop_flag(self):
        with self.assertRaises(ValueError): validate_axis7(self.p)
        for key in ['new_hardware_request', 'onsite_observer', 'camera_required']:
            p = dict(self.p); p[key] = False
            with self.assertRaises(ValueError): validate_plan(p)
        p = dict(self.p); p['historical_source_sha256'] = 'e' * 64
        with self.assertRaises(ValueError): validate_plan(p)

    def test_stale_nonoff_or_wrong_image_never_writes(self):
        with self.assertRaises(ValueError): self.device(boot_id='another-boot')
        with self.assertRaises(ValueError): self.device(marker=dict(boot_id=self.p['boot_id'],sha256='bad'))
        for address, value in [(8,128),(0x10,1),(0x20,677),(0x24,1),(0x0c,1),(0x98,1501)]:
            self.reg = FakeRegisters(); self.reg.values[0x20]=676; self.reg.values[address]=value
            with self.assertRaises(RuntimeError): self.device()
            self.assertEqual(self.reg.writes, [])

    def test_only_exact_next_frame_and_mask(self):
        d=self.device();d.begin()
        for pulses,mask in [(FRAMES[0],64),(FRAMES[100],128),([1501]*10,128)]:
            with self.assertRaises(ValueError):d.commit(pulses,mask,allow_arm=True)
        self.assertEqual(self.reg.writes, [])

    def test_no_rearm_or_fast_catchup(self):
        d=self.device();d.begin();d.commit(FRAMES[0],MASK,allow_arm=True)
        with self.assertRaises(RuntimeError):d.commit(FRAMES[1],MASK)
        d.off();self.clock.sleep(.04)
        before=len(self.reg.writes)
        with self.assertRaises(RuntimeError):d.commit(FRAMES[1],MASK)
        self.assertEqual(len(self.reg.writes),before)

    def test_consumed_before_motion_cannot_run_twice(self):
        d=self.device();d.begin()
        with self.assertRaises(RuntimeError):d.begin()
        with self.assertRaises(FileExistsError):self.device().begin()
        self.assertEqual(self.reg.writes, [])

    def test_lock_change_host_loss_cancel_and_logging_error_off(self):
        for cause in ['lock','host','cancel','log']:
            with self.subTest(cause=cause):
                self.setUp();d=self.device();rows=[]
                def emit(row):
                    rows.append(row)
                    if row.get('event')=='frame' and row['index']==40:
                        if cause=='lock':self.locks[0].write_text('changed')
                        elif cause=='cancel':(self.path/'cancel').write_text('stop')
                        elif cause=='log':raise OSError('log failed')
                        else:
                            def lost():raise RuntimeError('lease lost')
                            self.clock.check=lost
                with self.assertRaises((RuntimeError,OSError)):run(d,emit,sleep=self.clock.sleep)
                self.assertFalse(d.status()['armed'])
                self.assertEqual(d.status()['enabled_mask'],0)
                self.assertNotEqual(d.status()['pulse_us'][7],1500)
                self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)

    def test_unknown_adoption_is_not_retried(self):
        self.reg.apply=False;d=self.device();rows=[]
        with self.assertRaises(TimeoutError):run(d,rows.append,sleep=self.clock.sleep)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertFalse(d.status()['armed'])

    def test_previous_run_digest_and_state_must_match(self):
        raw=(json.dumps(dict(event='outputs_off',route_complete=True,state=self.device().status()))+'\n').encode()
        self.p['prior_log_sha256']=hashlib.sha256(raw).hexdigest();validate_prior(self.p,raw)
        with self.assertRaises(ValueError):validate_prior(self.p,raw+b' ')
        p=dict(self.p);p['expected_sequence']=675
        with self.assertRaises(ValueError):validate_prior(p,raw)

    def test_scheduling_slack_is_bounded_without_acceleration(self):
        d=self.device();rows=[]
        run(d,rows.append,sleep=lambda t:self.clock.sleep(t+.001))
        self.assertTrue(rows[-1]['route_complete'])
        self.assertGreater(self.clock.now,12.15)
        self.assertLess(self.clock.now,16)

    def phone_plan(self):
        self.p.update(schema=PHONE_SCHEMA, expected_sequence=978,
                      prior_log_path=PHONE_LOG, prior_log_sha256=PHONE_LOG_SHA,
                      camera_views=['phone_mechanism'])
        self.reg.values[0x20] = 978

    def test_phone_check_uses_new_completion_and_keeps_original_route(self):
        self.phone_plan(); rows=[]
        run(self.device(), rows.append, sleep=self.clock.sleep)
        self.assertEqual(rows[-1]['state']['sequence'],1280)
        self.assertTrue(rows[-1]['route_complete'])
        self.assertTrue(all(r['state']['enabled_mask']==128 for r in rows[:-1]))

    def test_phone_plan_cannot_use_old_or_fabricated_provenance(self):
        self.phone_plan(); validate_plan(self.p)
        for key,value in [('expected_sequence',676),('prior_log_sha256','e'*64),
                          ('camera_views',['front']),('schema',SCHEMA),('prior_log_path',PHONE_LOG.replace('0c451','1c451'))]:
            p=dict(self.p);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        self.assertEqual(self.reg.writes,[])


class PhoneCameraTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image, ImageDraw
        image=Image.new('RGB',(80,40),'white')
        ImageDraw.Draw(image).rectangle((0,0,30,30),fill='black')
        buffer=io.BytesIO();image.save(buffer,format='JPEG');self.raw=buffer.getvalue()
        self.now=100.;self.number=1;self.epoch='a'*32;self.age=20;self.stamp=100.
        owner=self
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            @property
            def headers(self):
                return {'X-Frame-Id':owner.epoch+'-'+str(owner.number),
                        'X-Frame-Age-Ms':str(owner.age),
                        'X-Frame-Read-At':datetime.fromtimestamp(owner.stamp,timezone.utc).isoformat()}
            def read(self):return owner.raw
        self.camera=PhoneCamera(opener=lambda *a,**kw:Response(),clock=lambda:self.now,monotonic=lambda:self.now)

    def test_valid_frames_advance_and_decode(self):
        self.assertEqual(self.camera.sample()['size'],[80,40])
        self.number=2
        self.assertTrue(self.camera.sample()['frame'].endswith('-2'))

    def test_old_timestamp_stale_report_and_bad_jpeg_reject(self):
        self.stamp=98.
        with self.assertRaises(RuntimeError):self.camera.sample()
        self.stamp=100.;self.age=1501
        with self.assertRaises(RuntimeError):self.camera.sample()
        self.age=10;self.raw=b'not a JPEG'
        with self.assertRaises(OSError):self.camera.sample()

    def test_epoch_change_and_stalled_identity_reject(self):
        self.camera.sample();self.epoch='b'*32
        with self.assertRaises(RuntimeError):self.camera.sample()
        self.epoch='a'*32;self.now=self.stamp=101.6
        with self.assertRaises(RuntimeError):self.camera.sample()

    def test_camera_loss_interrupts_active_route_without_return(self):
        base=Tests('test_phone_check_uses_new_completion_and_keeps_original_route')
        base.setUp();self.addCleanup(base.doCleanups);base.phone_plan()
        device=base.device();rows=[]
        def emit(row):
            rows.append(row)
            if row.get('event')=='frame' and row['index']==40:
                self.age=1501
                self.camera.sample()
        with self.assertRaises(RuntimeError):run(device,emit,sleep=base.clock.sleep)
        self.assertFalse(device.status()['armed'])
        self.assertNotEqual(device.status()['pulse_us'][7],1500)
        self.assertEqual(sum(a==0x10 for a,v in base.reg.writes),1)


if __name__=='__main__':unittest.main()
