import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
m=importlib.import_module('tiger_shadow_roar')


class Device:
    def __init__(self):
        self.plan={};self.t=0.;self.last_start=0.;self.sequence=1
        self.host=SimpleNamespace(action=('demo',2));self.pulses=m.START[:];self.normal=False;self.stopped=False
    def clock(self):return self.t
    def check(self):return dict(pulse_us=self.pulses[:],sequence=self.sequence)
    def adopt(self,p):self.pulses=p[:];self.sequence+=1;self.last_start=self.t;return self.check()
    def wait(self,n,sleep):self.t+=max(n,.000001);self.check()
    def off(self):self.stopped=True;return self.check()
    def stop_after_frame(self):self.normal=True;return self.off()


class Audio:
    def __init__(self,fail=False):self.finished=False;self.closed=False;self.fail=fail
    def start(self,d,sleep):self.d=d;self.onset=d.clock();return self.onset
    def check(self):
        if not hasattr(self,'d'):return
        if self.fail and self.d.clock()-self.onset>.5:raise RuntimeError('audio lost')
        self.finished=self.d.clock()-self.onset>=3;self.output='PLAY_COMPLETE'
    def close(self):self.closed=True


class Tests(unittest.TestCase):
    def test_roar_returns_and_waits_for_audio(self):
        d=Device();a=Audio();ev=[];m.run(d,ev.append,lambda:a)
        self.assertTrue(d.normal and d.stopped and a.closed)
        self.assertEqual(d.pulses,m.START)
        self.assertEqual(len([e for e in ev if e['event']=='roar_checkpoint']),len(m.TRACK))
        self.assertFalse(next(e for e in ev if e['event']=='shadow_roar_complete')['actual_stage_effect_verified'])
    def test_audio_loss_stops_without_recenter(self):
        d=Device();a=Audio(True)
        with self.assertRaisesRegex(RuntimeError,'audio lost'):m.run(d,lambda e:None,lambda:a)
        self.assertTrue(d.stopped and a.closed);self.assertFalse(d.normal);self.assertNotEqual(d.pulses,m.START)
    def test_fixed_observed_corridor_and_rate(self):
        samples=[m.sample(i*.02) for i in range(151)]
        self.assertLessEqual(max(abs(a-b) for x,y in zip(samples,samples[1:]) for a,b in zip(x,y)),24)
        for p in samples:self.assertEqual(p[:7],m.START[:7]);self.assertEqual(p[8],m.START[8])
        for t,i in m.TRACK:self.assertEqual(m.sample(t),m.LEVELS[i])


if __name__=='__main__':unittest.main()
