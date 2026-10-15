"""Attended height-difference measurement, NOT a completed rollover route.

Only tiger outputs, two bounded pitch excursions with separately reviewed
returns. No yaw exchange, inversion, audio, person motion or automatic replay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time

import story_midpoint_session as m

PROFILE='tiger-roll-height-probe-v1'
SOURCE='/tmp/puppet_choreography_continue_20261015_g.events.jsonl'
SOURCE_SHA='24f8c691bf227f727558fca7a548b488393e385c2a4f567fa83f5d895172b77f'
BOOT='7eea2c53-e104-45cf-88fe-439f1821e5d4'
START=m.score.START[:]


def pitch(head=0,rear=0):
    q=START[:];q[7]+=head;q[9]+=rear
    return q


TARGETS=[START,pitch(rear=-40),pitch(rear=-80),START,
         pitch(head=40),pitch(head=80),START]
ROUTE_SHA=hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()
FRAMES=[START[:]]+[q for a,b in zip(TARGETS,TARGETS[1:]) for q in m.transition_frames(a,b)]
RESUME_PROFILE='tiger-roll-height-resume-v1'
RESUME_SOURCE='/tmp/puppet_choreography_tiger_roll_20261015_a.events.jsonl'
RESUME_SHA='56b67d16f3638104d4d443272e6b30c5f28bbf324e5a30bdfffd4d60c5f586aa'
RESUME_TARGETS=[pitch(head=40),pitch(head=80),pitch(head=160),pitch(head=240),
                pitch(head=160),pitch(head=80),START]


def specification(profile):
    if profile==PROFILE:
        return SOURCE,SOURCE_SHA,37562,TARGETS
    if profile==RESUME_PROFILE:
        return RESUME_SOURCE,RESUME_SHA,37963,RESUME_TARGETS
    raise ValueError('Unknown fixed height trial')


def route_digest(targets):
    return hashlib.sha256(json.dumps(targets,separators=(',',':')).encode()).hexdigest()


def validate(p,raw,wall=None):
    source,sha,seq,targets=specification(p.get('profile'))
    if (p.get('approval')!=m.c.APPROVAL
            or p.get('expected_sequence')!=seq or p.get('expected_pulses_us')!=targets[0]
            or p.get('boot_id')!=BOOT or p.get('source_sha256')!=sha
            or p.get('route_sha256')!=route_digest(targets) or p.get('duration_seconds')!=240
            or any(p.get(k) is not True for k in ('observer_ready','dual_view_pose_reviewed','height_probe_only'))):
        raise ValueError('Only the reviewed post-show tiger height trial')
    stamp=p.get('reviewed_at_unix_ms')
    if type(stamp) is not int or stamp<=0 or (wall and not 0<=wall()*1000-stamp<120000):
        raise ValueError('Fresh host review required')
    if hashlib.sha256(raw).hexdigest()!=sha:
        raise ValueError('Source evidence changed')
    rows=[json.loads(line) for line in raw.splitlines()]
    s=rows[-1]['state']
    if (rows[-1]['event']!='outputs_off'
            or s['sequence']!=seq or s['pulse_us']!=targets[0] or s['enabled_mask']
            or s['armed'] or s['pending'] or s['faults']):
        raise ValueError('Prior reference changed')
    if p['profile']==PROFILE:
        if rows[-1].get('normal_frame_stop') is not True or not any(r['event']=='story_complete' for r in rows):
            raise ValueError('Prior show did not complete normally')
    else:
        # Exact completed four-edge prefix, stopped during static review, not
        # a stalled movement. Fresh pose comparison remains a separate check.
        completed=[r for r in rows if r['event']=='probe_complete']
        if ([r['axis'] for r in completed]!=[1,2,3,4]
                or [r['state']['pulse_us'] for r in completed]!=TARGETS[1:5]
                or rows[-1].get('normal_frame_stop') is not False
                or rows[-2].get('event')!='hold_alive' or rows[-2].get('awaiting')!='review_4'
                or rows[-2]['state']['pulse_us']!=targets[0]
                or rows[-2]['state']['sequence']!=seq):
            raise ValueError('Not the recorded static-review timeout')
    frames=[targets[0]]+[q for a,b in zip(targets,targets[1:]) for q in m.transition_frames(a,b)]
    for q in frames:
        if any(q[i]!=START[i] for i in (0,1,2,3,4,5,6,8)):
            raise ValueError('Only tiger pitch axes may change')
        if any(not 500+lo*2000/270<=q[i]<=500+hi*2000/270
               for i,(lo,hi) in enumerate(m.DEGREE_LIMITS)):
            raise ValueError('Outside inset limits')
    if any(max(abs(x-y) for x,y in zip(a,b))>3 for a,b in zip(frames,frames[1:])):
        raise ValueError('Step too large')


class HeightProbe(m.MidpointSession):
    def __init__(self,r,p,host,*,source_raw,clock=time.monotonic,wall=None,
                 motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel'):
        validate(p,source_raw,wall)
        _,_,sequence,targets=specification(p['profile'])
        m.c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=dict(p,tempo_step_us=3);self.host=host;self.clock=clock
        self.deadline=clock()+240;self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=targets[0][:];self.sequence=sequence;self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.own=960;self.frame_index=0
        self.frames=[targets[0][:]]+[q for a,b in zip(targets,targets[1:]) for q in m.transition_frames(a,b)]
        self.check()

    def adopt(self,q):
        if self.frame_index>=len(self.frames) or q!=self.frames[self.frame_index]:
            raise RuntimeError('Only the next fixed height frame, once')
        state=super().adopt(q);self.frame_index+=1
        return state


def run(d,emit,sleep=time.sleep):
    profile=d.plan.get('profile',PROFILE)
    _,_,_,targets=specification(profile)
    normal=False
    try:
        emit(dict(event='reference_held',profile=profile,route_sha256=route_digest(targets),
                  state=d.adopt(targets[0][:]),position_feedback=None,full_rollover=False))
        d.phase='height_probe'
        for edge,(a,b) in enumerate(zip(targets,targets[1:]),1):
            m.await_action(d,emit,'probe_'+str(edge),sleep)
            for index,q in enumerate(m.transition_frames(a,b)):
                d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
                if index and d.clock()-d.last_start>.06:
                    raise RuntimeError('Scheduling stalled; no catch-up')
                d.next_command=q
                emit(dict(event='probe_step',edge=edge,state=d.adopt(q)))
            emit(dict(event='probe_complete',axis=edge,state=d.check()))
            m.await_action(d,emit,'review_'+str(edge),sleep)
            emit(dict(event='path_reviewed',axis=edge,state=d.check()))
        d.wait(.5,sleep)
        emit(dict(event='height_probe_complete',state=d.check(),full_rollover=False))
        normal=True
    finally:
        emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),
                  normal_frame_stop=normal,full_rollover=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true')
    args=parser.parse_args();raw=args.plan.read_bytes();p=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:
        raise ValueError('Plan changed')
    source_path,_,_,targets=specification(p.get('profile'))
    source=Path(source_path).read_bytes();validate(p,source)
    if not re.fullmatch('[a-z0-9-]{1,80}',p.get('session_id','')):
        raise ValueError('Invalid session identity')
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,targets=targets,mask=960,full_rollover=False)));return
    if (Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=BOOT
            or json.loads(Path('/run/shadow-pwm-loaded.json').read_text()).get('sha256')!=m.IMAGE_SHA):
        raise ValueError('Boot/image changed before MMIO')
    with args.plan.with_suffix('.used').open('x') as f:f.write('one height trial\n')
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=m.c.HostControl(sys.stdin.fileno())
    print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    registers=m.c.Registers()
    try:
        d=HeightProbe(registers,p,host,source_raw=source)
        with args.plan.with_suffix('.events.jsonl').open('x') as log:run(d,m.rehearsal_emitter(log))
    finally:registers.close()


if __name__=='__main__':main()
