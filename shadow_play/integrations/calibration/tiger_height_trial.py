"""Attended, stage-reviewed vertical extension from the AW terminal reference.

No rail commands, no yaw changes, no arbitrary targets and no automatic replay.
The compiled targets are NEW candidates, not calibrated loaded positions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import time

PROFILE = 'tiger-height-aw-v1'
START = [1515,1372,1515,1514,1506,1660,1510,1275,1550,1640]
PITCHES = [(1275,1640),(1455,1640),(1535,1600),(1615,1520),(1695,1440)]
TARGETS = [START[:7]+[head,START[8],rear] for head,rear in PITCHES]
ROUTE_SHA = hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()
AW_ROUTE_SHA = '8f749a25cda759120104e2a8f51f09ef3fa52d4948beaf59925df379d442fea3'


def validate(p,rows,wall=None):
    required={'approval','session_id','profile','route_sha256','expected_sequence',
              'expected_pulses_us','observer_ready','operator_hardware_unmoved',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds','boot_id','baseline_source'}
    if set(p)!=required or p['profile']!=PROFILE or p['route_sha256']!=ROUTE_SHA:
        raise ValueError('Exact fixed vertical trial required')
    if p['approval']!='attended-fixed-puppet-choreography-20261012':raise ValueError('Attended trial required')
    if not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):raise ValueError('Invalid session ID')
    if any(p[k] is not True for k in ['observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed']):
        raise ValueError('Unchanged mechanism and attended dual view required')
    # Windows checks camera receipt age before launch. The board wall clock is
    # not synchronized; its live host lease and duration use monotonic time.
    if type(p['reviewed_at_unix_ms']) is not int or (wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000):
        raise ValueError('Review expired')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600:raise ValueError('Bounded session required')
    if not re.fullmatch('[a-f0-9-]{36}',p['boot_id']):raise ValueError('Boot ID required')
    if not rows:raise ValueError('Reference lineage required')
    if rows[0].get('profile')=='story-audio-v1':
        if rows[0].get('route_sha256')!=AW_ROUTE_SHA or not any(r['event']=='story_complete' and r.get('full_show_executed') is True for r in rows):
            raise ValueError('Completed full story reference required')
    elif rows[0].get('profile')==PROFILE:
        if rows[0].get('route_sha256')!=ROUTE_SHA or not any(r['event']=='height_trial_complete' and r['state']['pulse_us']==START for r in rows):
            raise ValueError('Completed height trial with recorded return required')
    else:raise ValueError('Unsupported reference lineage')
    last=rows[-1];s=last['state']
    if last['event']!='outputs_off' or last.get('normal_frame_stop') is not True:
        raise ValueError('Reference did not stop normally')
    if (s['pulse_us']!=START or p['expected_pulses_us']!=START or s['sequence']!=p['expected_sequence']
        or s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']):raise ValueError('Inspected AW terminal reference required')


def run(d,emit,sleep=time.sleep):
    normal=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=ROUTE_SHA,
                  state=d.adopt(START[:]),position_feedback=None,incident_locks_removed=False))
        visited=0
        while True:
            d.check()
            if d.host.action is None:
                d.wait(.03,sleep);continue
            action,seq=d.host.action;d.host.action=None
            if seq!=d.sequence:raise RuntimeError('Stale request; no retry')
            if action=='finish':
                # Only the actually visited fixed corridor can be reversed.
                d.targets=[d.pulses[:]]+list(reversed(TARGETS[:visited]));d.cursor=0
                for i in range(1,len(d.targets)):d.advance(i,emit,sleep)
                emit(dict(event='height_trial_complete',highest_stage=visited,state=d.check(),
                          stage_effect_verified=False));normal=True;break
            if action!='demo' or visited>=len(TARGETS)-1:raise RuntimeError('Only one next reviewed level')
            d.targets=[d.pulses[:],TARGETS[visited+1][:]];d.cursor=0
            d.advance(1,emit,sleep);visited+=1
            emit(dict(event='height_level_held',level=visited,state=d.check(),
                      needs_dual_view_review=True,position_feedback=None))
    finally:
        emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),
                  normal_frame_stop=normal,incident_locks_removed=False))


def main():
    import hand_crossing_session_20261014_r36 as h
    c=h.c
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true');args=parser.parse_args()
    raw=args.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Plan changed')
    p=json.loads(raw);validate(p,c.checked_log(p['baseline_source']))
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,targets=TARGETS,mask=960,rails_enabled=False)));return
    class HeightSession(c.ChoreographySession):
        def __init__(self,r,host):
            c.PwmDevice.__init__(self,r)
            self.boot=Path('/proc/sys/kernel/random/boot_id')
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
            if self.boot.read_text().strip()!=p['boot_id'] or marker.get('sha256')!=h.IMAGE_SHA:raise RuntimeError('Boot/image changed')
            self.plan=dict(p,tempo_step_us=8);self.host=host;self.clock=time.monotonic
            self.deadline=self.clock()+p['duration_seconds'];self.cancel=Path('/run/shadow-pwm-recovery-cancel')
            self.hashes=self.lock_hashes();self.pulses=START[:];self.sequence=p['expected_sequence']
            self.mask=0;self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
            self.phase='resume';self.cursor=0;self.completed=set();self.reviewed=set();self.demo_used=False
            self.own=960;self.indices=range(6,10);self.targets=[]
        def check(self):
            if self.boot.read_text().strip()!=p['boot_id']:raise RuntimeError('Boot changed')
            return super().check()
    def interrupt(*unused):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(__import__('sys').stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=HeightSession(r,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:
            run(d,c.motion_emitter(log))
    finally:r.close()


if __name__=='__main__':main()
