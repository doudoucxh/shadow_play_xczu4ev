import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

p = Path(__file__).resolve().parents[1]/'integrations/calibration/tiger_audio_segment.py'
spec = importlib.util.spec_from_file_location('segment', p)
segment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(segment)


class Device:
    def __init__(self):
        self.plan = {'profile':'tiger-operator-low-rear-fast','expected_pulses_us':[1500]*10}
        self.route_sha256 = 'test'
        self.sequence = 4
        self.host = SimpleNamespace(action=('demo',4))
        self.targets = [None]*8
        self.t = 0
        self.moves = []
        self.stopped = False
        self.normal = False
    def clock(self): return self.t
    def status(self): return {'sequence':self.sequence}
    def check(self): return self.status()
    def adopt(self,p): return self.status()
    def wait(self,n,sleep): self.t+=n; self.check()
    def advance(self,stage,emit,sleep): self.check(); self.moves.append((stage,self.t)); self.t+=.2
    def off(self): self.stopped=True; return self.status()
    def stop_after_frame(self): self.normal=True; return self.off()


class Clip:
    def __init__(self,fail=False): self.finished=False; self.closed=False; self.fail=fail
    def start(self,d,sleep): self.d=d; self.output='PLAY_COMPLETE'; return d.clock()
    def check(self):
        if not hasattr(self,'d'): return
        if self.fail and self.d.t>=2.1: raise RuntimeError('audio device lost')
        self.finished=self.d.t>=7
    def close(self): self.closed=True


class Tests(unittest.TestCase):
    def test_audio_lead_and_normal_stop(self):
        d=Device();a=Clip();events=[]
        segment.run_segment(d,events.append,audio_factory=lambda:a)
        self.assertAlmostEqual(d.moves[0][1],2)
        self.assertEqual([v[0] for v in d.moves],list(range(1,8)))
        self.assertTrue(d.normal and d.stopped and a.closed)
        self.assertEqual(events[-1]['event'],'outputs_off')
    def test_audio_failure_stops_motion_and_audio(self):
        d=Device();a=Clip(True)
        with self.assertRaisesRegex(RuntimeError,'audio device lost'):
            segment.run_segment(d,lambda e:None,audio_factory=lambda:a)
        self.assertTrue(d.stopped and a.closed)
        self.assertFalse(d.normal)
        self.assertEqual(len(d.moves),1)
    def test_bad_audio_never_adopts(self):
        d=Device();d.adopt=lambda p:self.fail('must not enable output')
        def bad(): raise RuntimeError('missing audio')
        with self.assertRaises(RuntimeError):
            segment.run_segment(d,lambda e:None,audio_factory=bad)
        self.assertTrue(d.stopped)


if __name__=='__main__': unittest.main()
