from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_body_linkage import rigid_match


class BodyAppearanceTests(unittest.TestCase):
    def test_rotation_translation_survive_exposure_change(self):
        before=np.full((120,120),80,dtype=np.uint8)
        before[46:75,53:68]=np.random.default_rng(10).integers(40,170,(29,15),dtype=np.uint8)
        rotated=Image.fromarray(before).rotate(15,resample=Image.Resampling.BILINEAR,center=(60,60),fillcolor=80)
        shifted=Image.new('L',(120,120),80);shifted.paste(rotated,(4,-2))
        after=np.asarray(shifted,dtype=float)*1.2+20
        result=rigid_match(before,after.astype(np.uint8),center=(60,60),search=12)
        self.assertEqual(result['rotation_ccw_deg'],15)
        self.assertEqual((result['dx'],result['dy']),(4,-2))
        self.assertTrue(result['usable_texture_match'])

    def test_flat_texture_and_image_edge_are_rejected(self):
        flat=np.full((120,120),80,dtype=np.uint8)
        with self.assertRaises(ValueError):rigid_match(flat,flat,center=(60,60),search=12)
        with self.assertRaises(ValueError):rigid_match(flat,flat,center=(8,8),search=12)


if __name__=='__main__':unittest.main()
