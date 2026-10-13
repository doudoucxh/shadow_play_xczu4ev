import math
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from hand_crossing_review import compare,relative_hand


def frame(name,wrist,neck=(0,-100),waist=(0,0)):
    return dict(camera='front',mirror_state=False,frame_id=name,neck_px=neck,waist_px=waist,
                hand_a_px=wrist,annotation_uncertainty_px=0)


class CrossingReviewTests(unittest.TestCase):
    def test_rigid_translation_and_rotation_do_not_become_hand_crossing(self):
        original=frame('before',(-40,-110))
        def transform(p):
            angle=.8
            return (p[0]*math.cos(angle)-p[1]*math.sin(angle)+170,
                    p[0]*math.sin(angle)+p[1]*math.cos(angle)+90)
        after=frame('after',transform(original['hand_a_px']),transform(original['neck_px']),transform(original['waist_px']))
        result=compare(original,after,'hand_a')
        self.assertAlmostEqual(result['before']['transverse_offset_px'],result['after']['transverse_offset_px'])
        self.assertFalse(result['endpoint_side_change_candidate'])

    def test_actual_endpoint_crossing_is_only_a_candidate_not_route_authorization(self):
        result=compare(frame('before',(-40,-110)),frame('after',(40,-110)),'hand_a')
        self.assertTrue(result['endpoint_side_change_candidate'])
        self.assertFalse(result['complete_crossing_verified'])
        self.assertFalse(result['automatic_motion_allowed'])

    def test_uniform_image_scale_preserves_relative_side_and_normalized_offset(self):
        a=relative_hand((0,-100),(0,0),(-40,-110))
        b=relative_hand((0,-170),(0,0),(-68,-187))
        self.assertEqual(a['side'],b['side'])
        self.assertAlmostEqual(a['transverse_offset_in_torso_axis_lengths'],b['transverse_offset_in_torso_axis_lengths'])

    def test_uncertainty_near_midline_prevents_false_side_claim(self):
        result=relative_hand((0,-100),(0,0),(2,-110),4)
        self.assertEqual(result['side'],'uncertain')
        self.assertLess(result['transverse_interval_px'][0],0)
        self.assertGreater(result['transverse_interval_px'][1],0)

    def test_head_clearance_checks_whole_outline_not_head_center(self):
        outline=[[-10,-130],[10,-130],[10,-110],[-10,-110]]
        below=relative_hand((0,-100),(0,0),(30,-120),0,outline)
        above=relative_hand((0,-100),(0,0),(30,-150),0,outline)
        self.assertFalse(below['wrist_above_entire_supplied_head_outline'])
        self.assertTrue(above['wrist_above_entire_supplied_head_outline'])
        self.assertFalse(above['whole_arm_weapon_and_rod_clearance_verified'])

    def test_degenerate_and_changed_camera_conventions_are_rejected(self):
        for neck,waist,error in (((0,0),(0,0),0),((0,-3),(0,0),2)):
            with self.assertRaises(ValueError):relative_hand(neck,waist,(40,0),error)
        a=frame('before',(-40,-110));b=frame('after',(40,-110))
        for key,value in (('camera','other'),('mirror_state',True),('frame_id','before')):
            invalid=dict(b);invalid[key]=value
            with self.assertRaises(ValueError):compare(a,invalid,'hand_a')


if __name__=='__main__':unittest.main()
