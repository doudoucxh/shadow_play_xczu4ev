"""Offline V20 candidate arithmetic. No device, serial or playback interfaces."""
import bisect
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from initial_pose_model import validate_pulses

ROD_CHANNELS={'WH':[3,4],'WL':[1,2],'WR':[5,6],'TH':[7,8],'TT':[9,10]}
MIDPOINT=[1500]*10
TIGER_MASK=960


def historical_pose(record,edge,source):
    """Extract a recorded tiger target, never a screen-coordinate inverse."""
    matches=[row for row in record['events'] if row.get('event')=='probe_complete' and row.get('axis')==edge]
    if len(matches)!=1:raise ValueError('Expected one historical target at this edge')
    row=matches[0];state=row['state']
    if state['enabled_mask']!=TIGER_MASK or not state['armed'] or state['pending'] or state['faults']:
        raise ValueError('Historical target lacks a clean adopted output')
    pulses=MIDPOINT[:6]+state['pulse_us'][6:]
    validate_pulses(pulses)
    return dict(pulse_us=pulses,source=dict(source,event='probe_complete',edge=edge,sequence=state['sequence']),
                current_assembly_verified=False)


def make_a01_candidate(poses):
    # All endpoints below are copied from adopted 2026-10-12 map A/B records.
    # The new timing/order/assembly and person-midpoint context are untested.
    keys=[(0.,'midpoint','巡视起点'),(.70,'head_yaw','小幅侧转候选'),
          (1.4333106576,'head_lift','抬头进入虎啸'),
          (2.10,'both_lift','虎头尾联动上提候选'),
          (2.70,'both_lift','虎啸短停'),(3.4333106576,'midpoint','回落进入扭动'),
          (4.30,'both_yaw','头尾同向横转候选'),(5.30,'midpoint','收回'),
          (6.30,'midpoint','末姿保持')]
    frames=[dict(time_s=t,pose=key,label=label,pulse_us=poses[key]['pulse_us'][:]) for t,key,label in keys]
    return dict(schema='v20-a01-offline-candidate-v1',id='A01',title='老虎吼叫与扭动',
        status='historical_targets_new_timing_not_executed',motor_ready=False,automatic_replay_allowed=False,
        source_audio_range_s=[2.7,9.],duration_s=6.3,enabled_mask=TIGER_MASK,
        reference_pulse_us=MIDPOINT[:],interpolation='cosine_zero_velocity_at_keyframes',
        keyframes=frames,maximum_adjacent_step_us=3,
        endpoint_source='Recorded tiger map A/B adopted targets; no visual-coordinate-to-PWM conversion',
        still_unverified=['当前装配下的方向、鱼线张力与杆件避让','中位到各目标及新顺序的完整路径',
                          'V20五连接点轨迹匹配','真实音效命中时间与播放/机构延迟'],
        end_behavior='Hold final scheduled midpoint target; no extra recenter after audio',
        execution_binding=None)


def make_direction_checks(poses):
    keys=['head_yaw','head_lift','tail_yaw','tail_lift','both_yaw','both_lift']
    instructions=['观察虎头横转方向和人物侧余量','观察虎头是否上提及耳部悬线',
                  '观察尾端横向方向及虎身扭动','观察尾端是否上提及悬线张力',
                  '观察头尾共同横转，不以轨移动代替','观察虎头尾联动上提及两端间距']
    result=[]
    for key,instruction in zip(keys,instructions):
        result.append(dict(id=key,title=instruction,motor_ready=False,reviewed=False,
            observer_note=None,keyframes=[dict(time_s=0.,pulse_us=MIDPOINT[:]),
            dict(time_s=2.,pulse_us=poses[key]['pulse_us'][:]),
            dict(time_s=3.,pulse_us=poses[key]['pulse_us'][:]),
            dict(time_s=5.,pulse_us=MIDPOINT[:]),dict(time_s=6.,pulse_us=MIDPOINT[:])],
            duration_s=6.,enabled_mask=TIGER_MASK,maximum_adjacent_step_us=1,
            end_behavior='Stop for onsite review after this isolated check; no automatic next check'))
    return result


