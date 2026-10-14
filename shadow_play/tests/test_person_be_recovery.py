import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_be_recovery as m


class Device:
    def __init__(self):
        self.sequence=27435; self.pulses=m.START[:]
        self.host=SimpleNamespace(action=('demo',27435)); self.moves=[];self.stopped=False
    def check(self): return {'pulse_us':self.pulses[:],'sequence':self.sequence}
    def adopt(self,p):
        assert p==m.START
        return self.check()
    def advance(self,stage,emit,sleep):
        self.pulses=self.targets[stage][:];self.moves.append(self.pulses[:]);self.sequence+=1
        self.host.action=('finish',self.sequence)
    def stop_after_frame(self): self.stopped=True; return self.check()
    off=stop_after_frame


class Tests(unittest.TestCase):
    def test_finish_stops_at_partial_recovery_without_reverse(self):
        d=Device();events=[];m.run(d,events.append)
        self.assertEqual(d.moves,[m.TARGETS[1]])
        self.assertTrue(d.stopped)
        self.assertFalse(next(e for e in events if e['event']=='recovery_complete')['recovered_reference'])
    def test_first_four_edges_only_retrace_last_edge(self):
        for i,q in enumerate(m.TARGETS[:5]):
            self.assertEqual(q,[a+round((b-a)*i/4) for a,b in zip(m.START,m.HIGH)])
        self.assertEqual(m.TARGETS[-1],m.REFERENCE)
        self.assertTrue(all(q[6:]==m.START[6:] for q in m.TARGETS))
    def test_missing_confirmation_cannot_validate(self):
        with self.assertRaises(ValueError):m.validate({},[])


if __name__=='__main__': unittest.main()
