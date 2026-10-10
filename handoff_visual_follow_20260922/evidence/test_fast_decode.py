import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'yolo_deploy_stage'/'runtime'))
from postprocess import decode
from fast_decode import decode_int8

class Tests(unittest.TestCase):
    def test_reference_equivalence(self):
        for seed in range(24):
            rng = np.random.default_rng(seed)
            raw, fixes = [], []
            for n in (48,24,12):
                for channels, fix in ((64,3),(1,2),(27,3)):
                    v = rng.integers(-128,128,(1,n,n,channels),dtype=np.int8)
                    if channels == 1 and seed < 20:
                        v.fill(-128)
                        for _ in range(seed):
                            v[0,rng.integers(n),rng.integers(n),0] = rng.integers(-6,15)
                    raw.append(v)
                    fixes.append(fix)
            floating = [(v.astype(np.float32)*2.**-f).transpose(0,3,1,2) for v,f in zip(raw,fixes)]
            args = ((.3,0,84,1280,720),)
            for conf in (.25,.5):
                expected = decode(floating,*args,conf=conf)
                actual = decode_int8(raw,fixes,*args,conf=conf)
                for e,a in zip(expected,actual):
                    np.testing.assert_allclose(a,e,rtol=1e-6,atol=1e-4,err_msg=f'seed={seed}, conf={conf}')

if __name__ == '__main__':
    unittest.main()
