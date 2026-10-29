"""Shared audio/motion edit decisions. Compilation never opens a device."""
import copy
from bisect import bisect_right
import json
import math
from pathlib import Path
import shutil
from uuid import uuid4

from .editing import digest, utc
from .model import MOTION_SCHEMA, finite, validate_recording

AV_SCHEMA = 'shadow.bus-av-project.v1'


def clip_end(clip):
    return clip['at_s'] + (clip['out_s']-clip['in_s'])/clip['speed']


def duration(data):
    return max([clip_end(c) for c in data['clips']] or [0])


def validate(data, profile):
    if data.get('schema') != AV_SCHEMA or data.get('profile_sha256') != profile.fingerprint:
        raise ValueError('音频轨迹工程与当前接线 / 轴配置不匹配。')
    profile.select(data['selected'])
    if len(data['clips']) > 1000 or len(data['motion_sources']) > 100 or len(data['audio_sources']) > 100:
        raise ValueError('工程最多1000段、各100个素材。')
    for key, source in data['motion_sources'].items():
        if 'av_project' in source:
            raise ValueError('联合工程请用“打开工程”；不要嵌套导入联合回放文件。')
        if digest(source) != key:
            raise ValueError('轨迹原素材摘要不一致。')
        validate_recording(source, profile)
        if not set(data['selected']) <= set(source['selected']):
            raise ValueError('轨迹素材缺少工程所选轴；请按素材重新选择工程轴。')
    for key, source in data['audio_sources'].items():
        if len(key) != 64 or source.get('sha256') != key or not isinstance(source.get('file'), str):
            raise ValueError('音频素材描述无效。')
        finite(source['duration_s'], .02, 1800, '音频时长')
        if source.get('sample_rate') != 48000 or source.get('channels') != 2:
            raise ValueError('音频需转换为48kHz双声道素材。')
    ids = set(); motion = []
    for c in data['clips']:
        if c['id'] in ids or c['kind'] not in ('motion','audio'):
            raise ValueError('片段编号或类型无效。')
        ids.add(c['id'])
        if not isinstance(c['name'],str) or not 1 <= len(c['name']) <= 120:
            raise ValueError('片段名称需要1～120个字符。')
        sources = data[c['kind']+'_sources']
        if c['source_id'] not in sources: raise ValueError('缺少片段原素材。')
        source = sources[c['source_id']]
        total = source['duration_s'] if c['kind']=='audio' else source['samples'][-1]['t']-source['samples'][0]['t']
        finite(c['at_s'],0,3600,'时间轴起点')
        finite(c['in_s'],0,total,'素材入点');finite(c['out_s'],c['in_s']+.02-1e-9,total+1e-9,'素材出点')
        finite(c['speed'],.1,2,'倍率');finite(c.get('gain',1),0,2,'音量')
        finite(clip_end(c),.02,3600,'片段终点')
        if c['kind']=='motion': motion.append(c)
    motion.sort(key=lambda c:c['at_s'])
    if any(clip_end(a)>b['at_s']+1e-8 for a,b in zip(motion,motion[1:])):
        raise ValueError('轨迹片段不能重叠；请调整时间轴起点。音频重叠会混音。')
    return data


