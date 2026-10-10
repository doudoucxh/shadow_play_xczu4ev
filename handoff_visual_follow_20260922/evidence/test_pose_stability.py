import unittest
import numpy as np
from pose_stability import PoseStabilizer

BOX=np.array([[100,100,600,700]],np.float32)
def pose(x=300):
    p=np.ones((1,9,3),np.float32);p[:,:,:2]=x
    return p

class Tests(unittest.TestCase):
    def test_static_quantization_noise_is_reduced(self):
        tracker=PoseStabilizer();raw=[];out=[]
        rng=np.random.default_rng(4)
        for i in range(150):
            p=pose();p[:,:,:2]+=rng.choice([-26.6667,0,26.6667],(1,9,2))
            result=tracker.update(BOX,[.9],p,i/28.6)
            raw.append(p[0,:,:2]);out.append(result[:,:2])
        a=np.linalg.norm(np.diff(raw[20:],axis=0),axis=2)
        b=np.linalg.norm(np.diff(out[20:],axis=0),axis=2)
        self.assertLess(np.percentile(b,95),np.percentile(a,95)*.4)

    def test_real_step_catches_up(self):
        tracker=PoseStabilizer()
        for i in range(10):tracker.update(BOX,[.9],pose(200),i/28.6)
        for i in range(10,16):r=tracker.update(BOX,[.9],pose(320),i/28.6)
        self.assertLess(np.max(abs(r[:,:2]-320)),8)

    def test_one_frame_outlier_is_not_drawn(self):
        tracker=PoseStabilizer();tracker.update(BOX,[.9],pose(),0)
        p=pose();p[0,5,:2]=700
        r=tracker.update(BOX,[.9],p,.035)
        self.assertEqual(r[5,2],0)
        r=tracker.update(BOX,[.9],pose(),.07)
        np.testing.assert_allclose(r[5,:2],[300,300])

    def test_track_does_not_switch_with_score_order(self):
        tracker=PoseStabilizer()
        boxes=np.array([[100,100,600,700],[700,100,1100,700]],np.float32)
        points=np.concatenate([pose(300),pose(900)])
        tracker.update(boxes,[.9,.8],points,0)
        r=tracker.update(boxes[::-1],[.99,.8],points[::-1],.035)
        np.testing.assert_allclose(r[:,:2],300)
        self.assertEqual(tracker.selected,1)

    def test_missing_evidence_not_synthesized_and_reacquired(self):
        tracker=PoseStabilizer();tracker.update(BOX,[.9],pose(),0)
        self.assertIsNone(tracker.update([],[],[],.1))
        self.assertIsNone(tracker.update([],[],[],.5))
        r=tracker.update(BOX,[.9],pose(400),.6)
        np.testing.assert_allclose(r[:,:2],400)

if __name__=='__main__':unittest.main()
