"""Non-destructive pose/clip editor and bounded trajectory compiler. No device I/O."""
from bisect import bisect_right
import copy
from datetime import datetime, timezone
import hashlib
import json
import math

from .model import SCHEMA, MOTION_SCHEMA, finite, validate_recording
from .protocol import integer

PROJECT_SCHEMA = 'shadow.bus-edit.v1'
POSE_SCHEMA = 'shadow.bus-pose.v1'


class PoseCaptureError(ValueError):
    """Fresh feedback was read, but the requested pose cannot be recorded."""


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def capture_pose(profile, numbers, rows, simulation):
    """Only fresh device rows belong here; target widgets are never sampled."""
    profile.select(numbers)
    if set(rows) != set(numbers):
        raise ValueError('姿势反馈缺少所选轴。')
    pose = {'schema': POSE_SCHEMA, 'profile_sha256': profile.fingerprint,
            'source': 'simulation' if simulation else 'servo_feedback',
            'captured_utc': utc(), 'selected': numbers[:],
            'positions': {str(n): rows[n]['p'] for n in numbers},
            'acquired_at': {str(n): rows[n]['at'] for n in numbers}}
    validate_pose(pose, profile)
    return pose


def validate_pose(pose, profile):
    if (pose.get('schema') != POSE_SCHEMA or pose.get('profile_sha256') != profile.fingerprint
            or pose.get('source') not in ('simulation', 'servo_feedback')):
        raise ValueError('姿势来源或轴配置不匹配。')
    axes = profile.select(pose['selected'])
    keys = {str(a.number) for a in axes}
    if set(pose['positions']) != keys or set(pose['acquired_at']) != keys:
        raise ValueError('姿势反馈不完整。')
    times = []
    for a in axes:
        a.check_position(pose['positions'][str(a.number)])
        times.append(finite(pose['acquired_at'][str(a.number)], 0, 1e12, '采集时间'))
    if max(times) - min(times) > .5:
        raise ValueError('各轴采集时间相隔超过0.5秒，请重新录入。')


def duration(record):
    return record['samples'][-1]['t'] - record['samples'][0]['t']


def validate_project(data, profile):
    if data.get('schema') != PROJECT_SCHEMA or data.get('profile_sha256') != profile.fingerprint:
        raise ValueError('编辑工程与当前轴配置不匹配。')
    profile.select(data['selected'])
    sources, segments = data['sources'], data['segments']
    if not isinstance(sources, dict) or not isinstance(segments, list) or len(sources) > 1000 or len(segments) > 1000:
        raise ValueError('单个工程最多1000个原始素材/片段。')
    for key, source in sources.items():
        if digest(source) != key:
            raise ValueError('原始素材摘要改变，不能伪装为未修改的反馈。')
        if source.get('schema') == POSE_SCHEMA:
            validate_pose(source, profile)
        elif source.get('schema') == SCHEMA:
            validate_recording(source, profile)
        else:
            raise ValueError('素材必须是原始反馈或姿势；合成轨迹需展开其编辑工程。')
        if not set(data['selected']) <= set(source['selected']):
            raise ValueError('素材缺少本工程的部分轴，不能用默认角度补齐。')
    for s in segments:
        source = sources.get(s['source_id'])
        if source is None or s.get('kind') not in ('pose', 'clip'):
            raise ValueError('片段没有对应原始素材。')
        if not isinstance(s['name'], str) or not 1 <= len(s['name']) <= 120:
            raise ValueError('片段名称需要1–120个字符。')
        finite(s['transition_s'], 0, 120, '移入过渡时间')
        if s['kind'] == 'pose':
            if source['schema'] != POSE_SCHEMA:
                raise ValueError('姿势片段的来源类型错误。')
            finite(s['hold_s'], 0, 120, '停留时间')
        else:
            if source['schema'] != SCHEMA:
                raise ValueError('录制片段的来源类型错误。')
            start = finite(s['start_s'], 0, duration(source), '入点')
            end = finite(s['end_s'], start, duration(source), '出点')
            if end - start < .02 - 1e-8:
                raise ValueError('裁剪后片段至少保留20毫秒。')
            finite(s['speed'], .1, 2, '片段倍率')
    return data


