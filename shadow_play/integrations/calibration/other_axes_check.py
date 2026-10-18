"""One requested small single-axis check, with separate review between axes.

This finite series starts only from the actual OFF1280 record. It cannot run
axis 8, initialize all axes, change targets, or proceed to another axis itself.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import signal
import sys
import time

from initial_pose_model import validate_pulses
from servo_pwm_device import PwmDevice, Registers
from v20_first_direction import FirstDirectionDevice, HostLease, IMAGE, MIDPOINT, PREFIX, digest

SCHEMA='attended-other-axes-check-v1'
ORDER=(9,10,7,1,2,3,4,5,6)
BOOT='8b5372c2-00de-459e-ad96-371ec5ea0ef9'
BOARD='/run/media/mmcblk0p2/piying/other-axes-check-20261019'
FIRST_LOG='/run/media/mmcblk0p2/piying/v20-head-lift-phone-20261019/run-0d69eb9ed7534cd2988cbb99504c88de.board.jsonl'
FIRST_SHA='2ff83781741b200fe393edf3681c971fce2fb71a660bb3b896894e02ddc8d333'
INTERVAL=.04
FRAME_COUNT=151


def route(channel):
    if type(channel) is not int or channel not in ORDER:
        raise ValueError('Only the requested other axes are allowed')
    frames=[]
    for index in range(FRAME_COUNT):
        t=index*INTERVAL
        u=.5-.5*math.cos(math.pi*min(t,2)/2) if t<=3 else .5+.5*math.cos(math.pi*min(t-3,2)/2)
        q=MIDPOINT[:]
        q[channel-1]+=(-1 if channel==10 else 1)*int(math.floor(24*u+.5))
        frames.append(validate_pulses(q))
    return frames


def validate_plan(p):
    keys={'schema','session_id','new_request_id','boot_id','channel','expected_sequence',
          'expected_pulse_us','route_sha256','prior_log_path','prior_log_sha256',
          'camera_required','onsite_observer','new_hardware_request','mechanism_visible'}
    if not isinstance(p,dict) or set(p)!=keys or p['schema']!=SCHEMA:
        raise ValueError('Dedicated one-axis diagnostic plan required')
    channel=p['channel']; frames=route(channel);index=ORDER.index(channel)
    if (p['boot_id']!=BOOT or type(p['expected_sequence']) is not int
            or p['expected_sequence']!=1280+index*(FRAME_COUNT+1)
            or p['expected_pulse_us']!=MIDPOINT or p['route_sha256']!=digest(frames)
            or any(p[k] is not True for k in ('camera_required','onsite_observer','new_hardware_request','mechanism_visible'))):
        raise ValueError('Inspected source, exact route and active observation required')
    if any(not isinstance(p[k],str) or not re.fullmatch('[a-f0-9]{32}',p[k]) for k in ('session_id','new_request_id')):
        raise ValueError('Unique request and session required')
    if not isinstance(p['prior_log_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',p['prior_log_sha256']):
        raise ValueError('Source hash required')
    if index==0:
        if p['prior_log_path']!=FIRST_LOG or p['prior_log_sha256']!=FIRST_SHA:
            raise ValueError('Original OFF1280 evidence required')
    elif not re.fullmatch(re.escape(BOARD+'/axis-'+str(ORDER[index-1])+'-')+'[a-f0-9]{32}\\.board\\.jsonl',p['prior_log_path']):
        raise ValueError('Previous completed single-axis log required')


def validate_prior(p,raw):
    if hashlib.sha256(raw).hexdigest()!=p['prior_log_sha256']:
        raise ValueError('Prior evidence changed')
    rows=[json.loads(line) for line in raw.splitlines()]
    last=rows[-1];state=last['state']
    if (last['event']!='outputs_off' or last['route_complete'] is not True or state['armed']
            or state['enabled_mask'] or state['pending'] or state['faults']
            or state['sequence']!=p['expected_sequence'] or state['pulse_us']!=MIDPOINT):
        raise ValueError('Prior route did not finish at the inspected OFF reference')
    index=ORDER.index(p['channel'])
    if index:
        previous=ORDER[index-1];expected=route(previous)
        frames=[x for x in rows if x['event']=='frame']
        if (last.get('channel')!=previous or len(frames)!=FRAME_COUNT
                or any(x['state']['pulse_us']!=q or x['state']['enabled_mask']!=1<<(previous-1)
                    or not x['state']['armed'] or x['state']['faults'] or x['state']['pending']
                    or x['state']['sequence']!=1281+(index-1)*(FRAME_COUNT+1)+j
                    for j,(x,q) in enumerate(zip(frames,expected)))):
            raise ValueError('Previous axis route incomplete or different')


class OtherAxesDevice(FirstDirectionDevice):
    def __init__(self,registers,plan,host,*,boot_id,marker,used_path,
                 motion_inhibit_paths=None,cancel_path='/run/other-axes-check-stop',clock=time.monotonic):
        validate_plan(plan)
        if boot_id!=BOOT or marker.get('boot_id')!=BOOT or marker.get('sha256')!=IMAGE:
            raise ValueError('Boot or inspected image changed')
        PwmDevice.__init__(self,registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.used_path=Path(used_path);self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.sequence=plan['expected_sequence'];self.pulses=MIDPOINT[:]
        self.frames=route(plan['channel']);self.target_mask=1<<(plan['channel']-1)
        self.mask=self.index=0;self.inside=self.started=self.failed=False
        self.last_issue=self.deadline=None
        self.check()

    def begin(self):
        super().begin();self.deadline=self.clock()+9

    def commit(self,pulses,mask,allow_arm=False):
        self.check()
        if not self.started or self.index>=len(self.frames):
            raise RuntimeError('No further frame in this one-use check')
        if pulses!=self.frames[self.index] or mask!=self.target_mask or allow_arm is not (self.index==0):
            raise ValueError('Only this axis and its exact next frame are allowed')
        issued=self.clock()
        if self.last_issue is not None and issued-self.last_issue<INTERVAL-1e-8:
            raise RuntimeError('No accelerated catch-up')
        self.inside=True
        try:state=PwmDevice.commit(self,pulses,mask,allow_arm=allow_arm)
        except BaseException:self.failed=True;raise
        finally:self.inside=False
        self.sequence=state['sequence'];self.pulses=pulses[:];self.mask=mask
        self.last_issue=issued;self.index+=1
        return state


def run(d,emit,sleep=time.sleep):
    complete=False
    try:
        d.begin();start=d.clock()
        for index,pulses in enumerate(d.frames):
            scheduled=max(start+index*INTERVAL,d.last_issue+INTERVAL if d.last_issue is not None else start)
            while d.clock()<scheduled:
                d.check();d.kick();sleep(max(0.,min(.005,scheduled-d.clock())))
            if d.last_issue is not None and d.clock()-d.last_issue>.15:
                raise RuntimeError('Command interval stalled')
            d.check();d.kick()
            state=d.commit(pulses,d.target_mask,allow_arm=index==0)
            emit(dict(event='frame',index=index,channel=d.plan['channel'],elapsed_s=d.clock()-start,state=state))
        complete=True
    finally:
        state=d.stop_after_frame() if complete else d.off()
        emit(dict(event='outputs_off',channel=d.plan['channel'],route_complete=complete,state=state,
                  incident_locks_removed=False,position_feedback=None))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path);parser.add_argument('--execute-one-axis-check',action='store_true')
    args=parser.parse_args();plan=json.loads(args.plan.read_text());validate_plan(plan)
    if not args.execute_one_axis_check:
        print(json.dumps(dict(dry_run=True,channel=plan['channel'],frames=FRAME_COUNT,route_sha256=digest(route(plan['channel'])))));return
    validate_prior(plan,Path(plan['prior_log_path']).read_bytes())
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostLease(sys.stdin.fileno(),plan['session_id']);registers=Registers()
    try:
        d=OtherAxesDevice(registers,plan,host,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()),
            used_path='/run/other-axes-{}-{}.used'.format(plan['boot_id'],plan['expected_sequence']))
        log_path=args.plan.with_suffix('.board.jsonl')
        with log_path.open('x') as log:
            def emit(row):
                log.write(json.dumps(row)+'\n')
                if row['event']!='frame' or row['index']%25==0:print(PREFIX+json.dumps(row),flush=True)
            print(PREFIX+json.dumps(dict(event='ready',session_id=plan['session_id'],state=d.check())),flush=True)
            while not host.begun:host.check();time.sleep(.01)
            run(d,emit)
        print(PREFIX+json.dumps(dict(event='audit',board_log=str(log_path),board_log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest())),flush=True)
    finally:registers.close()


if __name__=='__main__':main()
