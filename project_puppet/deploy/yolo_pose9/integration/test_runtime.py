import sys, unittest, struct
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import runtime
from postprocess import preprocess,decode

class RuntimeTests(unittest.TestCase):
    def test_letterbox_full_720p_rgb(self):
        frame=np.zeros((720,1280,3),np.uint8); frame[:,:,2]=255
        x,t=preprocess(frame)
        self.assertEqual(x.shape,(1,3,384,384)); self.assertEqual(t,(.3,0,84,1280,720))
        np.testing.assert_allclose(x[0,:,100,100],[1,0,0])
        np.testing.assert_allclose(x[0,:,0,0],114/255)
    def test_no_person_has_no_pose(self):
        outputs=[]
        for n in (48,24,12):
            outputs.extend([np.zeros((1,64,n,n),np.float32),np.full((1,1,n,n),-20,np.float32),np.zeros((1,27,n,n),np.float32)])
        boxes,scores,points=decode(outputs,(.3,0,84,1280,720))
        self.assertEqual(len(points),0)
    def test_coordinate_restore_and_visibility(self):
        outputs=[]
        for n in (48,24,12):
            outputs.extend([np.zeros((1,64,n,n),np.float32),np.full((1,1,n,n),-20,np.float32),np.zeros((1,27,n,n),np.float32)])
        outputs[1][0,0,24,24]=20
        outputs[2][0,2::3,24,24]=20
        boxes,scores,points=decode(outputs,(.3,0,84,1280,720))
        self.assertEqual(points.shape,(1,9,3))
        np.testing.assert_allclose(points[0,:,:2],np.tile([640,360],(9,1)),atol=1e-4)
    def test_capture_halt_rejected(self):
        camera=runtime.VdmaFullFrame.__new__(runtime.VdmaFullFrame)
        camera.regs=bytearray(0x10000); camera.previous=None
        struct.pack_into('<I',camera.regs,0x34,1)
        with self.assertRaisesRegex(RuntimeError,'halted'): camera.read()
    def test_capture_error_rejected(self):
        camera=runtime.VdmaFullFrame.__new__(runtime.VdmaFullFrame)
        camera.regs=bytearray(0x10000); camera.previous=None
        struct.pack_into('<I',camera.regs,0x34,0x15090)
        with self.assertRaisesRegex(RuntimeError,'error'): camera.read()
    def test_normal_frame_irq_not_error(self):
        camera=runtime.VdmaFullFrame.__new__(runtime.VdmaFullFrame)
        camera.regs=bytearray(0x10000); camera.previous=0
        camera.capture=bytearray(camera.BYTES*3)
        struct.pack_into('<I',camera.regs,0x34,0x1000)
        struct.pack_into('<I',camera.regs,0x28,2<<24)
        good,frame=camera.read()
        self.assertTrue(good); self.assertEqual(frame.shape,(720,1280,3))
    def test_hardware_fingerprint_rejected(self):
        with patch.object(runtime.subprocess,'run') as query:
            query.return_value.stdout='{"kernels":[{"fingerprint":"0x1"}]}'
            with self.assertRaisesRegex(RuntimeError,'mismatch'): runtime.check_hardware_fingerprint()
    def test_hardware_fingerprint_accepted(self):
        with patch.object(runtime.subprocess,'run') as query:
            query.return_value.stdout='{"kernels":[{"fingerprint":"0x101000056010407"}]}'
            runtime.check_hardware_fingerprint()
    def test_invalid_input_rejected(self):
        model=runtime.DpuModel.__new__(runtime.DpuModel)
        with self.assertRaises(ValueError): model(np.zeros((1,3,144,256)))
        with self.assertRaises(ValueError): model(np.full((1,3,384,384),-1.))

if __name__=='__main__': unittest.main()
