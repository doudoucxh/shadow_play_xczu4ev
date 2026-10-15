"""Limited attended trial: midpoint hold, ONE fixed edge, then OFF.

No audio, no full-show branch, no second edge or automatic return.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import story_midpoint_session as m

PROFILE = 'story-midpoint-first-edge-v1'
FRAMES = [m.MIDPOINT[:]] + m.transition_frames(m.MIDPOINT,m.TARGETS[1])


class FirstEdgeDevice(m.MidpointSession):
    def __init__(self, registers, plan, host, **kwargs):
        if plan.get('profile')!=PROFILE or plan.get('first_edge_only') is not True:
            raise ValueError('First-edge-only authorization required')
        internal=dict(plan,profile=m.PROFILE,duration_seconds=240)
        super().__init__(registers,internal,host,**kwargs)
        self.deadline=self.clock()+45
        self.frame_index=0

    def adopt(self,pulses):
        if self.frame_index>=len(FRAMES) or pulses!=FRAMES[self.frame_index]:
            raise RuntimeError('Only next fixed first-edge frame; no full show or repeat')
        state=super().adopt(pulses)
        self.frame_index+=1
        return state


def run(device,emit,sleep=time.sleep):
    complete=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,state=device.adopt(FRAMES[0])))
        device.phase='transition'
        m.await_action(device,emit,'probe_1',sleep)
        for index,q in enumerate(FRAMES[1:]):
            device.wait(max(0,.02-(device.clock()-device.last_start)),sleep)
            if index and device.clock()-device.last_start>.06:
                raise RuntimeError('First-edge scheduling stalled; no catch-up')
            device.next_command=q
            emit(dict(event='probe_step',index=index,state=device.adopt(q)))
        device.wait(1,sleep)
        emit(dict(event='first_edge_complete',state=device.check(),full_show_executed=False))
        complete=True
    finally:
        emit(dict(event='outputs_off',state=device.stop_after_frame() if complete else device.off(),
                  normal_frame_stop=complete,full_show_executed=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true')
    args=parser.parse_args();raw=args.plan.read_bytes();p=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:
        raise ValueError('Plan changed')
    if p.get('profile')!=PROFILE or p.get('first_edge_only') is not True:
        raise ValueError('Wrong scope')
    m.validate(dict(p,profile=m.PROFILE,duration_seconds=240))
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,frames=len(FRAMES),target=FRAMES[-1],audio=False)));return
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=p['boot_id']:
        raise ValueError('Boot changed')
    if json.loads(Path('/run/shadow-pwm-loaded.json').read_text()).get('sha256')!=m.IMAGE_SHA:
        raise ValueError('Wrong FPGA image')
    with args.plan.with_suffix('.used').open('x') as f:f.write('first edge only\n')
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=m.c.HostControl(sys.stdin.fileno())
    print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    registers=m.c.Registers()
    try:
        device=FirstEdgeDevice(registers,p,host)
        with args.plan.with_suffix('.events.jsonl').open('x') as log:
            run(device,m.rehearsal_emitter(log))
    finally:registers.close()


if __name__=='__main__':main()
