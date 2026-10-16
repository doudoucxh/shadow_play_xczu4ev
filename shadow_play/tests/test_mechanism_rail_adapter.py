import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mechanism_rail_adapter import UnconfiguredRailDriver,RailUnavailable,simulated_relative

class Rails(unittest.TestCase):
    def test_real_driver_cannot_be_accidentally_enabled(self):
        d=UnconfiguredRailDriver();self.assertFalse(d.ready)
        with self.assertRaises(RailUnavailable):d.move_relative('rail1',1)
        with self.assertRaises(RailUnavailable):d.home('rail1')
        self.assertFalse(d.stop()['confirmed'])
    def test_simulation_needs_reference_and_stays_in_travel(self):
        self.assertEqual(simulated_relative(5,-1,0,100),4)
        for values in [(None,1,0,100),(0,-1,0,100),(100,1,0,100),(5,1,10,0),(5,float('nan'),0,100),(True,1,0,100)]:
            with self.assertRaises(ValueError):simulated_relative(*values)

if __name__=='__main__':unittest.main()
