import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('duel',Path(__file__).parents[1]/'integrations/calibration/duel_interaction_trial.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Device:
    def __init__(self,fail_at=None):
        self.host=SimpleNamespace(action=None);self.sequence=1;self.plan={};self.pulses=m.START[:]
        self.moves=[];self.fail_at=fail_at;self.stopped=None
    def check(self):return dict(sequence=self.sequence,pulse_us=self.pulses[:])
    def adopt(self,p):self.pulses=p[:];return self.check()
    def wait(self,*args):self.host.action=('demo',self.sequence)
    def advance(self,i,emit,sleep):
        if len(self.moves)==self.fail_at:raise RuntimeError('lease lost')
        self.pulses=self.targets[i][:];self.sequence+=1;self.moves.append(self.pulses[:])
    def stop_after_frame(self):self.stopped='normal';return self.check()
    def off(self):self.stopped='interrupted';return self.check()
class Tests(unittest.TestCase):
    def test_four_distinct_phrases_return_to_reference(self):
        d=Device();events=[];m.run(d,events.append)
        self.assertEqual(len(d.moves),20);self.assertEqual(d.pulses,m.START)
        self.assertEqual(len([e for e in events if e['event']=='interaction_phrase_complete']),4)
        self.assertEqual(d.stopped,'normal')
    def test_loss_stops_in_place_without_reversal(self):
        d=Device(7)
        with self.assertRaisesRegex(RuntimeError,'lease lost'):m.run(d,lambda e:None)
        self.assertEqual(len(d.moves),7);self.assertEqual(d.stopped,'interrupted')
    def test_inset_envelope(self):
        for q in m.TARGETS:
            for p,lo,hi in zip(q,[10,95,10,50,70,50,50,100,70,50],[260,260,260,170,260,170,190,190,200,170]):
                self.assertGreaterEqual(p,500+lo*2000/270);self.assertLessEqual(p,500+hi*2000/270)
if __name__=='__main__':unittest.main()
