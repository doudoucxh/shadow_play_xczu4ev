"""One attended continuation of the recorded first edge, then gated audio.

The first-edge log is command provenance, not shaft feedback. The host must
separately compare new dual views before requesting execution and each edge.
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

PROFILE = 'story-midpoint-continue-v1'
SOURCE = '/tmp/puppet_choreography_first_edge_20261015_d.events.jsonl'
SOURCE_SHA = '88a1d553fd41c27313fe93b0e494ab53dd30746ebdad0ddc6f2279f72a6662e1'
BOOT = '7eea2c53-e104-45cf-88fe-439f1821e5d4'


def validate(p, raw, wall=None):
    if (p.get('profile') != PROFILE or p.get('expected_sequence') != 34129
            or p.get('expected_pulses_us') != m.TARGETS[1]
            or p.get('boot_id') != BOOT or p.get('source_sha256') != SOURCE_SHA
            or p.get('observer_ready') is not True
            or p.get('dual_view_pose_reviewed') is not True
            or p.get('endpoint_comparison') != 'no_obvious_change_in_new_dual_views'
            or p.get('duration_seconds') != 240
            or p.get('story_route_sha256') != m.score.check_envelope()['route_sha256']):
        raise ValueError('Only the freshly reviewed recorded first-edge endpoint')
    reviewed=p.get('reviewed_at_unix_ms')
    if type(reviewed) is not int or reviewed<=0:
        raise ValueError('Host review timestamp required')
    # Windows enforces freshness before dispatch. Board wall time is not synced.
    if wall is not None and not 0<=wall()*1000-reviewed<120000:
        raise ValueError('Review expired')
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('First-edge evidence changed')
    rows=[json.loads(line) for line in raw.splitlines()]
    steps=[r for r in rows if r['event']=='probe_step']
    frames=m.transition_frames(m.MIDPOINT,m.TARGETS[1])
    if (len(steps)!=100 or [r['state']['pulse_us'] for r in steps]!=frames
            or rows[-1]['event']!='outputs_off'
            or rows[-1].get('normal_frame_stop') is not True
            or rows[-2]['event']!='first_edge_complete'):
        raise ValueError('First edge did not finish normally')
    off=rows[-1]['state'];held=rows[-2]['state']
    if (off['sequence']!=34129 or off['armed'] or off['enabled_mask']
            or held['sequence']!=34128 or not held['armed'] or held['enabled_mask']!=1023
            or any(s['pulse_us']!=m.TARGETS[1] or s['faults'] or s['pending'] for s in (off,held))):
        raise ValueError('Endpoint evidence mismatch')
    # Reuse the complete fixed score's range and increment checks, without
    # treating this reference as another operator midpoint confirmation.
    m.validate(dict(profile=m.PROFILE,expected_pulses_us=m.MIDPOINT,
                    expected_sequence=34027,operator_midpoint_confirmed=True,
                    observer_ready=True,dual_view_pose_reviewed=True,
                    duration_seconds=240,story_route_sha256=p['story_route_sha256']))


class ContinuationSession(m.MidpointSession):
    def __init__(self, registers, plan, host, *, source_raw, clock=time.monotonic,
                 wall=None, motion_inhibit_paths=None,
                 cancel_path='/run/shadow-pwm-recovery-cancel'):
        validate(plan,source_raw,wall)
        m.c.PwmDevice.__init__(self,registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=dict(plan,tempo_step_us=3)
        self.host=host;self.clock=clock;self.deadline=clock()+240
        self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=m.TARGETS[1][:];self.sequence=34129;self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.own=1023
        self.check()


def run(d,emit,audio,sleep=time.sleep):
    handed_to_story=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,state=d.adopt(m.TARGETS[1][:]),
                  source_sha256=SOURCE_SHA,position_feedback=None))
        d.phase='transition'
        for edge in range(2,5):
            m.await_action(d,emit,'probe_'+str(edge),sleep)
            for index,q in enumerate(m.transition_frames(m.TARGETS[edge-1],m.TARGETS[edge])):
                d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
                if index and d.clock()-d.last_start>.06:
                    raise RuntimeError('Transition stalled; no catch-up')
                d.next_command=q
                emit(dict(event='probe_step',edge=edge,state=d.adopt(q)))
            emit(dict(event='probe_complete',axis=edge,state=d.check()))
            m.await_action(d,emit,'review_'+str(edge),sleep)
            emit(dict(event='path_reviewed',axis=edge,state=d.check()))
        d.wait(.03,sleep);d.next_command=m.score.START[:]
        handed_to_story=True
        # This requires a new demo action at the ACTIVE start sequence.
        # No intermediate OFF/re-arm or automatic full-show playback.
        m.story.run(d,emit,audio,sleep)
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
    source_raw=Path(SOURCE).read_bytes();validate(p,source_raw)
    if not re.fullmatch('[a-z0-9-]{1,80}',p.get('session_id','')):
        raise ValueError('Invalid session identity')
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,remaining_targets=m.TARGETS[2:])));return
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=BOOT:
        raise ValueError('Boot changed')
    if json.loads(Path('/run/shadow-pwm-loaded.json').read_text()).get('sha256')!=m.IMAGE_SHA:
        raise ValueError('Wrong FPGA image before MMIO')
    with args.plan.with_suffix('.used').open('x') as f:f.write('one continuation\n')
    _,_,m.sound.CLIP,m.sound.CLIP_SHA=m.story.MODES['full']
    audio=m.sound.AudioClip()
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=m.c.HostControl(sys.stdin.fileno())
    print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    registers=m.c.Registers()
    try:
        device=ContinuationSession(registers,p,host,source_raw=source_raw)
        with args.plan.with_suffix('.events.jsonl').open('x') as log:
            run(device,m.rehearsal_emitter(log),audio)
    finally:registers.close();audio.close()


if __name__=='__main__':main()