class AVProject:
    def __init__(self, profile, numbers=None, data=None):
        self.profile = profile
        self.data = copy.deepcopy(data) if data is not None else dict(
            schema=AV_SCHEMA,created_utc=utc(),profile_sha256=profile.fingerprint,
            selected=list(numbers or profile.axes),motion_sources={},audio_sources={},clips=[])
        validate(self.data,profile)
        self.undo_stack=[];self.redo_stack=[]

    def change(self, operation):
        d = dict(self.data, clips=copy.deepcopy(self.data['clips']),
                 motion_sources=dict(self.data['motion_sources']),audio_sources=dict(self.data['audio_sources']))
        operation(d);validate(d,self.profile)
        self.undo_stack.append(self.data);self.undo_stack=self.undo_stack[-30:]
        self.redo_stack.clear();self.data=d

    def add_motion(self, record, name='轨迹', at=None):
        validate_recording(record,self.profile)
        if 'av_project' in record: raise ValueError('联合回放文件请通过“打开工程”载入。')
        source=copy.deepcopy(record);key=digest(source)
        total=source['samples'][-1]['t']-source['samples'][0]['t']
        if at is None: at=max([clip_end(c) for c in self.data['clips'] if c['kind']=='motion'] or [0])
        def add(d):
            d['motion_sources'][key]=source
            d['clips'].append(dict(id=uuid4().hex,kind='motion',name=name[:120],source_id=key,
                                   at_s=at,in_s=0.,out_s=total,speed=1.,gain=1.))
        self.change(add)

    def add_audio(self, asset, at=0):
        asset=copy.deepcopy(asset);key=asset['sha256']
        def add(d):
            d['audio_sources'][key]=asset
            d['clips'].append(dict(id=uuid4().hex,kind='audio',name=asset['name'][:120],source_id=key,
                at_s=at,in_s=0.,out_s=asset['duration_s'],speed=1.,gain=1.))
        self.change(add)

    def update(self, ident, **values):
        if not set(values)<=set(('name','at_s','in_s','out_s','speed','gain')):raise ValueError('不支持的片段参数。')
        self.change(lambda d:next(c for c in d['clips'] if c['id']==ident).update(values))

    def split(self, time_s, ident=None):
        finite(time_s,0,3600,'分割时间')
        def edit(d):
            rows=[];count=0
            for c in d['clips']:
                if (ident is None or c['id']==ident) and c['at_s']+1e-8<time_s<clip_end(c)-1e-8:
                    cut=c['in_s']+(time_s-c['at_s'])*c['speed']
                    rows.extend([dict(c,out_s=cut),dict(c,id=uuid4().hex,in_s=cut,at_s=time_s)])
                    count+=1
                else: rows.append(c)
            if not count:raise ValueError('播放头没有落在可分割的片段内部。')
            d['clips']=rows
        self.change(edit)

    def delete(self, ident):
        self.change(lambda d:d.update(clips=[c for c in d['clips'] if c['id']!=ident]))

    def cut_range(self, start, end, keep=False):
        finite(start,0,duration(self.data),'选区起点');finite(end,start+.02,duration(self.data)+1e-8,'选区终点')
        def cut(d):
            rows=[]
            for c in d['clips']:
                a,b=c['at_s'],clip_end(c)
                spans=[(max(a,start),min(b,end))] if keep else [(a,min(b,start)),(max(a,end),b)]
                for x,y in spans:
                    if (y-x)*c['speed'] < .02-1e-8:continue
                    at=x-start if keep else x-(end-start if x>=end else 0)
                    rows.append(dict(c,id=uuid4().hex,at_s=max(0,at),
                        in_s=c['in_s']+(x-a)*c['speed'],out_s=c['in_s']+(y-a)*c['speed']))
            d['clips']=rows
        self.change(cut)

    def history(self, redo=False):
        src,dest=(self.redo_stack,self.undo_stack) if redo else (self.undo_stack,self.redo_stack)
        if src:dest.append(self.data);self.data=src.pop()


class MotionSampler:
    def __init__(self,data):
        self.data=data
        self.clips=sorted((c for c in data['clips'] if c['kind']=='motion'),key=lambda c:c['at_s'])
        if not self.clips:raise ValueError('请先导入至少一段舵机轨迹。')
        self.starts=[c['at_s'] for c in self.clips]
        self.times={key:[r['t']-source['samples'][0]['t'] for r in source['samples']]
                    for key,source in data['motion_sources'].items()}

    def at(self,time_s):
        c=self.clips[max(0,bisect_right(self.starts,time_s)-1)]
        rows=self.data['motion_sources'][c['source_id']]['samples'];times=self.times[c['source_id']]
        t=min(c['out_s'],max(c['in_s'],c['in_s']+(time_s-c['at_s'])*c['speed']))
        i=max(0,min(len(times)-2,bisect_right(times,t)-1));f=(t-times[i])/(times[i+1]-times[i])
        return {str(n):round(rows[i]['positions'][str(n)]*(1-f)+rows[i+1]['positions'][str(n)]*f)
                for n in self.data['selected']}


