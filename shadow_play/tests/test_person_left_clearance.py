import unittest
from test_person_be_recovery import Device
import person_left_clearance as m

class Fake(Device):
    def __init__(self):
        super().__init__();self.pulses=m.START[:]
    def adopt(self,p):
        assert p==m.START
        return self.check()

class Tests(unittest.TestCase):
    def test_separate_before_lift_and_cross(self):
        self.assertEqual(m.OUT[1][0],m.START[0]-60)
        self.assertEqual(m.OUT[1][1:],m.START[1:])
        self.assertEqual(m.OUT[2][0],m.OUT[1][0])
        self.assertEqual(m.OUT[2][1],m.START[1]+20)
        self.assertEqual(m.TARGETS[-1],m.START)
        self.assertTrue(all(q[6:]==m.START[6:] for q in m.TARGETS))
    def test_stop_cannot_trigger_auto_return(self):
        d=Fake();events=[];m.run(d,events.append)
        self.assertEqual(d.moves,[m.OUT[1]])
        self.assertTrue(d.stopped)
    def test_missing_recovery_evidence_rejected(self):
        with self.assertRaises(ValueError):m.validate({},[])

if __name__=='__main__':unittest.main()
