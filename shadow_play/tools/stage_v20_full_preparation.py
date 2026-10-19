"""Build or install the V20 DATA-only preparation pack; never start a process.

Installer accepts only six known JSON/JSONL data files in one new SD directory.
There are no hardware, playback, service-management or boot-file operations.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import uuid

RELEASE='v20-full-preparation-20261019-r2'
BASE=Path('/run/media/mmcblk0p2/piying')
DATA_FILES=('score.json','reference_timeline.jsonl','readiness.json','calibration_targets.json','source_audit.json','stage_policy.json')
MAX_TOTAL=12*1024*1024


def digest(data):return hashlib.sha256(data).hexdigest()


def check_policy(files):
    score=json.loads(files['score.json']);ready=json.loads(files['readiness.json'])
    targets=json.loads(files['calibration_targets.json']);policy=json.loads(files['stage_policy.json'])
    if (score.get('motor_ready') is not False or ready.get('physical_performance_ready') is not False
            or ready.get('automatic_replay_allowed') is not False or ready.get('physical_execution_entry_available') is not False
            or targets.get('authorized_motion') is not False or policy.get('data_only') is not True
            or policy.get('service_started') is not False or policy.get('motor_commands_sent') is not False
            or policy.get('automatic_replay_allowed') is not False
            or policy.get('physical_performance_ready') is not False
            or policy.get('contains_actual_motor_route') is not False):
        raise ValueError('Preparation archive cannot carry execution authority')
    if len(score['scenes'])!=24 or len(score['impact_cues'])!=19:
        raise ValueError('Incomplete score')
    if any(s.get('measured_servo_route') is not None or s.get('measured_rail_route') is not None
           or s.get('hardware_start_pose') is not None for s in score['scenes']):
        raise ValueError('Data-only preparation must not contain an executable route')
    rows=[json.loads(line) for line in files['reference_timeline.jsonl'].splitlines()]
    if len(rows)!=1916 or any(row.get('motor_command') is not None or row.get('rail_command') is not None
                             or row.get('motor_ready') is not False for row in rows):
        raise ValueError('Invalid data-only visual timeline')


def build(folder,archive):
    from v20_full_preparation import verify_output
    verify_output(folder)
    files={name:(Path(folder)/name).read_bytes() for name in DATA_FILES if name!='stage_policy.json'}
    policy=dict(schema='v20-full-stage-policy-v1',release=RELEASE,data_only=True,
        service_started=False,motor_commands_sent=False,automatic_replay_allowed=False,
        audio_asset='/run/media/mmcblk0p2/piying/shadow-theatre-board-20261017-r4-runtime/shadow_play/hdmi_ui/runtime/audio/wusong.mp3',
        audio_sha256='19a4cfe500ff555d27bd1b64261955fdddb62f774143ac42cade5c98207fe5fe',
        physical_performance_ready=False,contains_actual_motor_route=False)
    files['stage_policy.json']=(json.dumps(policy,sort_keys=True)+'\n').encode()
    check_policy(files)
    manifest=dict(schema='v20-full-data-stage-manifest-v1',release=RELEASE,files={name:digest(data) for name,data in files.items()})
    files['MANIFEST.json']=(json.dumps(manifest,sort_keys=True)+'\n').encode()
    with tarfile.open(archive,'w:gz') as tar:
        for name,data in files.items():
            info=tarfile.TarInfo(RELEASE+'/'+name);info.size=len(data);info.mode=0o644;info.mtime=0
            tar.addfile(info,io.BytesIO(data))
    return dict(archive=str(archive),sha256=digest(Path(archive).read_bytes()),files=len(files),data_only=True)


def read_archive(archive,expected_sha):
    if Path(archive).stat().st_size>MAX_TOTAL:raise ValueError('Archive exceeds size limit')
    raw=Path(archive).read_bytes()
    if digest(raw)!=expected_sha:raise ValueError('Archive checksum mismatch')
    files={};total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        for member in tar:
            prefix=RELEASE+'/'
            if not member.isfile() or not member.name.startswith(prefix):raise ValueError('Unexpected archive member')
            name=member.name[len(prefix):]
            if name not in (*DATA_FILES,'MANIFEST.json') or name in files:raise ValueError('Unexpected or duplicate data path')
            total+=member.size
            if member.size<0 or total>MAX_TOTAL:raise ValueError('Preparation data exceeds size limit')
            file=tar.extractfile(member);data=file.read()
            if len(data)!=member.size:raise ValueError('Truncated archive member')
            files[name]=data
    if set(files)!=set((*DATA_FILES,'MANIFEST.json')):raise ValueError('Incomplete data archive')
    manifest=json.loads(files.pop('MANIFEST.json'))
    if (manifest.get('schema')!='v20-full-data-stage-manifest-v1' or manifest.get('release')!=RELEASE
            or manifest.get('files')!={name:digest(data) for name,data in files.items()}):
        raise ValueError('Preparation manifest mismatch')
    check_policy(files)
    files['MANIFEST.json']=(json.dumps(manifest,sort_keys=True)+'\n').encode()
    return files


def install(archive,expected_sha,base=BASE):
    files=read_archive(archive,expected_sha);base=Path(base).resolve()
    dest=base/RELEASE
    if not base.is_dir() or dest.exists() or dest.is_symlink():raise ValueError('A new preparation directory is required')
    staging=base/('.'+RELEASE+'-'+uuid.uuid4().hex+'.part');staging.mkdir()
    # No extractall, subprocess, chmod executable, service start, or cleanup of user files.
    for name,data in files.items():
        with (staging/name).open('xb') as file:file.write(data)
        if (staging/name).read_bytes()!=data:raise RuntimeError('SD write verification failed')
    os.rename(str(staging),str(dest))
    for name,data in files.items():
        if (dest/name).read_bytes()!=data:raise RuntimeError('Installed data checksum mismatch')
    return dict(installed=str(dest),manifest_entries=len(files)-1,data_only=True,
                physical_performance_ready=False,service_started=False,motor_commands_sent=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['build','install'])
    p.add_argument('archive',type=Path);p.add_argument('--sha256');p.add_argument('--folder',type=Path)
    args=p.parse_args()
    if args.mode=='build':
        from v20_full_preparation import OUTPUT
        result=build(args.folder or OUTPUT,args.archive)
    else:result=install(args.archive,args.sha256)
    print(json.dumps(result))