def compile_motion(data, profile):
    validate(data,profile);end=duration(data)
    if end<.02:raise ValueError('工程为空。')
    motion=[c for c in data['clips'] if c['kind']=='motion']
    if not motion:raise ValueError('导出回放轨迹前请先添加舵机轨迹。')
    sampler=MotionSampler(data)
    # Preserve the original sampling density. Upsampling to video frame rates
    # would multiply serial RPCs and unnecessarily slow a physical performance.
    times={0.,end}
    for c in motion:
        times.update((c['at_s'],clip_end(c)))
        for t in sampler.times[c['source_id']]:
            if c['in_s']<t<c['out_s']:times.add(c['at_s']+(t-c['in_s'])/c['speed'])
    ordered=[]
    for t in sorted(times):
        if not ordered or t-ordered[-1]>1e-8:ordered.append(t)
    filled=[ordered[0]]
    for a,b in zip(ordered,ordered[1:]):
        count=max(1,math.ceil((b-a)/.5-1e-8))
        filled.extend(a+(b-a)*i/count for i in range(1,count+1))
    if len(filled)>100000:raise ValueError('联合轨迹超过100000帧，请拆分工程。')
    samples=[dict(t=t,positions=sampler.at(t),kind='av_plan') for t in filled]
    simulation=any(data['motion_sources'][c['source_id']]['source']=='simulation' for c in motion)
    summaries=[dict(index=i,name=c['name'],start_s=c['at_s'],end_s=clip_end(c),transition_s=0,extended=False)
               for i,c in enumerate(sorted(motion,key=lambda c:c['at_s']))]
    return dict(schema=MOTION_SCHEMA,created_utc=data['created_utc'],profile_sha256=profile.fingerprint,
        profile=copy.deepcopy(profile.data),source='simulation' if simulation else 'edited_feedback',
        selected=data['selected'][:],complete=True,end_reason='av_edited_plan',mode='av_edited_plan',
        samples=samples,av_project=copy.deepcopy(data),segments_summary=summaries)


def verify_compiled(record, profile):
    expected=compile_motion(record['av_project'],profile)
    for key in ('source','selected','samples','segments_summary'):
        if record.get(key)!=expected[key]:raise ValueError('联合轨迹与剪辑工程不一致，请重新导出。')


def load_file(path, profile):
    path=Path(path)
    if path.stat().st_size>64*1024*1024:raise ValueError('工程超过64MB。')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    project=data.get('av_project',data)
    validate(project,profile)
    for asset in project['audio_sources'].values():
        file=Path(asset['file'])
        if not file.is_absolute():asset['file']=str((path.parent/file).resolve())
    if 'av_project' in data:validate_recording(data,profile)
    return data


def save_bundle(path, data):
    """New JSON and a neighboring assets directory; never overwrite originals."""
    from .audio import verify_asset
    path=Path(path);out=copy.deepcopy(data);project=out.get('av_project',out)
    assets=path.with_name(path.stem+'.assets')
    if path.exists() or assets.exists():raise FileExistsError('目标已存在，请使用新名称另存。')
    for asset in project['audio_sources'].values():verify_asset(asset)
    if project['audio_sources']:assets.mkdir()
    for key,asset in project['audio_sources'].items():
        target=assets/(key+'.wav');shutil.copyfile(asset['file'],target)
        asset['file']=str(Path(assets.name)/target.name)
    with path.open('x',encoding='utf-8') as stream:json.dump(out,stream,ensure_ascii=False,indent=2,allow_nan=False)
    return path
