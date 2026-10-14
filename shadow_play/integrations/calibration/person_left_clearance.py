"""Left separation then overhead clearance probe; every new edge awaits review."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import time
PROFILE='person-left-clearance-v1'
START=[1515,1372,1515,1514,1506,1660,1510,1275,1550,1640]
REFERENCE=START[:]
OUT=[START,
 [1455,1372,1515,1514,1506,1660]+START[6:],
 [1455,1392,1515,1514,1506,1660]+START[6:],
 [1515,1392,1515,1514,1506,1660]+START[6:],
 [1575,1392,1525,1514,1506,1660]+START[6:],
 [1635,1392,1535,1514,1506,1660]+START[6:]]
TARGETS=OUT+list(reversed(OUT[:-1]))
ROUTE_SHA=hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()
BF_ROUTE_SHA='ffddfbf5cf2cef1d0cab1643ff4a7e55488a7199c6616707f37d582f5c1872a7'

def validate(p,rows,wall=None):
    required={'approval','session_id','profile','route_sha256','expected_sequence','expected_pulses_us',
              'observer_ready','operator_hardware_unmoved','operator_no_jam','power_on','recovery_requested',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds','boot_id','baseline_source'}
    if set(p)!=required or p['profile']!=PROFILE or p['route_sha256']!=ROUTE_SHA:raise ValueError('Exact BE recovery plan required')
    if p['approval']!='attended-fixed-puppet-choreography-20261012':raise ValueError('Attended recovery required')
    if not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):raise ValueError('Invalid session ID')
    for k in ['observer_ready','operator_hardware_unmoved','operator_no_jam','power_on','recovery_requested','dual_view_pose_reviewed']:
        if p[k] is not True:raise ValueError('Missing recovery condition: '+k)
    if type(p['reviewed_at_unix_ms']) is not int or (wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000):raise ValueError('Review expired')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600:raise ValueError('Bounded session required')
    if not re.fullmatch('[a-f0-9-]{36}',p['boot_id']):raise ValueError('Boot ID required')
    if not rows or rows[0].get('route_sha256')!=BF_ROUTE_SHA:raise ValueError('BF recovery evidence required')
    if not any(r.get('event')=='recovery_complete' and r.get('recovered_reference') is True and r['state']['pulse_us']==START for r in rows):raise ValueError('Completed BF recovery required')
    last=rows[-1];s=last['state']
    if last['event']!='outputs_off' or last.get('normal_frame_stop') is not True:raise ValueError('Normal recovery stop required')
    if (s['pulse_us']!=START or p['expected_pulses_us']!=START or s['sequence']!=27897 or p['expected_sequence']!=27897 or s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']):raise ValueError('Unchanged BF reference required')


def run(d,emit,sleep=time.sleep):
    normal=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=ROUTE_SHA,state=d.adopt(START[:]),position_feedback=None,incident_locks_removed=False))
        visited=0
        while True:
            d.check()
            if d.host.action is None:
                d.wait(.03,sleep);continue
            action,seq=d.host.action;d.host.action=None
            if seq!=d.sequence:raise RuntimeError('Stale request; no retry')
            if action=='finish':
                emit(dict(event='clearance_complete',highest_stage=visited,recovered_reference=visited==len(TARGETS)-1,state=d.check()))
                normal=True;break
            if action!='demo' or visited>=len(TARGETS)-1:raise RuntimeError('One reviewed recovery edge only')
            d.targets=[d.pulses[:],TARGETS[visited+1][:]];d.cursor=0
            d.advance(1,emit,sleep);visited+=1
            emit(dict(event='clearance_pose_held',level=visited,state=d.check(),needs_dual_view_review=True,position_feedback=None))
    finally:
        emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),normal_frame_stop=normal,incident_locks_removed=False))

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
            self.plan=dict(p,tempo_step_us=4);self.host=host;self.clock=time.monotonic
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
