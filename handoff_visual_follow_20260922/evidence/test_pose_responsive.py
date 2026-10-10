import unittest
import numpy as np
from pose_stability import PoseStabilizer as Previous
from pose_responsive import PoseStabilizer as Responsive

BOX=np.array([[100,100,600,700]],np.float32)
def point(x):
    p=np.ones((1,9,3),np.float32);p[:,:,:2]=300;p[0,5,0]=x
    return p

def simulate(cls,values):
    f=cls();out=[]
    for i,x in enumerate(values):out.append(f.update(BOX,[.9],point(x),i/28.6)[5].copy())
    return np.array(out)

class Tests(unittest.TestCase):
    def test_follows_moderate_step_within_two_frames(self):
        values=[300]*10+[350]*8
        slow=simulate(Previous,values);fast=simulate(Responsive,values)
        self.assertLess(abs(fast[11,0]-350),6)
        self.assertLess(abs(fast[11,0]-350),abs(slow[11,0]-350)*.5)

    def test_constant_movement_lag_is_reduced(self):
        values=[300]*10+list(np.arange(315,600,15))
        a=simulate(Previous,values);b=simulate(Responsive,values)
        old=np.mean(np.abs(a[13:,0]-np.array(values[13:])))
        new=np.mean(np.abs(b[13:,0]-np.array(values[13:])))
        self.assertLess(new,old*.4)

    def test_gross_outlier_remains_hidden(self):
        out=simulate(Responsive,[300]*10+[700,300,300])
        self.assertEqual(out[10,2],0)
        self.assertLess(abs(out[11,0]-300),1)

    def test_static_alternating_quantum_not_passed_directly(self):
        values=[300]*10+[300+(-1)**i*26.6667 for i in range(100)]
        out=simulate(Responsive,values)
        raw=np.abs(np.diff(values[20:]));filtered=np.abs(np.diff(out[20:,0]))
        self.assertLess(float(np.mean(filtered)),float(np.mean(raw))*.65)

if __name__=='__main__':unittest.main()
