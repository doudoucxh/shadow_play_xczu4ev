import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from image_response_review import compare


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.before=np.random.default_rng(1).uniform(.15,.75,(120,160))
        self.fixed=(15,70,45,35);self.moving=(85,15,50,40)

    def test_camera_jitter_and_global_brightness_are_not_axis_motion(self):
        after=np.roll(self.before,(-1,2),(0,1))*.9+.03
        result=compare(self.before,after,self.fixed,self.moving)
        self.assertEqual(result['camera_shift_pixels'],[2,-1])
        self.assertEqual(result['verdict'],'no_clear_pixel_change')
        self.assertFalse(result['automatic_motion_allowed'])
        self.assertIsNone(result['angle_feedback'])

    def test_local_change_is_visible_but_does_not_authorize_motion(self):
        after=self.before.copy();after[20:50,95:125]=1-after[20:50,95:125]
        result=compare(self.before,after,self.fixed,self.moving)
        self.assertEqual(result['verdict'],'visible_pixel_change')
        self.assertFalse(result['automatic_motion_allowed'])

    def test_invalid_or_unobservable_images_never_produce_motion_feedback(self):
        flat=np.zeros_like(self.before)
        self.assertEqual(compare(flat,flat,self.fixed,self.moving)['verdict'],'unresolved')
        changed=np.random.default_rng(4).uniform(.15,.75,self.before.shape)
        self.assertEqual(compare(self.before,changed,self.fixed,self.moving)['verdict'],'unresolved')
        with self.assertRaises(ValueError):compare(self.before,flat[:90],self.fixed,self.moving)
        with self.assertRaises(ValueError):compare(self.before,self.before,self.fixed,(-1,0,40,40))
        with self.assertRaises(ValueError):compare(self.before,self.before,self.fixed,self.moving,99)


if __name__=='__main__':unittest.main()
