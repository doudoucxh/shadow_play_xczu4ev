import copy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'integrations/calibration'),str(ROOT/'tests')]
from fixed_v20_a01_audio import (A01AudioDevice,AudioClip,BOOT,IMAGE,SCHEMA,PRIOR,PRIOR_SHA,
    frames,validate_plan,validate_prior,MIDPOINT,digest,run_audio)
from servo_pwm_device import PINS
from test_servo_commissioning import FakeRegisters
from test_v20_first_direction import Clock


def plan():
    return dict(schema=SCHEMA,session_id='a'*32,new_request_id='b'*32,boot_id=BOOT,
        channel='tiger4',expected_sequence=1542,expected_pulse_us=MIDPOINT[:],
        route_sha256=digest(frames()),prior_log_path=PRIOR,prior_log_sha256=PRIOR_SHA,
        camera_required=True,onsite_observer=True,new_hardware_request=True,mechanism_visible=True)


class FakeAudio:
    output=b'PLAY_COMPLETE frames=302400 elapsed=6.300\n'
    def __init__(self,clock,fail=False):self.clock=clock;self.fail=fail;self.finished=False;self.closed=False
    def start(self,d,sleep):self.onset=self.clock();return self.onset
    def check(self):
        if self.fail and self.clock()-self.onset>1.5:raise RuntimeError('audio failed')
        self.finished=self.clock()-self.onset>=6.3
    def close(self):self.closed=True


class Tests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.path=Path(temp.name)
        self.locks=[self.path/'global',self.path/'local']
        for p in self.locks:p.write_text('locked')
        self.reg=FakeRegisters();self.reg.values[0x20]=1542;self.clock=Clock();self.p=plan()
    def device(self):
        return A01AudioDevice(self.reg,self.p,self.clock,boot_id=BOOT,
            marker=dict(boot_id=BOOT,sha256=IMAGE,pins=list(PINS),design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS'),
            used_path=self.path/'used',motion_inhibit_paths=self.locks,cancel_path=self.path/'cancel',clock=self.clock)

    def test_audio_clock_only_tiger_changes_and_normal_close(self):
        d=self.device();audio=FakeAudio(self.clock);rows=[]
        run_audio(d,rows.append,audio,sleep=self.clock.sleep)
        q=[r for r in rows if r['event']=='frame']
        self.assertTrue(310<=len(q)<=318)
        self.assertEqual({r['state']['enabled_mask'] for r in q},{1023})
        self.assertTrue(all(r['state']['pulse_us'][:6]==[1500]*6 for r in q))
        self.assertLessEqual(max(abs(a-b) for x,y in zip(q,q[1:]) for a,b in zip(x['state']['pulse_us'],y['state']['pulse_us'])),4)
        self.assertGreaterEqual(q[-1]['audio_time_s'],6.3)
        self.assertTrue(rows[-1]['route_complete']);self.assertFalse(d.status()['armed'])
        self.assertEqual(d.status()['pulse_us'],MIDPOINT);self.assertTrue(audio.closed)

    def test_audio_loss_stops_in_place_and_closes_process(self):
        d=self.device();audio=FakeAudio(self.clock,fail=True);rows=[]
        with self.assertRaises(RuntimeError):run_audio(d,rows.append,audio,sleep=self.clock.sleep)
        self.assertTrue(audio.closed);self.assertFalse(d.status()['armed'])
        self.assertNotEqual(d.status()['pulse_us'],MIDPOINT)
        self.assertEqual(sum(a==0x10 for a,v in self.reg.writes),1)

    def test_wrong_prior_arbitrary_pulses_and_catchup_rejected(self):
        for key,value in [('expected_sequence',910),('prior_log_sha256','d'*64),('camera_required',False)]:
            p=copy.deepcopy(self.p);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        with self.assertRaises(ValueError):validate_prior(b'changed slow log')
        d=self.device();d.begin()
        with self.assertRaises(RuntimeError):d.commit(MIDPOINT,1023,allow_arm=True)
        d.adopt_sample();d.set_onset(self.clock())
        before=len(self.reg.writes)
        with self.assertRaises(RuntimeError):d.adopt_sample()
        self.clock.sleep(.2)
        with self.assertRaises(RuntimeError):d.adopt_sample()
        self.assertEqual(len(self.reg.writes),before)

    def test_player_must_complete_exact_clip_length(self):
        for text,ok in [(b'PLAY_COMPLETE frames=302400 elapsed=6.3\n',True),
                        (b'PLAY_COMPLETE frames=3024000 elapsed=6.3\n',False),
                        (b'PLAY_FAILED frames=123 elapsed=.1\n',False)]:
            audio=AudioClip();audio.process=Mock();audio.process.poll.return_value=0
            with patch('fixed_v20_a01_audio.os.read',side_effect=[text,b'']):
                if ok:audio.check();self.assertTrue(audio.finished)
                else:
                    with self.assertRaises(RuntimeError):audio.check()


if __name__=='__main__':unittest.main()
