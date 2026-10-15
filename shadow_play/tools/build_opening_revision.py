"""Offline task-space choreography. No PWM inverse model or hardware transport."""
import bisect
import argparse
import copy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'planning/wusong_complete_20261014'

# Artistic task-space candidate only; neither shoulder geometry nor PWM inverse.
HIP_ARC = dict(start_s=16.8, end_s=17.4, center=[-.22,.87], radius=.75,
               start_angle_rad=math.atan2(-.45,-.60), end_angle_rad=-math.pi/2)


def hip_arc_point(t):
    u=max(0,min(1,(t-HIP_ARC['start_s'])/(HIP_ARC['end_s']-HIP_ARC['start_s'])))
    u=u*u*u*(10+u*(-15+6*u))
    a=HIP_ARC['start_angle_rad']+(HIP_ARC['end_angle_rad']-HIP_ARC['start_angle_rad'])*u
    return [HIP_ARC['center'][0]+HIP_ARC['radius']*math.cos(a),
            HIP_ARC['center'][1]+HIP_ARC['radius']*math.sin(a)]


def keyframes():
    rows = []
    def put(t, lift, left, right, action):
        rows.append(dict(time_s=t, action=action, body_lift=lift,
                         head=[0, 1 + lift],
                         left_hand=[left[0], left[1] + lift],
                         right_hand=[right[0], right[1] + lift]))
    low_l, low_r = (-.28, .22), (.28, .22)
    hip = (-.22, .12)
    put(10, 0, low_l, low_r, '低手亮相，头在躯干上方')
    # A readable rise / plant / rebound, with unequal steps rather than vibration.
    for start, period, height in [(10.8,1.35,.12),(12.15,1.45,.16),(13.6,1.5,.10)]:
        put(start,0,low_l,low_r,'山路落步')
        put(start+period*.42,height,(-.35,.30),(.35,.18),'抬身迈步；双手随身')
        put(start+period*.78,0,(-.24,.20),(.26,.31),'落步回到基准')
        put(start+period,0,low_l,low_r,'落步回弹')
    put(16,0,(-.25,.28),(.28,.35),'减速停步、环顾')
    put(16.8,0,hip_arc_point(16.8),(.30,.45),'左手向外伸展，使手臂先展开；不是拉身体')
    for t in (16.9,17.0,17.1,17.2,17.3):
        put(t,0,hip_arc_point(t),(.30,.45),'左手连续快速圆弧收腰，途中不停顿，观察肘部外拱')
    put(17.4,0,hip,(.30,.45),'手到腰侧，圆弧末端减速；确认肘外拱再保持')
    put(17.6,.03,hip,(.55,.90),'挺身起语，左肘外展')
    for up, down, reach, height in [(18.15,18.65,.72,1.18),
                                  (19.6,20.15,.80,1.28),
                                  (21.15,21.85,.74,1.20)]:
        put(up,.04,hip,(reach,height),'右上指点重音；左手叉腰目标')
        put(down,.01,hip,(.47,.76),'右手短收，左手留腰侧')
    put(22.5,0,hip,(.32,.48),'对白收势；保留傲然姿态')
    put(23,0,low_l,low_r,'松开叉腰，重新迈步')
    for start, period, height in [(23.2,1.1,.14),(24.3,1.2,.18),
                                  (25.5,1.15,.15),(26.65,1.15,.10)]:
        put(start,0,low_l,low_r,'山路落步')
        put(start+period*.40,height,(-.35,.31),(.36,.18),'迈步上提；三点同向跟身')
        put(start+period*.76,0,(-.24,.18),(.27,.32),'落步吸收，双手换摆')
        put(start+period,0,low_l,low_r,'回弹')
    put(28.4,.02,(-.30,.64),(.36,.70),'察觉虎动，双手收护')
    put(29,0,(-.30,.70),(.38,.76),'停步迎接扑虎；后段衔接待实测')
    # Shared stride boundary: one target, not two zero-duration edges.
    return list({round(r['time_s'],8):r for r in sorted(rows,key=lambda r:r['time_s'])}.values())


def sample(rows, t):
    t = max(rows[0]['time_s'], min(t, rows[-1]['time_s']))
    i = min(bisect.bisect_right([r['time_s'] for r in rows],t)-1,len(rows)-2)
    a,b=rows[i:i+2]
    x=(t-a['time_s'])/(b['time_s']-a['time_s'])
    u=x*x*x*(10+x*(-15+6*x))
    result={k:[p+(q-p)*u for p,q in zip(a[k],b[k])]
            for k in ('head','left_hand','right_hand')}
    if HIP_ARC['start_s']<=t<=HIP_ARC['end_s']:
        result['left_hand']=hip_arc_point(t)
    return result


