import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import story_midpoint_first_edge as first
from test_story_midpoint_session import plan
from test_servo_commissioning import FakeRegisters


class FirstEdgeTests(unittest.TestCase):
    def setUp(self):
        self.p=dict(plan(),profile=first.PROFILE,first_edge_only=True)
        self.r=FakeRegisters();self.r.values[0x20]=34027
        self.now=0.

    def device(self):
        return first.FirstEdgeDevice(self.r,self.p,Mock(),clock=lambda:self.now,
                                     cancel_path='__missing_cancel__')

    def test_only_compiled_edge_then_no_more_frames(self):
        with patch.object(first.FirstEdgeDevice,'lock_hashes',return_value=('same',)):
            d=self.device()
            for index,q in enumerate(first.FRAMES):
                self.now=index*.021
                d.next_command=q
                d.adopt(q)
                d.phase='transition'
            self.assertEqual(d.pulses,first.m.TARGETS[1])
            with self.assertRaises(RuntimeError):d.adopt(first.m.TARGETS[2])
            with self.assertRaises(RuntimeError):d.adopt(first.FRAMES[0])

    def test_run_finishes_off_without_audio_or_show(self):
        with patch.object(first.FirstEdgeDevice,'lock_hashes',return_value=('same',)), \
             patch.object(first.m,'await_action'):
            d=self.device();events=[]
            def sleep(t):self.now+=t+.000001
            first.run(d,events.append,sleep)
            self.assertEqual(d.frame_index,101)
            self.assertFalse(events[-1]['state']['armed'])
            self.assertTrue(events[-1]['normal_frame_stop'])
            self.assertFalse(events[-1]['full_show_executed'])

    def test_no_scope_confirmation_is_rejected(self):
        self.p['first_edge_only']=False
        with self.assertRaises(ValueError):self.device()
        self.assertEqual(self.r.writes,[])

    def test_deadline_prevents_reenable(self):
        with patch.object(first.FirstEdgeDevice,'lock_hashes',return_value=('same',)):
            d=self.device();self.now=46
            with self.assertRaises(RuntimeError):d.adopt(first.FRAMES[0])
        self.assertEqual(self.r.writes,[])


if __name__=='__main__':unittest.main()
