import unittest
import time
import numpy as np
from pipeline_input import safe_snapshot,BlockCopier
from display_queue import DisplayQueue

class FakeDisplay:
    def __init__(self):self.frames=[]
    def present(self,frame):self.frames.append(frame)

class Tests(unittest.TestCase):
    def test_block_copy_is_exact_and_independent(self):
        copier=BlockCopier()
        try:
            rng=np.random.default_rng(33)
            for shape in ((720,1280,3),(3,3,3)):
                source=rng.integers(0,256,shape,dtype=np.uint8)
                original=source.copy()
                result=copier.copy(source)
                np.testing.assert_array_equal(result,original)
                self.assertFalse(np.shares_memory(result,source))
                result.fill(0)
                np.testing.assert_array_equal(source,original)
        finally:copier.close()

    def test_snapshot_one_writer_step_is_safe_but_two_is_not(self):
        for before in range(3):
            self.assertTrue(safe_snapshot(before,before,.027))
            self.assertTrue(safe_snapshot(before,(before+1)%3,.027))
            self.assertFalse(safe_snapshot(before,(before+2)%3,.027))
            self.assertFalse(safe_snapshot(before,before,.031))
            self.assertFalse(safe_snapshot(before,(before+1)%3,.031))
        self.assertFalse(safe_snapshot(-1,0,.001))

    def test_renderer_keeps_exact_frame_and_generation(self):
        display=FakeDisplay();worker=DisplayQueue(display)
        try:
            frame=np.zeros((3,3,3),np.uint8)
            worker.submit(frame,4,time.monotonic())
            deadline=time.monotonic()+1
            while worker.presented<1 and time.monotonic()<deadline:time.sleep(.001)
            self.assertEqual(worker.presented,1)
            self.assertIs(display.frames[0],frame)
            self.assertEqual(worker.last_sequence,4)
            worker.submit(frame,3,time.monotonic())
            deadline=time.monotonic()+1
            while worker.error is None and time.monotonic()<deadline:time.sleep(.001)
            with self.assertRaisesRegex(RuntimeError,'worker failed'):worker.check()
        finally:worker.close()

if __name__=='__main__':unittest.main()
