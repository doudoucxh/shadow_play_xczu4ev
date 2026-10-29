"""Explicit derived segments from structurally checked operator-stopped takes.

The original recording stays incomplete and is embedded with its content hash.
No missing frames, positions or time are synthesized, and no hardware is used.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .model import MOTION_SCHEMA, inspect_operator_stopped, validate_recording

RECOVERY_SCHEMA = 'shadow.bus-recovery.v1'


def digest(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=True,
                                     separators=(',',':'),allow_nan=False).encode()).hexdigest()


def compile_segment(recovery, profile):
    if recovery.get('schema') != RECOVERY_SCHEMA:
        raise ValueError('Unknown recovery schema')
    source=recovery['source_record']
    if digest(source)!=recovery['source_content_sha256']:
        raise ValueError('中止原始记录的摘要不一致。')
    inspect_operator_stopped(source,profile)
    original=source['samples'];origin=original[0]['t']
    samples=[dict(t=row['t']-origin,positions=copy.deepcopy(row['positions']),kind='retained_feedback')
             for row in original]
    return dict(schema=MOTION_SCHEMA,created_utc=recovery['reviewed_utc'],
                profile_sha256=profile.fingerprint,profile=copy.deepcopy(profile.data),
                source='simulation' if source['source']=='simulation' else 'edited_feedback',
                selected=source['selected'][:],complete=True,end_reason='reviewed_operator_stop_segment',
                mode='recovered_operator_stop',samples=samples,recovery=copy.deepcopy(recovery),
                segments_summary=[dict(index=0,name='中止后已检查片段',start_s=0,
                                       end_s=samples[-1]['t'],transition_s=0,extended=False)])


def recover_file(path, profile):
    path=Path(path)
    if path.stat().st_size>64*1024*1024:
        raise ValueError('轨迹文件超过64MB。')
    raw=path.read_bytes();source=json.loads(raw.decode('utf-8-sig'))
    recovery=dict(schema=RECOVERY_SCHEMA,reviewed_utc=datetime.now(timezone.utc).isoformat(),
                  method='retain_all_valid_frames_after_operator_stop',
                  source_name=path.name,source_file_sha256=hashlib.sha256(raw).hexdigest(),
                  source_content_sha256=digest(source),source_record=source)
    record=compile_segment(recovery,profile)
    validate_recording(record,profile)
    return record


def verify_compiled(record, profile):
    expected=compile_segment(record['recovery'],profile)
    for key in ('source','selected','samples','segments_summary','mode','end_reason'):
        if record.get(key)!=expected[key]:
            raise ValueError('恢复片段与保留的原始反馈不一致，请重新检查原文件。')
