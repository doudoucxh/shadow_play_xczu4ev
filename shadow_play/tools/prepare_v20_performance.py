"""Prepare V20 cues, sourced A01 candidates and a local review page. No motors."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import quote

import v20_preparation_model as model

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
DEFAULT_SOURCE=REPO/'任务一_V20_固定滑轨独立动作'
DEFAULT_OUTPUT=ROOT/'planning/wusong_v20_20261018'
V20_SUMMARIES={
    'A01':'TH抬头，TT配合上下和小范围横向摆动，带动虎身扭动；两条滑轨保持固定。',
    'A02':'WL在脖子高度、WR在腰部高度，快速水平换位再换回；保持固定左右手身份，不改成大圆弧。',
    'A03':'身体位置保持，双手各自向外上方展开，锣鼓停时恢复自然斜垂；肘部被动，臂长不变。',
    'A04':'双手在各自一侧大幅向外上方做说话手势，再恢复斜垂；不靠拉长前臂扩大幅度。',
    'A05':'站立左手沿身体右外侧大圆弧高举蓄势，离开头颈；右手向身体右外侧低位伸展。肘部被动，臂长不变。',
    'A06':'固定站位三连击：右手水平直拳打下巴，左手沿右外侧大圆弧砸虎头，再双手沿右外侧上绕后同砸，左上右下。',
    'A07':'仅练额头点竖直提起下放，双手跟随；不包含横向跳上虎背，两轨固定。',
    'A08':'先摆好骑姿。右手抓虎头，左手沿身体左外侧大圆弧高举、砸头、外侧回收，共11击；虎头尾挣扎逐渐衰弱。',
    'A09':'虎头逐渐低下，头与前身下沉，尾末不再主动摆动；本段只练虎头尾的死亡收势。',
    'A10':'预先靠近虎尾，左手向人物左侧远处斜伸抓住尾末并保持外展；本固定轨片段不包含拖行。',
    'A11':'右手先向低位后方拉开，再水平伸出击打预定下巴点并收回；左手保持上方蓄势。对应P01单练。',
    'A12':'左手沿身体右外侧大圆弧高举后砸虎头，再沿外侧回收；臂长不变，肘部被动。对应P02单练。',
    'A13':'双手沿身体右外侧大圆弧上绕后同时砸头，始终左上右下；臂长不变。对应P03单练。',
    'A14':'仅练三次受击反应：虎头回缩低头、尾末配合并保持悬线张力；虎轨固定，不用轨道平移替代。'
}


def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def relative_url(path,output):
    import os
    return quote(Path(os.path.relpath(path,output)).as_posix(),safe='/')


def build(source):
    checkpoint=load(ROOT/'config/task1_v20_midpoint_checkpoint_20261018.json')
    full=load(source/'source/full_plan.json');actions=load(source/'actions.json')
    audio=load(ROOT/'hdmi_ui/runtime/task1_audio.json')
    if sha(source/'source/full_audio.wav')!=audio['source']['sha256'] or full['audio']['sha256']!=audio['source']['sha256']:
        raise ValueError('V20 guidance and selected soundtrack differ')
    if sha(ROOT/audio['playback']['asset'])!=audio['playback']['sha256']:
        raise ValueError('Selected playback copy checksum mismatch')
    if len(actions)!=14 or len({a['id'] for a in actions})!=14:raise ValueError('Expected fourteen independent actions')
    if checkpoint['operator_report']['all_ten_at_135_degrees'] is not True:raise ValueError('Operator midpoint report required')
    source_hashes={name:sha(source/name) for name in ['actions.json','source/full_plan.json','V20最新动作补充.json']}
    groups={};prepared=[]
    for action in actions:
        folder=source/(action['id']+'_'+action['title']);script=load(folder/'script.json')
        trajectory=[json.loads(line) for line in (folder/'trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
        if script['motor_ready'] is not False:raise ValueError('Review new source calibration before rebuilding')
        if not trajectory or any(set(row['five_rods'])!=set(model.ROD_CHANNELS) for row in trajectory):
            raise ValueError('Complete five-rod references required')
        limits={}
        for rod in model.ROD_CHANNELS:
            points=[row['five_rods'][rod]['target_attachment_xy'] for row in trajectory]
            if any(len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point) for point in points):
                raise ValueError('Finite reference attachment points required')
            if any(row['five_rods'][rod]['motor_command'] is not None for row in trajectory):
                raise ValueError('Source commands changed; do not overwrite measured work')
            limits[rod]=dict(x_range=[min(p[0] for p in points),max(p[0] for p in points)],
                             y_range=[min(p[1] for p in points),max(p[1] for p in points)])
        if any(row['rails']['mode']!='hold' or row['rails']['wusong_display_x']!=action['wrail']
               or row['rails']['tiger_display_x']!=action['trail'] for row in trajectory):
            raise ValueError('Fixed-rail reference changed')
        pair=(action['wrail'],action['trail'])
        if pair not in groups:groups[pair]=dict(id='G'+str(len(groups)+1),reference_display_positions=list(pair),actual_mm=None,actions=[])
        groups[pair]['actions'].append(action['id'])
        source_hashes[(folder/'script.json').relative_to(source).as_posix()]=sha(folder/'script.json')
        source_hashes[(folder/'trajectory.jsonl').relative_to(source).as_posix()]=sha(folder/'trajectory.jsonl')
        prepared.append(dict(id=action['id'],title=action['title'],description=action['details'],
            preview_description=V20_SUMMARIES[action['id']],
            role='main_independent_scene' if int(action['id'][1:])<=10 else 'component_drill_not_an_extra_scene',
            source_audio_range_s=script['source_audio_range_s'],duration_s=script['duration_s'],
            position_group=groups[pair]['id'],start_condition=script['start_condition'],
            start_attachment_reference={k:v['target_attachment_xy'] for k,v in script['start_pose'].items()},
            reference_ranges=limits,reference_units='normalized_screen_xy_not_mm_or_PWM',
            manual_start_pulse_us=None,measured_waypoints=None,onsite_review=None,motor_ready=False,
            events=[dict(id=e['id'],source_time_s=e['source_time_s'],local_time_s=e['time_s']) for e in script['events']],
            source_directory=folder.relative_to(REPO).as_posix(),reference_frames=len(trajectory),
            end_policy='Hold this segment end pose; prepare its next start separately'))
    coverage=[]
    for cue in full['impact_cues']:
        ids=[a['id'] for a in prepared if a['source_audio_range_s'][0]<=cue['time_s']<a['source_audio_range_s'][1]]
        coverage.append(dict(id=cue['id'],time_s=cue['time_s'],attack_type=cue['attack_type'],covered_by=ids))
    poses={'midpoint':dict(pulse_us=model.MIDPOINT[:],source=dict(kind='operator_confirmed_midpoint'),current_assembly_verified=True)}
    historical_hashes={}
    for key,filename,edge in [('head_yaw','tiger_map_a_result.20261012.json',1),
            ('head_lift','tiger_map_a_result.20261012.json',3),('tail_yaw','tiger_map_a_result.20261012.json',5),
            ('tail_lift','tiger_map_b_result.20261012.json',1),('both_yaw','tiger_map_b_result.20261012.json',3),
            ('both_lift','tiger_map_b_result.20261012.json',5)]:
        path=ROOT/'config'/filename;historical_hashes[filename]=sha(path)
        poses[key]=model.historical_pose(load(path),edge,dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
    a01=model.make_a01_candidate(poses);checks=model.make_direction_checks(poses)
    original=model.compile_frames(a01);slow=model.compile_frames(a01,.25)
    check_summaries=[]
    for check in checks:
        frames=model.compile_frames(check)
        check_summaries.append(dict(id=check['id'],frames=len(frames['frames']),duration_s=frames['duration_s'],peak_step_us=frames['peak_step_us']))
    return dict(schema='v20_performance_preparation_v1',title='武松打虎 · V20固定轨表演准备',
        status='offline_candidates_prepared_not_executed',motor_ready=False,automatic_replay_allowed=False,
        camera_use_requested=False,reference_checkpoint=checkpoint,
        audio=audio,source_folder=source.relative_to(REPO).as_posix(),source_hashes=source_hashes,
        rod_channels=dict(mapping=model.ROD_CHANNELS,source='config/capture.servos.real.template.json',
                          meaning='Existing project fixed identities; current attachment identity still to check onsite'),
        position_groups=list(groups.values()),actions=prepared,
        main_scene_order=[a['id'] for a in prepared if a['role']=='main_independent_scene'],
        separate_drills=[a['id'] for a in prepared if a['role']!='main_independent_scene'],
        audio_impact_coverage=coverage,uncovered_impact_ids=[c['id'] for c in coverage if not c['covered_by']],
        continuous_full_show_available=False,
        continuity_requirements=['每个独立动作核对起始摆位；组间预置位置不同，固定轨运行不自动移动轨道',
            'A11–A14是A06的部件单练，不应再拼成额外一轮攻击',
            'P04–P08未被独立片段覆盖；其中两次踢腿依赖滑轨联动，保持缺项'],
        historical_target_hashes=historical_hashes,historical_a01_poses=poses,
        a01_candidate=a01,a01_direction_checks=checks,
        offline_checks=dict(original=dict(frames=len(original['frames']),duration_s=original['duration_s'],peak_step_us=original['peak_step_us']),
                            quarter_speed=dict(frames=len(slow['frames']),duration_s=slow['duration_s'],peak_step_us=slow['peak_step_us']),
                            isolated_checks=check_summaries,person_six_pulses_unchanged=True,rails_commanded=False),
        runtime_gate=model.proposed_runtime_gate(a01,checkpoint),
        next_review='现场逐个确认六项方向检查，再检查A01四分之一速；尚未执行这些步骤')


def write_outputs(plan,output,frames_output):
    output.mkdir(parents=True,exist_ok=True);frames_output.mkdir(parents=True,exist_ok=True)
    def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    save(output/'preparation.json',plan)
    a01=plan['a01_candidate']
    for name,speed in [('a01-original-speed.json',1.),('a01-quarter-speed.json',.25)]:
        save(frames_output/name,model.compile_frames(a01,speed))
    for check in plan['a01_direction_checks']:save(frames_output/(check['id']+'.json'),model.compile_frames(check))
    preview=dict(title=plan['title'],actions=[dict(action) for action in plan['actions']],groups=plan['position_groups'],
        missing=plan['uncovered_impact_ids'],poses=plan['historical_a01_poses'],
        candidate=a01,frames=model.compile_frames(a01)['frames'],checks=plan['a01_direction_checks'])
    for action in preview['actions']:
        folder=REPO/action['source_directory']
        action['guide_url']=relative_url(folder/'index.html',output)
        action['video_url']=relative_url(folder/'animation.mp4',output)
    preview['audio_url']=relative_url(ROOT/plan['audio']['playback']['asset'],output)
    template=(ROOT/'tools/v20_preparation.html').read_text(encoding='utf-8')
    packed=json.dumps(preview,ensure_ascii=True,separators=(',',':')).replace('<',r'\u003c')
    page=template.replace('/* PREPARATION_DATA */',packed)
    (output/'preview.html').write_text(page,encoding='utf-8',newline='\n')
    lines=['# V20固定轨表演准备单','',
           '已按用户确认的十路135°中位准备。此包无串口/电机执行入口，所有候选仍待当前装配现场核验。','',
           '| 动作 | 原音频区间（秒） | 预置组 | 用途 |','|---|---:|---|---|']
    for a in plan['actions']:
        lines.append(f"| {a['id']} {a['title']} | {a['source_audio_range_s'][0]:.3f}–{a['source_audio_range_s'][1]:.3f} | {a['position_group']} | {'独立场景' if a['role']=='main_independent_scene' else '部件单练'} |")
    lines+=['','四组位置为原预演显示单位，不是毫米，也不自动驱动滑轨。P04–P08保留为未覆盖项。',
        '', '首段A01：原音频2.7–9.0秒，6.3秒候选使用已有虎四路采纳目标。没有从归一化视觉坐标换算PWM。',
        '人物六路指令固定1500μs且不使能，虎四路候选使能掩码960。该选择仍待当前机械状态核对。',
        f"原速离线采样{plan['offline_checks']['original']['frames']}帧，最大相邻步进{plan['offline_checks']['original']['peak_step_us']}μs；四分之一速25.2秒。",'',
        '逐项检查：7号横转、8号上提、9号横转、10号上提、7/9号共同横转、8/10号共同上提；各项6秒，互不自动串行。',
        '每项含2秒到历史目标、1秒观察、2秒候选回程、1秒观察；这些是待核验路径，不是安全证明。',
        '', '每项方向/余量/鱼线/回程的现场记录仍为空。A01匹配V20视觉效果及音频实机延迟仍未验收。',
        '后续A02–A14的实机目标留空，准备页保留原指导与音频卡点供逐段配姿。','']
    (output/'准备单.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--frames-output',type=Path,default=REPO/'.review_work/v20-preparation-20261018/frames')
    args=p.parse_args();plan=build(args.source.resolve());write_outputs(plan,args.output.resolve(),args.frames_output.resolve())
    print(json.dumps(dict(prepared_actions=len(plan['actions']),position_groups=len(plan['position_groups']),
        uncovered_impacts=plan['uncovered_impact_ids'],a01=plan['offline_checks'],motor_ready=False,
        preview=str((args.output/'preview.html').resolve())),ensure_ascii=True))


if __name__=='__main__':main()
