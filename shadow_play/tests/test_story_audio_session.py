import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
score=importlib.import_module('story_motion')
actor=importlib.import_module('story_audio_session')


class Device:
    def __init__(self,mode):
        self.plan=dict(story_mode=mode);self.t=0.;self.last_start=0.
        self.sequence=1;self.host=SimpleNamespace(action=('demo',2));self.pulses=score.BASE[:]
        self.stopped=False;self.normal=False
    def clock(self):return self.t
    def status(self):return dict(pulse_us=self.pulses[:],sequence=self.sequence)
    def check(self):return self.status()
    def adopt(self,p):self.pulses=p[:];self.sequence+=1;self.last_start=self.t;return self.status()
    def wait(self,n,sleep):self.t+=max(n,.000001);self.check()
    def advance(self,i,emit,sleep):self.t+=.1;self.adopt(self.targets[i]);self.check()
    def off(self):self.stopped=True;return self.status()
    def stop_after_frame(self):self.normal=True;return self.off()


class Audio:
    def __init__(self,mode,fail=False):self.duration=actor.MODES[mode][1]-actor.MODES[mode][0];self.finished=False;self.fail=fail;self.closed=False
    def start(self,d,sleep):self.d=d;self.onset=d.clock();return self.onset
    def check(self):
        if not hasattr(self,'d'):return
        if self.fail and self.d.clock()-self.onset>.5:raise RuntimeError('speaker lost')
        self.finished=self.d.clock()-self.onset>=self.duration;self.output='PLAY_COMPLETE'
    def close(self):self.closed=True


class Tests(unittest.TestCase):
    def test_full_audio_coverage_and_terminal_hold(self):
        d=Device('full');a=Audio('full');ev=[];actor.run(d,ev.append,a)
        self.assertTrue(d.normal and d.stopped and a.closed)
        self.assertEqual(d.pulses,score.sample(score.DURATION))
        self.assertNotEqual(d.pulses,score.BASE)
        self.assertTrue(next(e for e in ev if e['event']=='story_complete')['full_show_executed'])
        self.assertAlmostEqual(next(e for e in ev if e['event']=='timeline_complete')['original_range_s'][1],score.DURATION)
        self.assertGreater(len([e for e in ev if e['event']=='timeline_checkpoint']),100)
    def test_fight_entry_and_exit(self):
        d=Device('fight');a=Audio('fight');ev=[];actor.run(d,ev.append,a)
        self.assertEqual(d.pulses,score.BASE)
        self.assertTrue(d.normal)
        names=[e['event'] for e in ev]
        self.assertLess(names.index('entry_complete'),names.index('audio_running_observed'))
        self.assertLess(names.index('audio_complete'),names.index('segment_exit_started'))
    def test_audio_failure_no_automatic_return(self):
        d=Device('fight');a=Audio('fight',True);ev=[]
        with self.assertRaisesRegex(RuntimeError,'speaker lost'):actor.run(d,ev.append,a)
        self.assertFalse(d.normal);self.assertTrue(d.stopped and a.closed)
        self.assertNotIn('segment_exit_started',[e['event'] for e in ev])
    def test_bounds_and_finite_full_track(self):
        self.assertLessEqual(score.check_envelope()['peak_20ms_step_us'],22)
        self.assertEqual(score.sample(0),score.BASE)
        self.assertEqual(score.sample(score.DURATION+10),score.sample(score.DURATION))
        for track in [score.HUMAN,score.TIGER]:
            for t,p,_ in track:self.assertEqual(score.sample_track(track,t),p)


if __name__=='__main__':unittest.main()
