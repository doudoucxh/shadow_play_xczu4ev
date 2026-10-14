import importlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from test_tiger_height_trial import Fake
m=importlib.import_module('person_variety_trial')


class Tests(unittest.TestCase):
    def test_full_route_stops_without_replaying_reverse(self):
        d=Fake(len(m.TARGETS)-1);events=[];m.run(d,events.append)
        self.assertEqual(d.visited,m.TARGETS[1:])
        self.assertTrue(d.normal and d.stopped)
        self.assertTrue(next(e for e in events if e['event']=='person_variety_complete')['full_route_executed'])
    def test_partial_trial_reverses_only_visited_corridor(self):
        d=Fake(2);events=[];m.run(d,events.append)
        self.assertEqual(d.visited,[m.TARGETS[1],m.TARGETS[2],m.TARGETS[1],m.TARGETS[0]])
        self.assertFalse(next(e for e in events if e['event']=='person_variety_complete')['full_route_executed'])
    def test_tiger_unchanged_and_bare_inset_not_exceeded(self):
        lo=[10,95,10,50,70,50];hi=[260,260,260,170,260,170]
        for p in m.TARGETS:
            self.assertEqual(p[6:],m.START[6:])
            for v,a,b in zip(p,lo,hi):self.assertTrue(500+a*2000/270<=v<=500+b*2000/270)


if __name__=='__main__':unittest.main()