def validate_candidate(candidate):
    if candidate.get('motor_ready') is not False or candidate.get('enabled_mask')!=TIGER_MASK:
        raise ValueError('Only offline tiger candidates are supported')
    keys=candidate['keyframes'];duration=candidate['duration_s']
    if len(keys)<2 or keys[0]['time_s']!=0 or keys[-1]['time_s']!=duration:
        raise ValueError('Complete zero-to-end keyframes required')
    if not math.isfinite(duration) or not 0<duration<=60:raise ValueError('Invalid candidate duration')
    last=-1
    for key in keys:
        t=key['time_s']
        if not math.isfinite(t) or t<=last:raise ValueError('Keyframes must strictly increase')
        pulses=validate_pulses(key['pulse_us'])
        if pulses[:6]!=MIDPOINT[:6] or any(abs(v-1500)>40 for v in pulses[6:]):
            raise ValueError('Outside the recorded tiger-target preparation envelope')
        last=t
    return candidate


def sample(candidate,source_local_time):
    validate_candidate(candidate)
    if not math.isfinite(source_local_time):raise ValueError('Finite time required')
    keys=candidate['keyframes'];times=[key['time_s'] for key in keys]
    if source_local_time<=0:return keys[0]['pulse_us'][:]
    if source_local_time>=times[-1]:return keys[-1]['pulse_us'][:]
    i=bisect.bisect_right(times,source_local_time)-1;a,b=keys[i:i+2]
    u=.5-.5*math.cos(math.pi*(source_local_time-a['time_s'])/(b['time_s']-a['time_s']))
    return [int(math.floor(x+(y-x)*u+.5)) for x,y in zip(a['pulse_us'],b['pulse_us'])]


def compile_frames(candidate,speed=1.,hz=50):
    """Export inspection data only. No live timing, ARM, leases or hardware I/O."""
    validate_candidate(candidate)
    if type(speed) not in (int,float) or not math.isfinite(speed) or not .05<=speed<=1:
        raise ValueError('Preparation speed must be 0.05..1')
    if hz!=50 or type(hz) is not int:raise ValueError('Only 50 Hz preparation samples')
    duration=candidate['duration_s']/speed
    count=round(duration*hz)
    if abs(count/hz-duration)>1e-8:raise ValueError('Duration must align to the inspection clock')
    rows=[];source_start=candidate.get('source_audio_range_s',[0])[0]
    for index in range(count+1):
        local=index/hz;source_local=min(candidate['duration_s'],local*speed)
        rows.append(dict(time_s=local,source_time_s=source_start+source_local,
                         pulse_us=sample(candidate,source_local),enabled_mask=TIGER_MASK))
    peak=max(abs(x-y) for a,b in zip(rows,rows[1:]) for x,y in zip(a['pulse_us'],b['pulse_us']))
    if peak>candidate['maximum_adjacent_step_us']:raise ValueError('Candidate sampling exceeds its step bound')
    return dict(status='offline_inspection_data_not_a_hardware_plan',motor_ready=False,
                speed=speed,sampling_hz=hz,duration_s=duration,frames=rows,peak_step_us=peak,
                sound_preview_allowed=bool(speed==1 and 'source_audio_range_s' in candidate),execution_binding=None)


def proposed_runtime_gate(candidate,checkpoint):
    """Always report preparation gaps; nothing in this module authorizes motion."""
    reasons=['Preparation tool has no hardware transport']
    state=checkpoint['board']
    if not (state.get('armed') is False and state.get('enabled_mask')==0 and state.get('pending') is False):
        reasons.append('Live output ownership must be reviewed')
    if candidate.get('motor_ready') is not True:reasons.append('Current assembly and loaded route not reviewed')
    if candidate.get('execution_binding') is None:reasons.append('No fresh boot/sequence one-use execution binding')
    return dict(execution_available=False,reasons=reasons,
                initial_reference='Operator-confirmed midpoint, not measured shaft feedback',
                camera_required=False,onsite_review_required=True)
