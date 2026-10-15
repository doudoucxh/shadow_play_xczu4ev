"""One attended replay from the recorded tiger height sweep, with gated entry.

Source records establish command lineage, not shaft position. Fresh dual-view
comparison is required separately; incident files and all stop checks remain.
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

PROFILE='story-replay-after-height-v1'
SOURCE='/tmp/puppet_choreography_tiger_roll_20261015_c.events.jsonl'
SOURCE_SHA='48ce4387e4a84485606ca61c027b271f8e0aba5d53ba4340cba12ca0097d97c4'
SHOW='/tmp/puppet_choreography_continue_20261015_g.events.jsonl'
SHOW_SHA='24f8c691bf227f727558fca7a548b488393e385c2a4f567fa83f5d895172b77f'
BOOT='7eea2c53-e104-45cf-88fe-439f1821e5d4'
REFERENCE=m.score.START[:]
REFERENCE[7]=1330
ENTRY=[REFERENCE[:]]+m.transition_frames(REFERENCE,m.score.START)


def validate(p,raw,show_raw,wall=None):
    if (p.get('profile')!=PROFILE or p.get('approval')!=m.c.APPROVAL
            or p.get('expected_sequence')!=38465 or p.get('expected_pulses_us')!=REFERENCE
            or p.get('boot_id')!=BOOT or p.get('source_sha256')!=SOURCE_SHA
            or p.get('show_sha256')!=SHOW_SHA or p.get('story_mode')!='full'
            or p.get('duration_seconds')!=240
            or p.get('observer_ready') is not True or p.get('dual_view_pose_reviewed') is not True
            or p.get('endpoint_comparison')!='no_obvious_change_in_new_dual_views'
            or p.get('story_route_sha256')!=m.score.check_envelope()['route_sha256']):
        raise ValueError('Only the reviewed height endpoint and previously completed full score')
    stamp=p.get('reviewed_at_unix_ms')
    if type(stamp) is not int or stamp<=0 or (wall and not 0<=wall()*1000-stamp<120000):
        raise ValueError('Fresh host review required')
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA or hashlib.sha256(show_raw).hexdigest()!=SHOW_SHA:
        raise ValueError('Source evidence changed')
    rows=[json.loads(line) for line in raw.splitlines()]
    phases=[r for r in rows if r['event']=='probe_complete']
    expected=[]
    for v in (1410,1490,1410,1330):
        q=REFERENCE[:];q[7]=v;expected.append(q)
    off=rows[-1];s=off['state'];held=rows[-2]
    if ([r['axis'] for r in phases]!=[1,2,3,4]
            or [r['state']['pulse_us'] for r in phases]!=expected
            or off['event']!='outputs_off' or off.get('normal_frame_stop') is not False
            or s['sequence']!=38465 or s['pulse_us']!=REFERENCE or s['enabled_mask']
            or s['armed'] or s['faults'] or s['pending']
            or held.get('event')!='hold_alive' or held.get('awaiting')!='review_4'
            or held['state']['pulse_us']!=REFERENCE or held['state']['sequence']!=38465):
        raise ValueError('Not the recorded static stop after returning to 1330 us')
    show=[json.loads(line) for line in show_raw.splitlines()]
    if (not any(r['event']=='story_complete' for r in show)
            or show[-1]['event']!='outputs_off' or show[-1].get('normal_frame_stop') is not True
            or show[-1]['state']['sequence']!=37562
            or show[-1]['state']['pulse_us']!=m.score.START):
        raise ValueError('Prior full score did not finish normally')
    for q in ENTRY:
        if any(q[i]!=REFERENCE[i] for i in range(10) if i!=7):raise ValueError('Only head pitch entry')
        if any(not 500+lo*2000/270<=q[i]<=500+hi*2000/270 for i,(lo,hi) in enumerate(m.DEGREE_LIMITS)):
            raise ValueError('Entry outside inset bounds')
    if any(max(abs(x-y) for x,y in zip(a,b))>3 for a,b in zip(ENTRY,ENTRY[1:])):
        raise ValueError('Entry step too large')


class ReplaySession(m.MidpointSession):
    def __init__(self,r,p,host,*,source_raw,show_raw,clock=time.monotonic,wall=None,
                 motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel'):
        validate(p,source_raw,show_raw,wall)
        m.c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=dict(p,tempo_step_us=3);self.host=host;self.clock=clock
        self.deadline=clock()+240;self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=REFERENCE[:];self.sequence=38465;self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.own=1023;self.entry_index=0
        self.entry_complete=False
        self.check()

    def adopt(self,q):
        if not self.entry_complete:
            if self.entry_index>=len(ENTRY) or q!=ENTRY[self.entry_index]:
                raise RuntimeError('Only the next fixed entry frame')
        result=super().adopt(q)
        if not self.entry_complete:self.entry_index+=1
        return result


def run(d,emit,audio,sleep=time.sleep):
    handed=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,state=d.adopt(REFERENCE[:]),position_feedback=None))
        d.phase='entry'
        m.await_action(d,emit,'probe_1',sleep)
        for index,q in enumerate(ENTRY[1:]):
            d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
            if index and d.clock()-d.last_start>.06:raise RuntimeError('Entry stalled; no catch-up')
            d.next_command=q
            emit(dict(event='probe_step',edge=1,state=d.adopt(q)))
        emit(dict(event='probe_complete',axis=1,state=d.check()))
        m.await_action(d,emit,'review_1',sleep)
        emit(dict(event='path_reviewed',axis=1,state=d.check()))
        d.entry_complete=True
        d.wait(.03,sleep);d.next_command=m.score.START[:]
        handed=True
        m.story.run(d,emit,audio,sleep)
    finally:
        if not handed:
            try:emit(dict(event='outputs_off',state=d.off(),normal_frame_stop=False))
            finally:audio.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('plan',type=Path)
    p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('--execute-attended-fixed-choreography',action='store_true');args=p.parse_args()
    raw=args.plan.read_bytes();plan=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Plan changed')
    source=Path(SOURCE).read_bytes();show=Path(SHOW).read_bytes();validate(plan,source,show)
    if not re.fullmatch('[a-z0-9-]{1,80}',plan.get('session_id','')):raise ValueError('Invalid session')
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,entry=[REFERENCE,m.score.START],duration=m.score.DURATION)));return
    if (Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=BOOT
            or json.loads(Path('/run/shadow-pwm-loaded.json').read_text()).get('sha256')!=m.IMAGE_SHA):
        raise ValueError('Boot/image changed before MMIO')
    with args.plan.with_suffix('.used').open('x') as f:f.write('one attended replay\n')
    _,_,m.sound.CLIP,m.sound.CLIP_SHA=m.story.MODES['full'];audio=m.sound.AudioClip()
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=m.c.HostControl(sys.stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=m.c.Registers()
    try:
        d=ReplaySession(r,plan,host,source_raw=source,show_raw=show)
        with args.plan.with_suffix('.events.jsonl').open('x') as log:run(d,m.rehearsal_emitter(log),audio)
    finally:r.close();audio.close()


if __name__=='__main__':main()
