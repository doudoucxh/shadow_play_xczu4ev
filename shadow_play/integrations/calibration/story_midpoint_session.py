"""One attended midpoint-to-opening trial, then reviewed full audio rehearsal.

The operator's new midpoint report is the reference, not the old BP registers.
Four fixed transition edges require host review. Incident files remain intact.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import signal
import sys
import time

import puppet_choreography_session as c
import story_audio_session_v3 as story
import story_motion_v3_candidate as score
import tiger_audio_segment as sound

PROFILE = 'story-midpoint-v1'
IMAGE_SHA = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
MIDPOINT = [1500]*10
TARGETS = [[round(a+(b-a)*i/4) for a,b in zip(MIDPOINT,score.START)] for i in range(5)]
DEGREE_LIMITS = [(10,260),(95,260),(10,260),(50,170),(70,260),
                 (50,170),(50,190),(100,190),(70,200),(50,170)]


def transition_frames(start, target):
    # Two seconds per quarter; bounded velocity and zero end velocity.
    return [[round(a+(b-a)*(.5-.5*math.cos(math.pi*i/100)))
             for a,b in zip(start,target)] for i in range(1,101)]


def validate(p):
    if p.get('profile') != PROFILE or p.get('expected_pulses_us') != MIDPOINT:
        raise ValueError('Only a newly operator-confirmed ten-axis midpoint is accepted')
    for key in ('operator_midpoint_confirmed', 'observer_ready', 'dual_view_pose_reviewed'):
        if p.get(key) is not True:
            raise ValueError('Missing '+key)
    if type(p.get('expected_sequence')) is not int or not 0 <= p['expected_sequence'] < 2**32:
        raise ValueError('Current sequence required')
    if p.get('story_route_sha256') != score.check_envelope()['route_sha256']:
        raise ValueError('Score changed')
    if p.get('duration_seconds') != 240:
        raise ValueError('Bounded session required')
    for a,b in zip(TARGETS,TARGETS[1:]):
        previous=a
        for q in transition_frames(a,b):
            if max(abs(x-y) for x,y in zip(previous,q))>3:
                raise ValueError('Transition exceeds three microseconds per frame')
            previous=q
    for q in TARGETS+[score.sample(i*.02) for i in range(math.ceil(score.DURATION/.02)+1)]:
        if any(not 500+lo*2000/270 <= v <= 500+hi*2000/270
               for v,(lo,hi) in zip(q,DEGREE_LIMITS)):
            raise ValueError('Outside axis inset limits')


def rehearsal_emitter(log):
    last=-math.inf
    def emit(row):
        nonlocal last
        now=time.monotonic()
        row=dict(row,board_monotonic_seconds=now)
        log.write(json.dumps(row)+'\n')
        # Every command stays in the board log. Dense keyframes must not
        # repeatedly block the 115200-baud stdout during the motion loop.
        dense=row['event'] in ('probe_step','timeline_checkpoint')
        if not dense or now-last>=.5:
            log.flush();print(json.dumps(row),flush=True);last=now
    return emit


class MidpointSession(c.ChoreographySession):
    def __init__(self, registers, plan, host, *, clock=time.monotonic,
                 motion_inhibit_paths=None, cancel_path='/run/shadow-pwm-recovery-cancel'):
        validate(plan)
        c.PwmDevice.__init__(self, registers, motion_inhibit_paths=motion_inhibit_paths)
        self.plan=dict(plan,tempo_step_us=3)
        self.host=host;self.clock=clock;self.deadline=clock()+240
        self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=MIDPOINT[:];self.sequence=plan['expected_sequence'];self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.own=1023
        self.check()

    def check(self):
        if self.clock()>=self.deadline:
            raise RuntimeError('Session expired')
        return super().check()


def await_action(d, emit, expected, sleep):
    report=0
    while True:
        d.check()
        if d.host.action is not None:
            action,sequence=d.host.action;d.host.action=None
            if action!=expected or sequence!=d.sequence:
                raise RuntimeError('Unexpected or stale review action')
            return
        if d.clock()>=report:
            emit(dict(event='hold_alive',awaiting=expected,state=d.check()))
            report=d.clock()+.5
        d.wait(.02,sleep)


def run(d, emit, audio, sleep=time.sleep):
    handed_to_story=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,state=d.adopt(MIDPOINT[:]),
                  reference_source='operator_confirmed_after_ten_single_midpoint_commands',
                  position_feedback=None))
        d.phase='transition'
        for edge,(a,b) in enumerate(zip(TARGETS,TARGETS[1:]),1):
            await_action(d,emit,'probe_'+str(edge),sleep)
            for index,q in enumerate(transition_frames(a,b)):
                d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
                if d.clock()-d.last_start>.06:
                    # Waiting for visual review is allowed only before edge start.
                    if index != 0:
                        raise RuntimeError('Transition stalled; no catch-up')
                d.next_command=q
                emit(dict(event='probe_step',edge=edge,state=d.adopt(q)))
            emit(dict(event='probe_complete',axis=edge,state=d.check()))
            await_action(d,emit,'review_'+str(edge),sleep)
            emit(dict(event='path_reviewed',axis=edge,state=d.check()))
        d.wait(.03,sleep)
        d.next_command=score.START[:]
        handed_to_story=True
        story.run(d,emit,audio,sleep)
    finally:
        if not handed_to_story:
            try:emit(dict(event='outputs_off',state=d.off(),normal_frame_stop=False))
            finally:audio.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true')
    args=parser.parse_args();raw=args.plan.read_bytes();p=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:
        raise ValueError('Plan changed')
    validate(p)
    if not re.fullmatch('[a-z0-9-]{1,80}',p.get('session_id','')) or not re.fullmatch('[a-f0-9-]{36}',p.get('boot_id','')):
        raise ValueError('Invalid session/boot identity')
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,transition_targets=TARGETS,score=score.check_envelope())));return
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=p['boot_id']:
        raise ValueError('Boot changed')
    marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    if marker.get('sha256')!=IMAGE_SHA:
        raise ValueError('Expected ten-servo G13 FPGA image before MMIO')
    with args.plan.with_suffix('.used').open('x') as receipt:receipt.write('one use\n')
    _,_,sound.CLIP,sound.CLIP_SHA=story.MODES['full']
    audio=sound.AudioClip()  # Audio dependency failure occurs before motor enable.
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(sys.stdin.fileno())
    print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    registers=c.Registers()
    try:
        d=MidpointSession(registers,p,host)
        with Path('/tmp/puppet-choreography-'+p['session_id']+'.jsonl').open('x') as log:
            run(d,rehearsal_emitter(log),audio)
    finally:registers.close();audio.close()


if __name__=='__main__':main()
