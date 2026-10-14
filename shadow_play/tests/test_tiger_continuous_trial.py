import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('trial',Path(__file__).parents[1]/'integrations/calibration/tiger_continuous_trial.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Device:
    def __init__(self,fail=False):
        self.host=SimpleNamespace(action=None);self.sequence=1;self.plan={}
        self.pulses=m.START[:];self.moves=[];self.fail=fail;self.stopped=None
    def check(self):return dict(sequence=self.sequence,pulse_us=self.pulses[:])
    def adopt(self,p):self.pulses=p[:];return self.check()
    def wait(self,*args):self.host.action=('demo',self.sequence)
    def advance(self,i,emit,sleep):
        if self.fail:raise RuntimeError('camera lost')
        self.pulses=self.targets[i][:];self.sequence+=1;self.moves.append(self.pulses[:])
    def stop_after_frame(self):self.stopped='normal';return self.check()
    def off(self):self.stopped='interrupted';return self.check()

class TrialTests(unittest.TestCase):
    def test_complete_fixed_cycles_leave_person_commands_unchanged(self):
        d=Device();events=[];m.run(d,events.append)
        self.assertEqual(len(d.moves),3*(len(m.TARGETS)-1))
        self.assertTrue(all(q[:6]==m.START[:6] for q in d.moves))
        self.assertEqual(d.pulses,m.START);self.assertEqual(d.stopped,'normal')
    def test_interruption_stops_without_reverse(self):
        d=Device(True)
        with self.assertRaisesRegex(RuntimeError,'camera lost'):m.run(d,lambda e:None)
        self.assertEqual(d.moves,[]);self.assertEqual(d.stopped,'interrupted')

if __name__=='__main__':unittest.main()