def build(base, observed, component_result=None, extension_result=None, application_results=()):
    rows=keyframes()
    revision=dict(schema='opening_task_space_v4',status='planned_not_executed',
        motor_ready=False,automatic_replay_allowed=False,
        audio=copy.deepcopy(base['audio']),
        coordinate_frame=dict(x='Sony右为正',y='向上为正',origin='人物骨盆中点',
            unit='计划中的骨盆至头部控制点距离=1；不是像素、毫米或舵机角度',
            purpose='艺术目标，用于后续姿态采样，不是PWM逆解'),
        hand_assignment=dict(left=dict(servos=[1,2],role='叉腰'),
                             right=dict(servos=[5,6],role='向Sony右上方指点'),
                             verification='沿用项目人物左右手编号；实测时核对轮廓与持械关系'),
        head_reference=dict(source='../../config/person_head_centering_fine_result.20261015.json',
            last_command_us=observed['final_state']['pulse_us'],
            last_stop_sequence=observed['final_state']['sequence'],
            meaning='L静态居中观察基准，不是新的全场动作标定',
            startup_command=None,actual_angle_feedback=None,cloth_gap_verified=False),
        dialogue=dict(window_s=[17,23],detected_voice_window_s=[17.5,22.9],
            intended_phrase='酒家吓人',exact_word_timing_s=None,
            accent_times_s=[18.15,19.6,21.15],
            timing_status='编舞候选重音；不是逐词听审结果'),
        keyframes=rows,servo_keyframes_us=None,
        hip_entry=dict(status='planned_not_executed',
            correction='M直接内收不是叉腰；先伸展，再快速圆弧收腰使肘外拱',
            phases=['16.0–16.8 向外伸展','16.8–17.4 连续圆弧收腰','17.4–17.6 减速定势'],
            arc=HIP_ARC, interpolation='analytic_circle_quintic_time_no_interior_stops',
            duration_status='候选节奏，尚非实机验证速度',
            fixed_during_arc=['head','right_hand'],
            elbow_control='被动关节；腕点圆弧不能保证肘部翻向，必须观察',
            pwm_route=None, evidence='../../config/person_opening_m_result.20261015.json'),
        component_command_candidates=dict(status='offline_unexecuted_not_inverse_solution',
            note='独立试姿候选，不绑定上方时间轴；组合与叉腰/指点效果均未实测',
            head_yaw_fixed_us=1565,
            poses=[dict(id=name,person_us=q,executed=False) for name,q in [
                ('left_hand_inward_prepare',[1510,1212,1565,1554,1416,1740]),
                ('right_hand_raise_prepare',[1510,1212,1565,1554,1460,1660]),
                ('right_hand_point_candidate',[1510,1212,1565,1554,1500,1580]),
                ('hill_step_rise_candidate',[1470,1252,1565,1534,1416,1700])]],
            sources=['../../config/hand_a_low_yaw_recheck_result.20261014.json',
                     '../../integrations/calibration/duel_interaction_trial.py'],
            limitations=['1号增加曾使低位手向内，未证明腕已在腰侧',
                         '右手候选借用旧分量，Sony右上方向及组合须重看',
                         '2号下点维持1212，不再往名义下限压；以上抬再回落表现落步']),
        slide_rail=dict(enabled=False,step_landings_s=[10.8,12.15,13.6,23.2,24.3,25.5,26.65],
                        distance_mm=None,speed_mm_s=None,commands=None,
                        future_sync='抬身阶段推进，落步阶段减速；当前只原地表现走山路'),
        acceptance=['头颈保持躯干上方，不随手势偏到一侧',
                    '左腕靠近腰侧且肘弯曲，不能用拉紧悬挂代替叉腰',
                    '右腕向右上连续三次指点，强弱有别且短收',
                    '走山路三杆共同起落，双手保持相对身体余量',
                    '不得把腰被双手固定后仅头杆上下拉动当作迈步',
                    '贴幕间隙另行观察，二维位置居中不代表深度已修正'],
        continuation=dict(after_s=29,reference='interaction_revision_v3.json',
            old_motor_route_unchanged=True,automatic_splice=False,
            requirement='逐段核对头部居中及三杆联动后才生成完整新PWM路线；不全局加140μs'))
    if component_result is not None:
        c=revision['component_command_candidates']
        c['status']='partial_experiment_M; hip_rejected; rise_not_executed'
        c['note']='M已执行前三种手部指令；叉腰未通过，右手抬举可见；身体起伏未执行。不是新圆弧路线。'
        c['execution_evidence']='../../config/person_opening_m_result.20261015.json'
        executed=[s['state']['pulse_us'][:6] for s in component_result['stages']]
        for p in c['poses']:
            p['executed']=p['person_us'] in executed
        revision['latest_observed_command_state']=component_result['final_state']
        revision['latest_observed_command_state_note']='M停止指令，非实际轴角；不自动重启'
    if extension_result is not None:
        revision['latest_observed_command_state']=extension_result['final_state']
        revision['latest_observed_command_state_note']='N正常停止指令，非实际轴角；不自动重启'
        revision['hip_entry']['extension_trial']=dict(
            evidence='../../config/person_hip_extension_n_result.20261015.json',
            status='extension_and_return_executed; full_arc_not_executed',
            observation='手臂向外展开；身体也随动，固定头部指令不代表身体固定')
    if application_results:
        revision['hip_entry']['application_trials']=[dict(session=r['session'],status=r['status'],
            final_sequence=r['final_state']['sequence'],automatic_replay_allowed=False) for r in application_results]
        revision['hip_entry']['status']='partial_trials_executed_hip_not_achieved'
        revision['hip_entry']['remaining']='横向靠腰与贴幕需组合修正；不能单纯继续抬身'
        revision['latest_observed_command_state']=application_results[-1]['final_state']
        revision['latest_observed_command_state_note']='P第二档后正常停止；已非L/N基准，不自动启用旧剧本'
    score=copy.deepcopy(base)
    score['title']='武松打虎 · 开场叉腰指点与山路步态 v4（编排预览）'
    score['latest_revision']='opening_revision_v4.json'
    score['motor_ready']=False
    score['automatic_replay_allowed']=False
    edits={
        'S06':('低手入场','头在躯干上方，落定后轻提身；双手低位随动'),
        'S07':('山路迈步与环顾','三次抬身—落步—回弹，步幅不等，手臂随身摆动'),
        'S08':('收步起语','减速站稳，左手先向外伸展，准备圆弧收腰；右手准备指点'),
        'S09':('叉腰指点酒家','左手先沿快速圆弧收腰、肘外拱后保持；右手向Sony右上方三次指点；第二次较重'),
        'S10':('山路起伏前行','放下指点手，四次抬身落步；三杆协调起伏，末尾收护迎虎；滑轨留待接入')}
    for scene in score['scenes']:
        if scene['id'] in edits:
            scene['previous_version_execution']=dict(status=scene['execution_status'],
                evidence=scene.pop('execution_evidence',None))
            scene['title'],scene['human']=edits[scene['id']]
            scene['execution_status']='planned_not_executed'
            scene['revision']='opening_v4'
    score['head_alignment_policy']=revision['acceptance'][0]
    score['opening_keyframes']=rows
    score['rehearsal_order']=['17–23秒：叉腰与右上指点', '10–16及23–29秒：三杆山路起伏',
                             '29秒衔接及后续攻防：复核新头部基准', '完整原音轨连排']
    return revision,score


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview',type=Path)
    parser.add_argument('--audio',type=Path)
    args=parser.parse_args()
    base=json.loads((OUT/'score.json').read_text(encoding='utf-8'))
    observed=json.loads((ROOT/'config/person_head_centering_fine_result.20261015.json').read_text())
    result_path=ROOT/'config/person_opening_m_result.20261015.json'
    result=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else None
    extension_path=ROOT/'config/person_hip_extension_n_result.20261015.json'
    extension=json.loads(extension_path.read_text(encoding='utf-8')) if extension_path.exists() else None
    applications=[]
    for name in ('person_hip_arc_o_result.20261015.json','person_hip_support_p_result.20261015.json'):
        path=ROOT/'config'/name
        if path.exists():applications.append(json.loads(path.read_text(encoding='utf-8')))
    revision,score=build(base,observed,result,extension,applications)
    for name,value in [('opening_revision_v4.json',revision),('score.opening_v4.json',score)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.preview:
        import hashlib
        import shutil
        if args.audio is None or hashlib.sha256(args.audio.read_bytes()).hexdigest()!=base['audio']['sha256']:
            raise ValueError('Preview requires the unchanged original audio')
        args.preview.mkdir(parents=True,exist_ok=True)
        shutil.copy2(args.audio,args.preview/'task1.wav')
        template=Path(__file__).with_name('story_rehearsal.html').read_text(encoding='utf-8')
        (args.preview/'index.html').write_text(template.replace('__SCORE_JSON__',
            json.dumps(score,ensure_ascii=False).replace('<','\\u003c')),encoding='utf-8')
    print(json.dumps(dict(keyframes=len(revision['keyframes']),motor_ready=False)))


if __name__=='__main__':main()
