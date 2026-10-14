"""Offline review of hand side changes relative to a puppet's torso.

Input landmarks are manually supplied image observations, not encoder feedback.
This module has no motor, serial, network, or device-file backend. Endpoint side
changes never certify the intermediate arm/weapon/rod path or authorize motion.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def point(value):
    if (not isinstance(value,(list,tuple)) or len(value)!=2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in value)):
        raise ValueError('Two finite image coordinates required')
    return tuple(float(v) for v in value)


def relative_hand(neck,waist,wrist,uncertainty_px=0,head_outline=None):
    """Signed transverse distance: negative/positive are torso-relative sides.

    Each supplied coordinate has an absolute component error <= uncertainty_px.
    The distance interval includes wrist/neck error and torso-axis uncertainty;
    it is a mathematical bound conditional on that annotation error assumption.
    """
    neck,waist,wrist=map(point,(neck,waist,wrist))
    if (type(uncertainty_px) not in (int,float) or not math.isfinite(uncertainty_px)
            or uncertainty_px<0):raise ValueError('Finite nonnegative annotation uncertainty required')
    vx,vy=neck[0]-waist[0],neck[1]-waist[1];length=math.hypot(vx,vy)
    error=2*math.sqrt(2)*uncertainty_px
    if not math.isfinite(length) or not math.isfinite(error) or length<=max(error,1e-9):
        raise ValueError('Torso direction is degenerate or too uncertain')
    ux,uy=vx/length,vy/length;rx,ry=-uy,ux
    bx,by=wrist[0]-neck[0],wrist[1]-neck[1]
    if not math.isfinite(math.hypot(bx,by)):raise ValueError('Image distances must remain finite')
    direction_error=2*math.sin(math.asin(error/length)/2)
    offset=bx*rx+by*ry;bound=error+math.hypot(bx,by)*direction_error
    low,high=offset-bound,offset+bound
    side='negative' if high<0 else ('positive' if low>0 else 'uncertain')
    result={'transverse_offset_px':offset,'transverse_interval_px':[low,high],
            'transverse_offset_in_torso_axis_lengths':offset/length,
            'upward_offset_px':bx*ux+by*uy,'torso_axis_length_px':length,'side':side,
            'whole_arm_weapon_and_rod_clearance_verified':False}
    if head_outline is not None:
        if not isinstance(head_outline,list) or len(head_outline)<3:
            raise ValueError('Head and headdress outline needs at least three points')
        outline=[point(p) for p in head_outline]
        gaps=[(wrist[0]-x)*ux+(wrist[1]-y)*uy for x,y in outline]
        distance=max(math.hypot(wrist[0]-x,wrist[1]-y) for x,y in outline)
        head_error=error+distance*direction_error
        interval=[min(gaps)-head_error,min(gaps)+head_error]
        result.update(wrist_above_head_interval_px=interval,
                      wrist_above_entire_supplied_head_outline=interval[0]>0)
    return result


def compare(before,after,hand):
    if (before['camera']!=after['camera'] or before['mirror_state']!=after['mirror_state']
            or before['frame_id']==after['frame_id']):
        raise ValueError('Distinct frames with the same camera and mirror convention required')
    a,b=map(lambda f:assess_observation(f,hand),(before,after))
    eligible=a['assessment_status']==b['assessment_status']=='assessable'
    ma,mb=a['measurement'],b['measurement']
    return {'hand':hand,'before':ma,'after':mb,
            'assessment_status':'assessable' if eligible else 'not_assessable',
            'ineligible_observations':{name:r['reasons'] for name,r in (('before',a),('after',b)) if r['reasons']},
            'endpoint_side_change_candidate':bool(eligible and ma['side']!='uncertain' and mb['side']!='uncertain' and ma['side']!=mb['side']),
            'complete_crossing_verified':False,'automatic_motion_allowed':False}


def assess_observation(frame,hand):
    """Require explicit visual review; an estimated hidden wrist is not evidence.

    A torso-relative 2D axis removes in-plane motion, but cannot remove torso
    rotation out of the image plane. These flags are reviewer declarations,
    not automatic visibility detection or a measured confidence score.
    """
    if hand not in ('hand_a','hand_b'):raise ValueError('Known physical hand required')
    quality=frame.get('observation_quality',{})
    if not isinstance(quality,dict):raise ValueError('Observation quality must be an object')
    visible=quality.get(hand+'_visible')
    comparable=quality.get('torso_projection_comparable')
    if any(v is not None and type(v) is not bool for v in (visible,comparable)):
        raise ValueError('Visibility and torso comparability declarations must be boolean')
    reasons=[]
    if visible is not True:reasons.append('hand_visibility_not_confirmed')
    if comparable is not True:reasons.append('torso_projection_not_confirmed_comparable')
    if frame.get(hand+'_px') is None:reasons.append('no_observed_hand_point')
    measurement=None
    if not reasons:
        measurement=relative_hand(frame['neck_px'],frame['waist_px'],frame[hand+'_px'],
                                  frame['annotation_uncertainty_px'],frame.get('head_outline_px'))
    return {'assessment_status':'not_assessable' if reasons else 'assessable',
            'reasons':reasons,'measurement':measurement}


def review(spec):
    from PIL import Image
    if (spec.get('schema_version')!=1 or spec.get('coordinate_system')!='image_pixels_x_right_y_down'
            or spec.get('landmarks_are_verified_anatomical_joints') is not False):
        raise ValueError('Explicit offline image-observation schema required')
    samples=spec['samples'];measures=[]
    if len(samples)<2:raise ValueError('At least two observations required')
    for s in samples:
        raw=Path(s['image_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=s['image_sha256']:raise ValueError('Referenced frame changed')
        with Image.open(s['image_file']) as im:
            im.load();size=list(im.size)
        if size!=s['image_size']:raise ValueError('Image coordinate convention changed')
        landmarks=[s[k] for k in ('neck_px','waist_px')]+[s[k] for k in ('hand_a_px','hand_b_px') if s.get(k) is not None]+s['head_outline_px']
        if any(not (0<=x<size[0] and 0<=y<size[1]) for x,y in map(point,landmarks)):
            raise ValueError('Landmarks must lie inside their referenced image')
        measures.append({'label':s['label'],'frame_id':s['frame_id'],
                         'hand_a':assess_observation(s,'hand_a'),
                         'hand_b':assess_observation(s,'hand_b')})
    comparisons=[{'before_label':a['label'],'after_label':b['label'],
                  'hands':[compare(a,b,h) for h in ('hand_a','hand_b')]} for a,b in zip(samples,samples[1:])]
    return {'schema_version':2,'input_schema_version':spec['schema_version'],
            'method':'Explicitly visible, comparable torso projections followed by conditional 2D annotation-error bounds',
            'manual_image_estimates':True,'metric_coordinates_calibrated':False,'actual_angle_feedback':None,
            'visibility_and_torso_comparability_are_reviewer_declarations':True,
            'automatic_motion_allowed':False,'complete_crossing_verified':False,
            'samples':measures,'comparisons':comparisons}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('observations',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=review(json.loads(a.observations.read_text(encoding='utf-8-sig')))
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'observations':len(result['samples']),'complete_crossing_verified':False,'automatic_motion_allowed':False}))


if __name__=='__main__':main()
