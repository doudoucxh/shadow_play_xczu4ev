import hashlib,math,tempfile
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from hand_crossing_review import compare,relative_hand,review


def frame(name,wrist,neck=(0,-100),waist=(0,0)):
    return dict(camera='front',mirror_state=False,frame_id=name,neck_px=neck,waist_px=waist,
                hand_a_px=wrist,annotation_uncertainty_px=0,
                observation_quality={'hand_a_visible':True,'torso_projection_comparable':True})


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

    def test_hidden_wrist_cannot_be_guessed_into_a_crossing(self):
        before=frame('before',(-40,-110));after=frame('after',(40,-110))
        after['observation_quality']['hand_a_visible']=False
        result=compare(before,after,'hand_a')
        self.assertEqual(result['assessment_status'],'not_assessable')
        self.assertIsNone(result['after'])
        self.assertFalse(result['endpoint_side_change_candidate'])
        after['hand_a_px']=None
        self.assertFalse(compare(before,after,'hand_a')['endpoint_side_change_candidate'])

    def test_out_of_plane_body_turn_is_not_an_independent_hand_crossing(self):
        before=frame('before',(-40,-110));after=frame('after',(40,-110))
        after['observation_quality']['torso_projection_comparable']=False
        result=compare(before,after,'hand_a')
        self.assertFalse(result['endpoint_side_change_candidate'])
        self.assertIn('torso_projection_not_confirmed_comparable',result['ineligible_observations']['after'])

    def test_legacy_or_partial_annotations_require_new_visual_confirmation(self):
        before=frame('before',(-40,-110));after=frame('after',(40,-110))
        for quality in (None,{}, {'hand_a_visible':True}, {'torso_projection_comparable':True}):
            candidate=dict(after)
            if quality is None:candidate.pop('observation_quality')
            else:candidate['observation_quality']=quality
            self.assertEqual(compare(before,candidate,'hand_a')['assessment_status'],'not_assessable')
        after['observation_quality']['hand_a_visible']='true'
        with self.assertRaises(ValueError):compare(before,after,'hand_a')

    def test_image_review_preserves_missing_occluded_points_without_inventing_coordinates(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.png';Image.new('RGB',(10,10),'white').save(path)
            sample=dict(label='before',camera='front',mirror_state=False,frame_id='a',
                        image_file=str(path),image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        image_size=[10,10],neck_px=[4,4],waist_px=[4,8],hand_a_px=[1,4],hand_b_px=None,
                        head_outline_px=[[3,1],[5,1],[4,3]],annotation_uncertainty_px=0,
                        observation_quality={'hand_a_visible':True,'hand_b_visible':False,'torso_projection_comparable':True})
            after=dict(sample,label='after',frame_id='b',hand_a_px=None,
                       observation_quality={'hand_a_visible':False,'hand_b_visible':False,'torso_projection_comparable':False})
            result=review(dict(schema_version=1,coordinate_system='image_pixels_x_right_y_down',
                               landmarks_are_verified_anatomical_joints=False,samples=[sample,after]))
            self.assertEqual(result['schema_version'],2)
            self.assertEqual(result['samples'][1]['hand_a']['assessment_status'],'not_assessable')
            self.assertIsNone(result['samples'][1]['hand_a']['measurement'])
            self.assertTrue(all(not h['endpoint_side_change_candidate'] for h in result['comparisons'][0]['hands']))

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
