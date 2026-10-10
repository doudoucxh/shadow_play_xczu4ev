import unittest
import cv2
import numpy as np
from orientation import orient_frame, keypoints_to_camera

class Tests(unittest.TestCase):
    def test_pixels_rotated_before_preprocessing(self):
        a = np.arange(6*8*3, dtype=np.uint8).reshape(6,8,3)
        b = orient_frame(a)
        np.testing.assert_array_equal(b, a[::-1,::-1])
        np.testing.assert_array_equal(orient_frame(b), a)
        self.assertFalse(np.shares_memory(a,b))

    def test_ids_confidence_and_coordinate_roundtrip(self):
        p = np.array([[[0.,0.,.5],[1279.,719.,.9],[600.,400.,0.]]])
        q = keypoints_to_camera(p,1280,720)
        np.testing.assert_array_equal(q[0,:,:2],[[1279,719],[0,0],[679,319]])
        np.testing.assert_array_equal(q[...,2],p[...,2])
        np.testing.assert_array_equal(keypoints_to_camera(q,1280,720),p)
        self.assertFalse(np.shares_memory(p,q))

    def test_empty_and_invalid(self):
        self.assertEqual(keypoints_to_camera(np.empty((0,9,3)),1280,720).shape,(0,9,3))
        with self.assertRaises(ValueError): orient_frame(np.zeros((2,2,3),np.uint8),90)

if __name__ == '__main__': unittest.main()
