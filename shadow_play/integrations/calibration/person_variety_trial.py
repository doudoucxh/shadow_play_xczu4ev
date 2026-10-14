"""Attended person variety candidates: body drop, double lift/drop, guard, strike.
No rails or arbitrary targets. Fixed body/hand coordination needs visual review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import time

PROFILE = 'person-body-double-smash-v2'
START = [1515,1372,1515,1514,1506,1660,1510,1275,1550,1640]
HUMAN_POSES = [
    START[:6],
    [1515,1252,1515,1594,1506,1720],  # lower body and both hand supports
    [1515,1372,1515,1554,1506,1500],  # double lift, not an assumed image pose
    [1515,1212,1535,1594,1546,1660],  # double drop with body following tiger
    [1575,1272,1535,1574,1486,1650],  # candidate guard
    [1575,1372,1535,1574,1486,1650],  # lift before crossing the head
    [1715,1372,1535,1574,1486,1650],  # cross above the head
    [1715,1232,1555,1589,1586,1580],  # candidate double strike
    [1715,1372,1535,1574,1486,1650],  # lift before crossing back
    [1575,1372,1535,1574,1486,1650],
    [1575,1272,1535,1574,1486,1650],
    [1515,1252,1515,1594,1506,1720],
    START[:6]]
TARGETS = [q+START[6:] for q in HUMAN_POSES]
LABELS = ['reference','lower_body','double_lift','double_drop','guard','cross_lift','overhead_cross',
          'double_strike','return_lift','overhead_return','guard_return','lower_return','reference_return']
ROUTE_SHA = hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()
ROAR_ROUTE_SHA = '2f67a14585a330f0afd549caa9be30e3c279dce0a79b8c2a3f0491c7e3904134'


def validate(p,rows,wall=None):
    required={'approval','session_id','profile','route_sha256','expected_sequence',
              'expected_pulses_us','observer_ready','operator_hardware_unmoved',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds','boot_id','baseline_source'}
    if set(p)!=required or p['profile']!=PROFILE or p['route_sha256']!=ROUTE_SHA:
        raise ValueError('Exact fixed person variety trial required')
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
    if rows[0].get('profile')=='tiger-shadow-roar-v1':
        if rows[0].get('route_sha256')!=ROAR_ROUTE_SHA or not any(r['event']=='shadow_roar_complete' for r in rows):
            raise ValueError('Completed shadow-roar return required')
    elif rows[0].get('profile')==PROFILE:
        if rows[0].get('route_sha256')!=ROUTE_SHA or not any(r['event']=='person_variety_complete' and r['state']['pulse_us']==START for r in rows):
            raise ValueError('Completed person variety with recorded return required')
    elif rows[0].get('profile')=='person-body-double-smash-v1':
        if rows[0].get('route_sha256')!='2de4bebe62c3112e73f4429963e0c259a596ed7867d493cccea6976e2025fd6b' or not any(
            r['event']=='person_variety_complete' and r.get('highest_stage')==4 and r['state']['pulse_us']==START for r in rows):
            raise ValueError('Observed BB first-four-stage return required')
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
                d.targets=[d.pulses[:]]+(list(reversed(TARGETS[:visited])) if visited<len(TARGETS)-1 else []);d.cursor=0
                for i in range(1,len(d.targets)):d.advance(i,emit,sleep)
                emit(dict(event='person_variety_complete',highest_stage=visited,full_route_executed=visited==len(TARGETS)-1,state=d.check(),
                          stage_effect_verified=False));normal=True;break
            if action!='demo' or visited>=len(TARGETS)-1:raise RuntimeError('Only one next reviewed level')
            # BB established these four connected edges. Run them as a single
            # short phrase; all new overhead edges still stop for review.
            last=4 if visited==0 else visited+1
            while visited<last:
                d.targets=[d.pulses[:],TARGETS[visited+1][:]];d.cursor=0
                d.advance(1,emit,sleep);visited+=1
                emit(dict(event='person_pose_held',level=visited,pose_label=LABELS[visited],state=d.check(),
                          needs_dual_view_review=visited==last,position_feedback=None))
                d.wait(.10,sleep)
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
        print(json.dumps(dict(dry_run=True,targets=TARGETS,mask=63,rails_enabled=False)));return
    class PersonSession(c.ChoreographySession):
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
            self.own=63;self.indices=range(6);self.targets=[]
        def check(self):
            if self.boot.read_text().strip()!=p['boot_id']:raise RuntimeError('Boot changed')
            return super().check()
    def interrupt(*unused):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(__import__('sys').stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=PersonSession(r,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:
            run(d,c.motion_emitter(log))
    finally:r.close()


if __name__=='__main__':main()
