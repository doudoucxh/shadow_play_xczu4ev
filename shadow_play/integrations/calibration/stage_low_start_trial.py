"""Fixed initial-pose trial: lower Wu Song arms, then lower tiger rear at right.
New geometry and combined poses remain candidates until visual review.
"""
import hashlib
import json
import time
from pathlib import Path

PROFILE = 'stage-low-start-v1'
START = [1515,1372,1515,1514,1506,1660,1510,1275,1550,1640]
def pose(a,b,c,d): return START[:6]+[a,b,c,d]
LOW=[1515,1252,1515,1594,1506,1720]
TARGETS=[START,
 [1515,1312,1515,1554,1506,1690]+START[6:],
 LOW+START[6:],
 LOW+[1570,1275,1610,1640],
 LOW+[1630,1275,1670,1640],
 LOW+[1630,1275,1670,1680],
 LOW+[1630,1275,1670,1720]]
ROUTE_SHA=hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()

def validate(p, rows, wall=None):
    required={'approval','session_id','profile','route_sha256','expected_sequence',
              'expected_pulses_us','observer_ready','operator_tiger_unmoved',
              'person_rods_shortened_mm','operator_axes_unmoved','power_on',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds',
              'boot_id','baseline_source'}
    if set(p)!=required or p['profile']!=PROFILE or p['route_sha256']!=ROUTE_SHA:
        raise ValueError('Exact fixed tiger trial required')
    if p['approval']!='attended-fixed-puppet-choreography-20261012':raise ValueError('Attended trial required')
    import re
    if not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):raise ValueError('Invalid ID')
    if not re.fullmatch('[a-f0-9-]{36}',p['boot_id']):raise ValueError('Invalid boot')
    for k in ['observer_ready','operator_tiger_unmoved','operator_axes_unmoved','power_on','dual_view_pose_reviewed']:
        if p[k] is not True:raise ValueError('Missing condition: '+k)
    if p['person_rods_shortened_mm']!={'head':5,'right_hand':5}:raise ValueError('Geometry receipt required')
    if type(p['reviewed_at_unix_ms']) is not int or (wall and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000):raise ValueError('Expired review')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600:raise ValueError('Bounded session required')
    if not rows or rows[0].get('profile')!='tiger-continuous-v1' or rows[0].get('route_sha256')!='e5371475e81aea491c55bb9af9a0cafd2a149eb49b3a381bfcb8e586f85fa822':raise ValueError('BJ lineage required')
    if not any(r.get('event')=='tiger_continuous_complete' for r in rows):raise ValueError('Incomplete baseline')
    last=rows[-1];s=last['state']
    if last['event']!='outputs_off' or last.get('normal_frame_stop') is not True:raise ValueError('Normal stop required')
    if (s['pulse_us']!=START or p['expected_pulses_us']!=START or s['sequence']!=31748 or p['expected_sequence']!=31748 or s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']):raise ValueError('BJ reference changed')
    for q in TARGETS:
        for value,lo,hi in zip(q,[10,95,10,50,70,50,50,100,70,50],[260,260,260,170,260,170,190,190,200,170]):
            if not 500+lo*2000/270<=value<=500+hi*2000/270:raise ValueError('Outside inset envelope')

def run(d,emit,sleep=time.sleep):
    normal=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=ROUTE_SHA,state=d.adopt(START[:]),position_feedback=None,incident_locks_removed=False))
        stage=0
        while True:
            d.check()
            if d.host.action is None:d.wait(.03,sleep);continue
            action,seq=d.host.action;d.host.action=None
            if seq!=d.sequence:raise RuntimeError('Stale command')
            if action=='finish':normal=True;break
            if action!='demo':raise RuntimeError('Fixed next stage only')
            if stage<len(TARGETS)-1:
                d.plan['tempo_step_us']=8
                d.targets=[d.pulses[:],TARGETS[stage+1][:]];d.cursor=0
                d.advance(1,emit,sleep);stage+=1
                emit(dict(event='low_start_pose_held',level=stage,state=d.check(),needs_dual_view_review=True))
            else:raise RuntimeError('No repeat')
    finally:
        emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),normal_frame_stop=normal,incident_locks_removed=False))

def main():
    # Reuse the transport/watchdog implementation with a tiger-only mask.
    import hand_crossing_session_20261014_r36 as h
    c=h.c
    import argparse, signal, sys
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true');args=parser.parse_args()
    raw=args.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Plan changed')
    # Windows validates freshness against its own camera/review clock. Board RTC
    # is not synchronized; comparing that clock with host timestamps is invalid.
    p=json.loads(raw);validate(p,c.checked_log(p['baseline_source']))
    if not args.execute_attended_fixed_choreography:print(json.dumps(dict(dry_run=True,mask=1023,targets=TARGETS)));return
    class TigerSession(c.ChoreographySession):
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
            self.own=1023;self.indices=range(10);self.targets=[]
        def check(self):
            if self.boot.read_text().strip()!=p['boot_id']:raise RuntimeError('Boot changed')
            return super().check()
    def interrupt(*unused):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(sys.stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=TigerSession(r,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:run(d,c.motion_emitter(log))
    finally:r.close()

if __name__=='__main__':main()
