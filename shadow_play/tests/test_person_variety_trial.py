import importlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from test_tiger_height_trial import Fake as BaseFake
m=importlib.import_module('person_variety_trial')


class Fake(BaseFake):
    def wait(self,n,sleep):
        if n!=.10:raise AssertionError('Unexpected idle in fake')


class Tests(unittest.TestCase):
    def test_withdrawn_route_cannot_reach_device(self):
        # A bare object has no device methods: rejection must precede adoption.
        events=[]
        with self.assertRaisesRegex(RuntimeError,'withdrawn'):
            m.run(object(),events.append)
        self.assertEqual(events,[])
    def test_withdrawn_route_rejects_even_before_plan_parsing(self):
        with self.assertRaisesRegex(RuntimeError,'withdrawn'):
            m.validate({},[])
    def test_tiger_unchanged_and_bare_inset_not_exceeded(self):
        lo=[10,95,10,50,70,50];hi=[260,260,260,170,260,170]
        for p in m.TARGETS:
            self.assertEqual(p[6:],m.START[6:])
            for v,a,b in zip(p,lo,hi):self.assertTrue(500+a*2000/270<=v<=500+b*2000/270)


if __name__=='__main__':unittest.main()