class EditProject:
    """Undo stores small edit decisions; immutable source recordings are shared."""
    def __init__(self, profile, numbers=None, data=None):
        self.profile = profile
        self.data = copy.deepcopy(data) if data is not None else {
            'schema': PROJECT_SCHEMA, 'created_utc': utc(), 'profile_sha256': profile.fingerprint,
            'selected': list(numbers or []), 'sources': {}, 'segments': []}
        validate_project(self.data, profile)
        self.undo_stack, self.redo_stack = [], []

    def _snapshot(self):
        return dict(self.data, sources=dict(self.data['sources']), segments=copy.deepcopy(self.data['segments']))

    def _change(self, operation):
        candidate = self._snapshot()
        operation(candidate)
        validate_project(candidate, self.profile)
        self.undo_stack.append(self.data)
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()
        self.data = candidate

    def add_pose(self, pose, name=None, transition_s=2, hold_s=.5):
        pose = copy.deepcopy(pose)
        def change(d):
            key = digest(pose); d['sources'][key] = pose
            d['segments'].append({'kind': 'pose', 'source_id': key, 'name': name or f'姿势 {len(d["segments"])+1}',
                                  'transition_s': transition_s, 'hold_s': hold_s})
        self._change(change)

    def add_recording(self, record, name='录制片段'):
        validate_recording(record, self.profile)
        if 'av_project' in record:
            raise ValueError('音频联合轨迹请在“音频 / 轨迹剪辑”中打开，避免丢失音频编辑。')
        if not set(self.data['selected']) <= set(record['selected']):
            raise ValueError('导入轨迹没有选择本工程的全部轴，不能启用其隐藏素材中的其他轴。')
        record = copy.deepcopy(record)
        def change(d):
            if record['schema'] == MOTION_SCHEMA:
                p = record['edit_project']
                d['sources'].update(p['sources'])
                incoming = copy.deepcopy(p['segments'])
                if incoming: incoming[0]['transition_s'] = 2
                d['segments'].extend(incoming)
            else:
                key = digest(record); d['sources'][key] = record
                d['segments'].append({'kind': 'clip', 'source_id': key, 'name': name,
                                      'start_s': 0, 'end_s': duration(record), 'speed': 1, 'transition_s': 2})
        self._change(change)

    def replace_pose(self, index, pose):
        s = self.data['segments'][integer(index, 0, len(self.data['segments'])-1, '片段索引')]
        if s['kind'] != 'pose': raise ValueError('只能重新录入姿势行。')
        pose = copy.deepcopy(pose)
        def change(d):
            key = digest(pose); d['sources'][key] = pose; d['segments'][index]['source_id'] = key
        self._change(change)

    def update(self, index, **values):
        integer(index, 0, len(self.data['segments'])-1, '片段索引')
        fields = {'name', 'transition_s', 'hold_s'} if self.data['segments'][index]['kind'] == 'pose' else {
            'name', 'transition_s', 'start_s', 'end_s', 'speed'}
        if not set(values) <= fields:
            raise ValueError('不能改写原始反馈角度。')
        self._change(lambda d: d['segments'][index].update(values))

    def delete(self, index):
        integer(index, 0, len(self.data['segments'])-1, '片段索引')
        self._change(lambda d: d['segments'].pop(index))

    def duplicate(self, index):
        integer(index, 0, len(self.data['segments'])-1, '片段索引')
        def change(d):
            s = copy.deepcopy(d['segments'][index]); s['name'] = s['name'][:115] + ' 副本'
            d['segments'].insert(index+1, s)
        self._change(change)

    def move(self, index, destination):
        for n in (index, destination): integer(n, 0, len(self.data['segments'])-1, '片段索引')
        self._change(lambda d: d['segments'].insert(destination, d['segments'].pop(index)))

    def split(self, index, at):
        s = self.data['segments'][integer(index, 0, len(self.data['segments'])-1, '片段索引')]
        if s['kind'] != 'clip': raise ValueError('只有连续录制片段可按时间分割。')
        finite(at, s['start_s']+.02, s['end_s']-.02, '分割点（原素材秒）')
        def change(d):
            left, right = copy.deepcopy(s), copy.deepcopy(s)
            left['end_s'] = right['start_s'] = at
            right['transition_s'] = 0  # A contiguous split must not insert a pause.
            right['name'] = s['name'][:115] + ' 后段'
            d['segments'][index:index+1] = [left, right]
        self._change(change)

    def remove_range(self, index, start, end):
        s = self.data['segments'][integer(index, 0, len(self.data['segments'])-1, '片段索引')]
        if s['kind'] != 'clip': raise ValueError('只有连续录制片段可删除时间区间。')
        finite(start, s['start_s'], s['end_s'], '删除入点')
        finite(end, start+.02, s['end_s'], '删除出点')
        def change(d):
            rest = []
            if start > s['start_s']+1e-8:
                rest.append(dict(s, end_s=start))
            if end < s['end_s']-1e-8:
                rest.append(dict(s, start_s=end, transition_s=max(2, s['transition_s']) if rest else s['transition_s']))
            d['segments'][index:index+1] = rest
        self._change(change)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.data); self.data = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.data); self.data = self.redo_stack.pop()


