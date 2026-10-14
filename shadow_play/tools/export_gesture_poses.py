"""Export observations for scene planning; contains no hardware control code."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

POINTS=('hand_a_attachment','head_attachment','hand_b_attachment','tiger_head_attachment','tiger_foot_attachment')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def export(result_path,session,annotations_path=None):
    result=json.loads(result_path.read_text(encoding='utf-8-sig'))
    pose_count=result.get('expected_pose_count',7)
    if type(pose_count) is not int or not 7<=pose_count<=64:raise ValueError('Invalid expected pose count')
    annotations=json.loads(annotations_path.read_text(encoding='utf-8-sig')) if annotations_path else {}
    if set(annotations)-{str(i) for i in range(pose_count)}:
        raise ValueError('Unknown annotation stage')
    if any(set(value)-{'front','top'} for value in annotations.values()):
        raise ValueError('Unknown annotation camera')
    continuous=result['status']=='completed_operator_attended_trial'
    if result['status'] not in ('closed_attended_gesture_probe','completed_operator_attended_trial') or not result['normal_frame_stop']:
        raise ValueError('Only completed, normally stopped diagnostics may be exported')
    final=result['final_state']
    if final['enabled_mask'] or final['armed'] or final['pending'] or final['faults']:
        raise ValueError('Final state must be OFF without faults')
    raw=session/'full_board_motion.jsonl'
    if sha(raw)!=result['full_board_log_sha256']:
        raise ValueError('Board log does not match the result')
    events=[json.loads(line) for line in raw.read_bytes().splitlines()]
    acknowledged={r['axis'] for r in events if r['event']=='path_reviewed'}
    continuous_selection=None
    if continuous:
        if (sum(r['event']=='operator_trial_started' for r in events)!=1
                or sum(r['event']=='operator_trial_complete' for r in events)!=1
                or [r['axis'] for r in events if r['event']=='probe_complete']!=list(range(1,pose_count))
                or events[-1].get('event')!='outputs_off' or not events[-1].get('normal_frame_stop')
                or events[-1]['state']!=final or events[0]['state']['pulse_us']!=final['pulse_us']):
            raise ValueError('Continuous trial must complete all declared edges and close at its reference')
        review=session/'continuous_selection.json'
        if sha(review)!=result['continuous_selection_sha256']:raise ValueError('Continuous camera selection was changed')
        continuous_selection=json.loads(review.read_text())
        if set(continuous_selection)!=set(str(i) for i in range(pose_count)):
            raise ValueError('Every declared trial snapshot required')
    elif pose_count!=7:raise ValueError('Variable stage count is only supported for continuous trials')
    elif acknowledged!=set(range(1,7)):
        witness=result.get('post_stop_closure_review',{})
        if (acknowledged!=set(range(1,6)) or witness.get('event')!='post_stop_closure_review'
                or witness.get('reviewed_stage')!=6 or witness.get('source_log_sha256')!=result['full_board_log_sha256']
                or witness.get('state')!=final or witness.get('fresh_dual_view_reviewed') is not True
                or [r['axis'] for r in events if r['event']=='probe_complete']!=list(range(1,pose_count))):
            raise ValueError('Six reviewed stages or a bound final closure review are required')
    poses=[]
    for stage in range(pose_count):
        if continuous:selection={'views':continuous_selection[str(stage)]}
        else:
            review=session/f'review-{max(1,stage)}'/'selection.json'
            selection=json.loads(review.read_text())
            expected=next(r['selection_sha256'] for r in result['visual_reviews'] if r['stage']==max(1,stage))
            if sha(review)!=expected:raise ValueError('Camera selection was changed')
        event=next(r for r in events if (r['event']=='reference_held' if stage==0 else r['event']=='probe_complete' and r['axis']==stage))
        state=event['state'];pulse=state['pulse_us']
        if len(pulse)!=10 or any(type(v) is not int for v in pulse):raise ValueError('Ten command coordinates required')
        views={}
        for camera,selected in selection['views'].items():
            frame=selected if continuous else selected[0 if stage==0 else 1];path=session/frame['file']
            with Image.open(path) as im:im.load();width,height=im.size
            manual=annotations.get(str(stage),{}).get(camera,{})
            if set(manual)-set(POINTS):raise ValueError('Unknown attachment identifier')
            points={}
            for name in POINTS:
                xy=manual.get(name)
                if xy is not None and (not isinstance(xy,list) or len(xy)!=2 or
                    any(type(v) not in (int,float) or not math.isfinite(v) for v in xy) or
                    not (0<=xy[0]<width and 0<=xy[1]<height)):
                    raise ValueError('Invalid pixel annotation')
                points[name]={'pixel_xy':xy,'millimeter_xy':None,
                              'method':'manual_approximate_attachment_location' if xy is not None else 'not_measured',
                              'validated_error_mm':None}
            views[camera]={'frame_id':frame['frame_id'],'host_unix_ns':frame['host_unix_ns'],
                           'jpeg_sha256':sha(path),'image_size_px':[width,height],'points':points}
        poses.append({'stage':stage,'command_sequence':state['sequence'],'command_pulse_us':pulse,
                      'controller_visual_review_acknowledged':stage in acknowledged if stage else None,
                      'snapshot_timing':'during_continuous_motion_not_a_settled_pose' if continuous else 'separate_before_and_settled_review',
                      'actual_shaft_angles_deg':None,'board_monotonic_seconds':event['board_monotonic_seconds'],
                      'views':views})
    return {'schema_version':1,'action_id':result['session_id'],'profile':result['plan']['profile'],
            'status':'executed_attended_trial_not_an_approved_replay' if continuous else 'executed_diagnostic_not_a_completed_crossing','result_file':result_path.name,
            'result_sha256':sha(result_path),'boot_id':result['plan']['boot_id'],
            'coordinate_convention':{'pixel_origin':'raw_image_top_left','x_direction':'right','y_direction':'down',
                'servo_coordinates':'command_pulse_us_ordered_servo_1_to_10','millimeter_transform':None,
                'manual_points_are_approximate':True,'null_point_means_not_measured':True},
            'servo_pins':['D14','D15','F13','G13','G14','G15','J14','E13','E14','E15'],
            'poses':poses,'visual_findings':result['visual_findings'],
            'diagnostic_execution_completed':True,'automatic_replay_allowed':False,'overhead_crossing_completed':False,
            'post_stop_closure_review':result.get('post_stop_closure_review'),
            'reported_anomaly':result.get('reported_anomaly'),
            'reuse_requirements':['unchanged mechanical connections and reference verified',
                                 'same camera framing or new image calibration',
                                 'current attended authorization and unchanged incident locks'],
            'final_state':final}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--result',required=True,type=Path);p.add_argument('--session',required=True,type=Path)
    p.add_argument('--annotations',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();record=export(a.result,a.session,a.annotations)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(a.output.resolve()),'poses':len(record['poses']),
                      'annotated_points':sum(v['pixel_xy'] is not None for r in record['poses'] for c in r['views'].values() for v in c['points'].values())}))

if __name__=='__main__':main()
