"""Attended local head-yaw comparison from the completed pitch probe; no depth claim."""
import argparse,hashlib,json,re,signal,sys,time
from pathlib import Path
import story_midpoint_session as m

PROFILE='person-head-lateral-probe-v1'
SOURCE='/tmp/puppet_choreography_head_contact_20261015_i.events.jsonl'
SOURCE_SHA='3e0cdf9ff498c3f66d75ea4aae9aea183b8b8f94c8d43869926c25039162681e'
BOOT='7eea2c53-e104-45cf-88fe-439f1821e5d4'
START=[1470,1212,1425,1554,1416,1740,1730,1250,1770,1740]
TARGETS=[START[:]]
for v in (1465,):
    q=START[:];q[2]=v;TARGETS.append(q)
FRAMES=[START[:]]+[q for a,b in zip(TARGETS,TARGETS[1:]) for q in m.transition_frames(a,b)]
ROUTE_SHA=hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()


def validate(p,raw,wall=None):
    if (p.get('profile')!=PROFILE or p.get('approval')!=m.c.APPROVAL
            or p.get('expected_sequence')!=41790 or p.get('expected_pulses_us')!=START
            or p.get('source_sha256')!=SOURCE_SHA or p.get('route_sha256')!=ROUTE_SHA
            or p.get('boot_id')!=BOOT or p.get('duration_seconds')!=240
            or p.get('observer_ready') is not True or p.get('dual_view_pose_reviewed') is not True):
        raise ValueError('Only the reviewed post-pitch local yaw comparison')
    stamp=p.get('reviewed_at_unix_ms')
    if type(stamp) is not int or stamp<=0 or (wall and not 0<=wall()*1000-stamp<120000):
        raise ValueError('Fresh host review required')
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('Evidence changed')
    rows=[json.loads(line) for line in raw.splitlines()];last=rows[-1];s=last['state']
    if (last['event']!='outputs_off' or last.get('normal_frame_stop') is not True
            or not any(r['event']=='head_pitch_comparison_complete' for r in rows)
            or s['sequence']!=41790 or s['pulse_us']!=START or s['armed'] or s['enabled_mask']
            or s['faults'] or s['pending']):raise ValueError('Not the completed pitch comparison endpoint')
    for q in FRAMES:
        if any(q[i]!=START[i] for i in range(10) if i!=2):raise ValueError('Only head yaw changes')
        if any(not 500+lo*2000/270<=q[i]<=500+hi*2000/270 for i,(lo,hi) in enumerate(m.DEGREE_LIMITS)):
            raise ValueError('Outside inset bounds')


class HeadProbe(m.MidpointSession):
    def __init__(self,r,p,host,*,source_raw,clock=time.monotonic,wall=None,
                 motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel'):
        validate(p,source_raw,wall);m.c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=dict(p,tempo_step_us=3);self.host=host;self.clock=clock;self.deadline=clock()+240
        self.cancel=Path(cancel_path);self.hashes=self.lock_hashes();self.pulses=START[:]
        self.sequence=41790;self.mask=0;self.inside=False;self.failed=False
        self.last_start=None;self.next_command=None;self.phase='resume';self.own=63;self.cursor=0
        self.check()
    def adopt(self,q):
        if self.cursor>=len(FRAMES) or q!=FRAMES[self.cursor]:raise RuntimeError('Only next fixed yaw frame')
        state=super().adopt(q);self.cursor+=1;return state


def reviewed_or_finish(d,emit,edge,sleep):
    report=0
    while True:
        d.check()
        if d.host.action is not None:
            action,seq=d.host.action;d.host.action=None
            if seq!=d.sequence or action not in ('review_'+str(edge),'finish'):
                raise RuntimeError('Unexpected or stale review')
            return action
        if d.clock()>=report:
            emit(dict(event='hold_alive',awaiting='review_'+str(edge),finish_available=True,state=d.check()))
            report=d.clock()+.5
        d.wait(.02,sleep)


def run(d,emit,sleep=time.sleep):
    normal=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,state=d.adopt(START[:]),position_feedback=None))
        d.phase='head_yaw'
        for edge,(a,b) in enumerate(zip(TARGETS,TARGETS[1:]),1):
            m.await_action(d,emit,'probe_'+str(edge),sleep)
            for i,q in enumerate(m.transition_frames(a,b)):
                d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
                if i and d.clock()-d.last_start>.06:raise RuntimeError('Scheduler stalled')
                d.next_command=q;emit(dict(event='probe_step',edge=edge,state=d.adopt(q)))
            emit(dict(event='probe_complete',axis=edge,state=d.check()))
            decision=reviewed_or_finish(d,emit,edge,sleep)
            emit(dict(event='path_reviewed',axis=edge,decision=decision,state=d.check()))
            if decision=='finish':break
        emit(dict(event='head_lateral_comparison_complete',state=d.check(),cloth_distance_measured=False))
        normal=True
    finally:emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),normal_frame_stop=normal))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true');args=parser.parse_args()
    raw=args.plan.read_bytes();p=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Plan changed')
    source=Path(SOURCE).read_bytes();validate(p,source)
    if not re.fullmatch('[a-z0-9-]{1,80}',p.get('session_id','')):raise ValueError('Invalid session')
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,targets=TARGETS,mask=63)));return
    if (Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=BOOT
            or json.loads(Path('/run/shadow-pwm-loaded.json').read_text()).get('sha256')!=m.IMAGE_SHA):
        raise ValueError('Boot/image changed before MMIO')
    with args.plan.with_suffix('.used').open('x') as f:f.write('one head lateral comparison\n')
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=m.c.HostControl(sys.stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=m.c.Registers()
    try:
        d=HeadProbe(r,p,host,source_raw=source)
        with args.plan.with_suffix('.events.jsonl').open('x') as log:run(d,m.rehearsal_emitter(log))
    finally:r.close()


if __name__=='__main__':main()
