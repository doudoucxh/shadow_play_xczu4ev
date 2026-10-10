import unittest
import queue
import time
import numpy as np
from optimized_input import QuantizedInput,safe_snapshot,LatestCamera
from postprocess import preprocess

class Tests(unittest.TestCase):
    def test_quantization_matches_reference(self):
        rng=np.random.default_rng(2)
        frames=[rng.integers(0,256,(720,1280,3),dtype=np.uint8),np.full((720,1280,3),255,np.uint8),np.zeros((720,1280,3),np.uint8)]
        for fix in (-2,0,3,6,7,8):
            prepare=QuantizedInput(fix)
            for frame in frames:
                x,t=preprocess(frame,384)
                reference=np.ascontiguousarray(np.clip(np.rint(x.transpose(0,2,3,1)*2.**fix),-128,127).astype(np.int8))
                result,actual_t=prepare(frame)
                np.testing.assert_array_equal(reference,result)
                self.assertEqual(t,actual_t)
                self.assertTrue(result.flags.c_contiguous)

    def test_reject_crossing_slow_or_invalid_snapshot(self):
        self.assertTrue(safe_snapshot(0,0,.026))
        for args in ((0,1,.020),(0,0,.1),(0,0,.031),(3,3,.001),(-1,-1,.001),(0,0,-1)):
            self.assertFalse(safe_snapshot(*args))

    def test_latest_frame_delivery_and_staleness(self):
        c=LatestCamera.__new__(LatestCamera)
        c.error=None;c.queue=queue.Queue(maxsize=1)
        image=np.zeros((2,2,3),np.uint8)
        c.queue.put((image,3,time.monotonic()))
        result=c.read()
        self.assertIs(result[0],image)
        self.assertEqual(result[1],3)
        c.queue.put((image,4,time.monotonic()-1))
        with self.assertRaisesRegex(RuntimeError,'stale'):c.read()

    def test_producer_failure_is_not_silently_reused(self):
        c=LatestCamera.__new__(LatestCamera)
        c.error=RuntimeError('capture stopped')
        with self.assertRaisesRegex(RuntimeError,'producer failed'):c.read()

if __name__=='__main__':unittest.main()
