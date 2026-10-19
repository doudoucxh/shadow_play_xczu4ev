"""Compile the full V20 visual score and readiness evidence, without hardware I/O.

This module deliberately has no serial, MMIO, motion-backend or player imports.
Normalized attachment points never become pulse widths or measured rail targets.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import wave

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SOURCE = REPO / '任务一_V20_完整版_外展蓄势与大圆弧下砸'
OUTPUT = ROOT / 'planning/wusong_v20_full_20261019'
RODS = ('WH', 'WL', 'WR', 'TH', 'TT')
POINTS = dict(WH='wusong_head', WL='wusong_left', WR='wusong_right',
              TH='tiger_head', TT='tiger_tail')
IMAGE = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
OUTPUT_FILES = ('calibration_targets.json', 'preview.html', 'readiness.json',
                'reference_timeline.jsonl', 'score.json', 'source_audit.json')


def load(path):
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as file:
        for data in iter(lambda: file.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def contained(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('Relative package path required')
    parts = PurePosixPath(name)
    if parts.is_absolute() or any(p in ('..', '.') for p in parts.parts):
        raise ValueError('Package path escapes its root')
    path = Path(root) / name
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Package path or symlink escapes its root')
    return path


def verify_manifest(source):
    manifest = load(source / '文件清单与校验值.json')
    if not isinstance(manifest, list) or not manifest:
        raise ValueError('Nonempty source file manifest required')
    names, total = set(), 0
    for item in manifest:
        name = item['path']; path = contained(source, name)
        if name in names or type(item['bytes']) is not int or item['bytes'] < 0:
            raise ValueError('Duplicate file or invalid size in source manifest')
        names.add(name)
        if not path.is_file() or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise ValueError('Source file checksum mismatch: ' + name)
        total += item['bytes']
    extras = sorted(p.relative_to(source).as_posix() for p in source.rglob('*')
                    if p.is_file() and p.relative_to(source).as_posix() not in names
                    and p.name != '文件清单与校验值.json')
    return dict(passed=True, files_checked=len(names), total_bytes=total,
                unlisted_files=extras, manifest_sha256=sha(source / '文件清单与校验值.json'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def point(value):
    return isinstance(value, list) and len(value) == 2 and all(finite(v) for v in value)


def scene_at(scenes, when):
    for scene in scenes:
        if scene['start_s'] <= when < scene['end_s']:
            return scene
    if when == scenes[-1]['end_s']:
        return scenes[-1]
    raise ValueError('Time is not covered by a scene')


def sample_at(when, rate):
    if not finite(when) or when < 0 or type(rate) is not int or rate <= 0:
        raise ValueError('Nonnegative finite time and positive integer sample rate required')
    return int(math.floor(when * rate + .5))


def validate_structure(plan, frames, rods, *, expected_scenes=24, expected_cues=19):
    if plan.get('schema') != 'task1_choreography_editor_v3' or plan.get('motor_ready') is not False:
        raise ValueError('Uncalibrated V20 choreography input required; do not overwrite measured work')
    audio = plan['audio']; duration = audio['duration_s']
    if (not finite(duration) or duration <= 0 or type(audio['sample_rate_hz']) is not int
            or type(audio['sample_frames']) is not int or audio['sample_rate_hz'] <= 0
            or abs(duration - audio['sample_frames'] / audio['sample_rate_hz']) > 1e-9):
        raise ValueError('Audio duration must match its exact sample count')
    scenes = plan['scenes']
    if len(scenes) != expected_scenes or len({s['id'] for s in scenes}) != len(scenes):
        raise ValueError('Complete, uniquely identified scene list required')
    previous = 0
    for scene in scenes:
        start, end = scene['start_s'], scene['end_s']
        if not all(finite(x) for x in (start, end)) or end <= start or abs(start - previous) > 1e-6:
            raise ValueError('Scene gap, overlap or invalid interval')
        previous = end
    if abs(previous - duration) > 1e-6:
        raise ValueError('Scene coverage differs from audio duration')
    cues = plan['impact_cues']
    if (len(cues) != expected_cues or len({c['id'] for c in cues}) != len(cues)
            or len({c['time_s'] for c in cues}) != len(cues)):
        raise ValueError('Complete unique impact cue list required')
    for cue in cues:
        if not finite(cue['time_s']) or not 0 <= cue['time_s'] < duration:
            raise ValueError('Impact outside audio clock')
        scene_at(scenes, cue['time_s'])
    if len(frames) != len(rods) or not frames:
        raise ValueError('Paired complete five-rod reference streams required')
    for index, (frame, rod) in enumerate(zip(frames, rods)):
        t = frame['time_s']
        if (not finite(t) or abs(t - index / 25) > 1e-7 or t >= duration
                or rod['time_s'] != t or frame.get('motor_ready') is not False
                or rod.get('motor_ready') is not False or set(rod['five_rods']) != set(RODS)
                or frame.get('units') != 'normalized_screen_xy'
                or frame.get('origin') != 'bottom_left'):
            raise ValueError('Reference timing, units or five-rod identity mismatch')
        expected_scene = scene_at(scenes, t)['id']
        if frame['scene_id'] != expected_scene or rod['scene_id'] != expected_scene:
            raise ValueError('Frame assigned to the wrong scene')
        for name in RODS:
            attachment = frame['puppet_attachment_points'][POINTS[name]]
            if (not point(attachment) or rod['five_rods'][name]['target_front_attachment_xy'] != attachment
                    or rod['five_rods'][name].get('command') is not None
                    or rod['five_rods'][name].get('rear_observation_xy') is not None
                    or not point(rod['five_rods'][name]['illustrative_tip_xy'])
                    or not point(frame['rod_endpoints_illustrative'][POINTS[name]])):
                raise ValueError('Attachment, illustrative tip, observation or command mismatch')
        if set(frame['visible']) != {'wusong', 'tiger'} or any(not finite(v) or not 0 <= v <= 1 for v in frame['visible'].values()):
            raise ValueError('Invalid visibility envelope')
    if duration - frames[-1]['time_s'] > .04 + 1e-6:
        raise ValueError('Reference ends before the final audio frame')
    return dict(scene_count=len(scenes), cue_count=len(cues), paired_reference_frames=len(frames),
                reference_hz=25, duration_s=duration, complete_audio_coverage=True,
                motor_commands_present=False)


def compile_score(plan, frames, playback=None):
    rate = plan['audio']['sample_rate_hz']; duration = plan['audio']['duration_s']
    scenes = copy.deepcopy(plan['scenes'])
    for scene in scenes:
        scene.update(start_audio_sample=sample_at(scene['start_s'], rate),
                     end_audio_sample=sample_at(scene['end_s'], rate),
                     reset_pose_at_boundary=False, hardware_start_pose=None,
                     measured_servo_route=None, measured_rail_route=None)
    events = []
    for cue in sorted(plan['impact_cues'], key=lambda c: c['time_s']):
        nearest = min(frames, key=lambda f: abs(f['time_s'] - cue['time_s']))
        if abs(nearest['time_s'] - cue['time_s']) > .020001 or nearest['impact_id'] != cue['id']:
            raise ValueError('Impact lacks a nearby source reference frame')
        event = copy.deepcopy(cue)
        event.update(scene_id=scene_at(scenes, cue['time_s'])['id'],
                     target_audio_sample=sample_at(cue['time_s'], rate),
                     nearest_reference_time_s=nearest['time_s'],
                     reference_quantization_error_ms=(nearest['time_s'] - cue['time_s']) * 1000,
                     measured_motor_lead_s=None, motor_send_time_s=None,
                     motor_send_audio_sample=None)
        if playback is not None:
            event['target_playback_sample'] = sample_at(cue['time_s'], playback['sample_rate_hz'])
        events.append(event)
    return dict(schema='v20-full-offline-score-v1',
                title='武松打虎 · V20完整版准备', motor_ready=False,
                audio=copy.deepcopy(plan['audio']), duration_s=duration,
                scene_count=len(scenes), cue_count=len(events), scenes=scenes, impact_cues=events,
                narration_segments=copy.deepcopy(plan.get('narration_segments', [])),
                attack_groups=copy.deepcopy(plan['attack_groups']),
                clock=dict(origin='First selected WAV sample', sample_rate_hz=rate,
                           terminal_audio_sample=plan['audio']['sample_frames'],
                           command_lead='Unknown until measured; never substitute preview_lead_s',
                           cue_order='Sort by time_s and retain IDs; P15 precedes P14',
                           scene_boundaries='Continuous score, no implicit initialization'),
                playback_clock=(dict(sample_rate_hz=playback['sample_rate_hz'],
                    decoded_frames=playback['decoded_frames'],asset_sha256=playback['sha256'],
                    acoustic_latency_s=None, measured_motor_lead_s=None) if playback else None),
                source_choreography=copy.deepcopy(plan),
                mechanics_v20=copy.deepcopy(plan['v20_additions']),
                source_contract=copy.deepcopy(plan['mechanism_contract']))


def compile_references(frames, duration, rate):
    result = []
    for frame in frames:
        result.append(dict(time_s=frame['time_s'], audio_sample=sample_at(frame['time_s'], rate),
            scene_id=frame['scene_id'], phase=frame['phase'], impact_id=frame['impact_id'],
            visible=frame['visible'],
            attachments={name: frame['puppet_attachment_points'][POINTS[name]] for name in RODS},
            illustrative_rod_tips={name: frame['rod_endpoints_illustrative'][POINTS[name]] for name in RODS},
            body_reference_centers=frame['body_centers'],
            relative_depth=frame['relative_depth_state'],
            holding_hand=frame['holding_hand'],
            motor_command=None, rail_command=None, motor_ready=False))
    # Exact audio endpoint is a visual final-pose hold, never an output/keepalive.
    terminal = copy.deepcopy(result[-1])
    terminal.update(time_s=duration, audio_sample=sample_at(duration, rate),
                    impact_id=None, visual_endpoint_hold=True)
    result.append(terminal)
    return result


def readiness(evidence, rail_setup):
    state = evidence['state']
    clear = evidence['observed_clear_response_channels']
    unresolved = sorted(set(range(1, 11)) - set(clear))
    clean_record = (state.get('armed') is False and state.get('enabled_mask') == 0
                    and state.get('faults') == 0 and state.get('pending') is False)
    blockers = [
        dict(id='unconfirmed_servo_response', description=str(len(unresolved))+'路舵盘实际响应未确认', channels=unresolved),
        dict(id='tiger_attachment_conflict', description='完整版TT要求尾末控制点，用户当前9/10定义为虎脚；没有已核验的尾末通道',
             source_role='tiger_tail_tip', user_current_role='tiger_feet', channels=[9, 10]),
        dict(id='no_loaded_mapping', description='缺五点实测坐标到十路PWM的映射及杆长、鱼线、层次和避让边界'),
        dict(id='no_full_motor_route', description='24场完整PWM路线、起势衔接和带杆连续路径尚未实测'),
        dict(id='no_rail_driver', description='两轨实际固件、地址、接线、限位、零点和已验证驱动仍缺失'),
        dict(id='no_measured_timing', description='出拳、受击、滑轨停止和音频命中的实测提前量与误差未标定'),
        dict(id='no_current_dual_view_calibration', description='前后台相机没有可用的幕面/杆端联合标定'),
        dict(id='no_fresh_execution_binding', description='完整路线没有绑定当前实际姿态、启动、序号和现场复核的单次执行许可'),
    ]
    if not clean_record:
        blockers.insert(0, dict(id='unclean_last_record', description='最新记录不是无故障的关闭输出状态'))
    return dict(schema='v20-full-readiness-v1', offline_preparation_complete=True,
        physical_performance_ready=False, automatic_replay_allowed=False,
        evidence_is_historical=True, last_recorded_sequence=state['sequence'],
        last_recorded_boot_id=evidence['boot_id'], last_recorded_state=state,
        clear_local_response_channels=clear, unresolved_response_channels=unresolved,
        operator_control_groups=evidence['operator_confirmed_control_groups'],
        source_TT_channel_assignment=None, rails=copy.deepcopy(rail_setup['rails']), blockers=blockers,
        physical_execution_entry_available=False,
        policy='No hardware interface in this package; editing flags never creates execution permission')


def geometry_audit(frames, score):
    def display(p): return p[0] * 80, p[1] * 50
    def distance(a, b):
        a, b = display(a), display(b)
        return math.hypot(a[0] - b[0], a[1] - b[1])
    lengths = {name: [] for name in ('left_upper', 'left_forearm', 'right_upper', 'right_forearm')}
    for frame in frames:
        p = frame['points']
        if p['wusong_left_shoulder'] != p['wusong_right_shoulder']:
            raise ValueError('Reference violates common shoulder projection')
        for side in ('left', 'right'):
            lengths[side + '_upper'].append(distance(p['wusong_'+side+'_shoulder'], p['wusong_'+side+'_elbow']))
            lengths[side + '_forearm'].append(distance(p['wusong_'+side+'_elbow'], p['wusong_'+side]))
    contacts = []
    for cue in score['impact_cues']:
        frame = min(frames, key=lambda f: abs(f['time_s'] - cue['time_s']))
        contacts.append(dict(id=cue['id'], target_time_s=cue['time_s'], reference_time_s=frame['time_s'],
                             marker=frame['impact_id'], quantization_ms=cue['reference_quantization_error_ms']))
    return dict(common_shoulder_all_frames=True,
        arm_lengths_display_units={k:dict(min=min(v), max=max(v), spread=max(v)-min(v)) for k,v in lengths.items()},
        projected_forearm_lengths_are_not_fixed_hardware_lengths=True,
        source_projection_note='Source renderer changes wrist/fingertip anchor across turning and uses schematic depth foreshortening; no measured 3D constant-length model is available',
        contact_reference_frames=contacts,
        reference_units='Source schematic units 80 by 50; not measured centimetres',
        actual_hardware_geometry_verified=False)


def build(source=SOURCE, output=OUTPUT):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.is_relative_to(source):
        raise ValueError('Output must be separate from the user source bundle')
    manifest = verify_manifest(source)
    plan = load(source/'03_action_plan.json')
    frames = [json.loads(line) for line in (source/'video/visual_refs.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    rods = [json.loads(line) for line in (source/'五杆逐帧位置_25Hz.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    structure = validate_structure(plan, frames, rods)
    audio = contained(source, plan['audio']['file'])
    if sha(audio) != plan['audio']['sha256']:
        raise ValueError('Selected source WAV checksum mismatch')
    with wave.open(str(audio), 'rb') as wav:
        if (wav.getnframes() != plan['audio']['sample_frames'] or wav.getframerate() != plan['audio']['sample_rate_hz']
                or wav.getnchannels() != plan['audio']['channels'] or wav.getsampwidth()*8 != plan['audio']['pcm_bits']):
            raise ValueError('WAV format differs from the score clock')
    current_audio = load(ROOT/'hdmi_ui/runtime/task1_audio.json')
    if current_audio['source']['sha256'] != sha(audio) or sha(ROOT/current_audio['playback']['asset']) != current_audio['playback']['sha256']:
        raise ValueError('Installed playback selection and full score soundtrack differ')
    original_audio = REPO.parent/'武松打虎8.wav'
    if original_audio.exists() and sha(original_audio) != sha(audio):
        raise ValueError('User-selected original audio differs from source score')
    evidence = load(ROOT/'config/rewired_axes_result_20261019.json')
    rail_setup = load(ROOT/'config/manual_mechanism_setup.json')
    score = compile_score(plan, frames, current_audio['playback'])
    references = compile_references(frames, score['duration_s'], score['audio']['sample_rate_hz'])
    ready = readiness(evidence, rail_setup)
    geometry = geometry_audit(frames, score)
    render = load(source/'video/render_validation.json')
    if render['source_plan_sha256'] != sha(source/'03_action_plan.json') or render['audio_sha256'] != sha(audio):
        raise ValueError('Rendered reference belongs to another plan/audio')
    source_checks = load(source/'audit/final_check.json')
    for item in source_checks['movies']:
        if sha(contained(source/'video', item['file'])) != item['sha256']:
            raise ValueError('Preview movie differs from source audit')
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'score.json', score)
    with (output/'reference_timeline.jsonl').open('w', encoding='utf-8', newline='\n') as file:
        for row in references:file.write(json.dumps(row,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    write_json(output/'readiness.json', ready)
    poses = load(source/'12_起始站位与标定目标.json')
    write_json(output/'calibration_targets.json', dict(schema='v20-full-calibration-targets-v1',
        source_poses=poses, source_semantic_conflict='TT tail tip versus currently assigned tiger feet',
        measured_motor_values=None, measured_rail_values=None, measured_lead_times=None,
        authorized_motion=False, original_source_sha256=sha(source/'12_起始站位与标定目标.json')))
    audit = dict(schema='v20-full-source-audit-v1', source_directory=source.relative_to(REPO).as_posix(),
        source_plan_sha256=sha(source/'03_action_plan.json'), manifest=manifest, structure=structure,
        selected_original_audio_verified=original_audio.exists(), audio_sha256=sha(audio),
        current_playback=current_audio, geometry=geometry,
        source_version='V20 additions override preserved legacy labels',
        source_stale_labels=['00_先读我 first line V16', '03_action_plan title V9', 'source contract drag hand pending while V20 selects left'],
        imported_source_instructions_executed=False, source_code_executed=False,
        user_source_modified=False, motor_commands_sent=False, raw_camera_frames_in_output=False,
        generated_reference_frames=len(references), terminal_reference_is_visual_only=True)
    write_json(output/'source_audit.json', audit)
    payload=dict(score=score,readiness=ready,references=references,
        media=dict(audio=os.path.relpath(audio,output).replace(os.sep,'/'),
                   audience=os.path.relpath(source/'video/audience.mp4',output).replace(os.sep,'/'),
                   annotated=os.path.relpath(source/'video/annotated.mp4',output).replace(os.sep,'/')))
    template=(ROOT/'tools/v20_full_preview.html').read_text(encoding='utf-8')
    embedded=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    (output/'preview.html').write_text(template.replace('__V20_DATA__',embedded),encoding='utf-8',newline='\n')
    write_json(output/'MANIFEST.json',dict(schema='v20-full-output-manifest-v1',files={name:sha(output/name) for name in OUTPUT_FILES}))
    return dict(output=str(output),offline_preparation_complete=True,physical_performance_ready=False,
                scenes=len(score['scenes']),cues=len(score['impact_cues']),reference_frames=len(references),
                source_files_checked=manifest['files_checked'],blockers=len(ready['blockers']))


def verify_output(output=OUTPUT, source=None):
    output=Path(output)
    manifest=load(output/'MANIFEST.json')
    if manifest.get('schema')!='v20-full-output-manifest-v1' or set(manifest['files'])!=set(OUTPUT_FILES):
        raise ValueError('Unexpected prepared file set')
    for name,expected in manifest['files'].items():
        if sha(contained(output,name))!=expected:
            raise ValueError('Prepared file checksum mismatch: '+name)
    score=load(output/'score.json');ready=load(output/'readiness.json')
    targets=load(output/'calibration_targets.json')
    if (score.get('motor_ready') is not False or ready.get('physical_performance_ready') is not False
            or ready.get('automatic_replay_allowed') is not False
            or ready.get('physical_execution_entry_available') is not False
            or targets.get('authorized_motion') is not False):
        raise ValueError('Offline package cannot acquire hardware authority by editing flags')
    refs=[json.loads(line) for line in (output/'reference_timeline.jsonl').read_text(encoding='utf-8').splitlines()]
    if any(r.get('motor_command') is not None or r.get('rail_command') is not None or r.get('motor_ready') is not False for r in refs):
        raise ValueError('Offline reference contains an unexpected hardware command')
    if len(score['scenes'])!=24 or len(score['impact_cues'])!=19 or len(refs)!=1916:
        raise ValueError('Incomplete full V20 score')
    if source is not None:
        original=load(output/'source_audit.json');checked=verify_manifest(Path(source))
        if checked['manifest_sha256']!=original['manifest']['manifest_sha256']:
            raise ValueError('Original source bundle changed after preparation')
    return dict(software_integrity_passed=True,files_checked=len(manifest['files']),
                scenes=24,cues=19,reference_frames=len(refs),physical_performance_ready=False,
                blockers=ready['blockers'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    print(json.dumps(verify_output(args.output,args.source) if args.verify_only else build(args.source,args.output),ensure_ascii=False))