def clip_points(source, start, end, numbers):
    rows = source['samples']; origin = rows[0]['t']
    times = [r['t']-origin for r in rows]
    def at(t):
        i = max(0, min(len(rows)-2, bisect_right(times, t)-1))
        fraction = min(1, max(0, (t-times[i])/(times[i+1]-times[i])))
        return {str(n): round(rows[i]['positions'][str(n)]*(1-fraction)+rows[i+1]['positions'][str(n)]*fraction) for n in numbers}
    result = [(start, at(start))]
    result.extend((t, {str(n): r['positions'][str(n)] for n in numbers})
                  for t, r in zip(times, rows) if start+1e-8 < t < end-1e-8)
    result.append((end, at(end)))
    return result


def compile_project(data, profile):
    """Compile explicit planned samples; never forge acquisition timestamps."""
    validate_project(data, profile)
    if not data['segments']:
        raise ValueError('请先录入姿势或导入轨迹。')
    axes = profile.select(data['selected']); samples = []; clock_ms = 0; summaries = []
    def append(target, seconds, kind, extend=False):
        nonlocal clock_ms
        before = samples[-1]['positions']
        required = max(abs(a.degrees(target[str(a.number)])-a.degrees(before[str(a.number)]))/a.max_speed for a in axes)
        total = max(seconds, required) if extend else seconds
        if total <= 1e-9 and target == before:
            return 0
        # <=0.5s planned intervals also permit slow playback and long holds.
        count = max(1, math.ceil(total/.5))
        started = clock_ms
        for step in range(1, count+1):
            p = {k: round(v+(target[k]-v)*step/count) for k, v in before.items()}
            prev = samples[-1]['positions']
            minimum = max(abs(a.degrees(p[str(a.number)])-a.degrees(prev[str(a.number)]))/a.max_speed for a in axes)
            dt = max(.02, total/count)
            if extend: dt = max(dt, minimum)
            ms = max(20, math.ceil(dt*1000-1e-8))
            if minimum > ms/1000+1e-8:
                raise ValueError('录制片段超过轴速度限制，请降低该片段倍率；过渡会单独自动限速。')
            clock_ms += ms
            if clock_ms > 3600000 or len(samples) >= 100000:
                raise ValueError('编辑结果超过1小时或100000帧上限。')
            samples.append({'t': clock_ms/1000, 'positions': p, 'kind': kind})
        return (clock_ms-started)/1000
    for index, s in enumerate(data['segments']):
        source = data['sources'][s['source_id']]
        points = [(0, {str(a.number): source['positions'][str(a.number)] for a in axes})] if s['kind'] == 'pose' else clip_points(source, s['start_s'], s['end_s'], data['selected'])
        start = clock_ms/1000
        bridge = 0
        if not samples:
            samples.append({'t': 0.0, 'positions': points[0][1], 'kind': 'start'})
        else:
            bridge = append(points[0][1], s['transition_s'], 'transition', extend=True)
        if s['kind'] == 'pose':
            append(points[0][1], s['hold_s'], 'hold')
        else:
            for (t0, _), (t1, p) in zip(points, points[1:]):
                append(p, (t1-t0)/s['speed'], 'clip')
        summaries.append({'index': index, 'name': s['name'], 'start_s': start, 'end_s': clock_ms/1000,
                          'transition_s': bridge, 'extended': index > 0 and bridge > s['transition_s']+.002})
    if len(samples) < 2:
        raise ValueError('动作总时长为0，请增加姿势的移入或停留时间。')
    simulation = any(data['sources'][s['source_id']]['source'] == 'simulation' for s in data['segments'])
    return {'schema': MOTION_SCHEMA, 'created_utc': data['created_utc'], 'profile_sha256': profile.fingerprint,
            'profile': copy.deepcopy(profile.data), 'source': 'simulation' if simulation else 'edited_feedback',
            'selected': data['selected'][:], 'complete': True, 'end_reason': 'edited_plan', 'mode': 'edited_plan',
            'samples': samples, 'edit_project': copy.deepcopy(data), 'segments_summary': summaries}


def verify_compiled(record, profile):
    expected = compile_project(record['edit_project'], profile)
    for key in ('source', 'selected', 'samples', 'segments_summary'):
        if record.get(key) != expected[key]:
            raise ValueError('合成轨迹与原始素材/编辑步骤不一致，请重新导出。')
