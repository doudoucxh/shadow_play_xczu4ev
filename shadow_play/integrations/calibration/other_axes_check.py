"""One requested small single-axis check, with separate review between axes.

Each finite series starts from its actual completed source record. It cannot
run axis 8, initialize all axes, change targets, or advance to another axis.
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
LARGER_SCHEMA='attended-other-axes-40us-v2'
LARGER_ORDER=(3,6,1,2,4,5,7,9,10)
LARGER_BOARD='/run/media/mmcblk0p2/piying/other-axes-40us-20261019'
LARGER_LOG='/run/media/mmcblk0p2/piying/other-axes-check-20261019/axis-6-e70459d1760d405c9a988cbb2a285f1e.board.jsonl'
LARGER_SHA='3bbc14d593a1c7654536a886616e2efb2f0f8713be2581c466fde73dd269a401'
OPPOSITE_SCHEMA='attended-other-axes-opposite-v3'
OPPOSITE_ORDER=(1,4,5,9,10,2,3,6,7)
OPPOSITE_BOARD='/run/media/mmcblk0p2/piying/other-axes-direction-20261019'
OPPOSITE_LOG='/run/media/mmcblk0p2/piying/other-axes-40us-20261019/axis-10-d6f3d88259e14590b4fbef767623d8a7.board.jsonl'
OPPOSITE_SHA='e389518ce1b1e46312ab3ab2eaac908fb0aa4eddeb1a48becab74b8a209580d7'


def profile(larger=False,opposite=False):
    if opposite:
        return dict(schema=OPPOSITE_SCHEMA,order=OPPOSITE_ORDER,board=OPPOSITE_BOARD,first_log=OPPOSITE_LOG,
                    first_sha=OPPOSITE_SHA,start_sequence=4691,frames=226,amplitude=40,ramp_s=3,hold_s=2,deadline_s=12)
    if larger:
        return dict(schema=LARGER_SCHEMA,order=LARGER_ORDER,board=LARGER_BOARD,first_log=LARGER_LOG,
                    first_sha=LARGER_SHA,start_sequence=2648,frames=226,amplitude=40,ramp_s=3,hold_s=2,deadline_s=12)
    return dict(schema=SCHEMA,order=ORDER,board=BOARD,first_log=FIRST_LOG,first_sha=FIRST_SHA,
                start_sequence=1280,frames=FRAME_COUNT,amplitude=24,ramp_s=2,hold_s=1,deadline_s=9)


def route(channel,larger=False,opposite=False):
    if type(channel) is not int or channel not in ORDER:
        raise ValueError('Only the requested other axes are allowed')
    cfg=profile(larger,opposite);ramp=cfg['ramp_s'];turn=ramp+cfg['hold_s'];frames=[]
    for index in range(cfg['frames']):
        t=index*INTERVAL
        u=.5-.5*math.cos(math.pi*min(t,ramp)/ramp) if t<=turn else .5+.5*math.cos(math.pi*min(t-turn,ramp)/ramp)
        q=MIDPOINT[:]
        q[channel-1]+=(-1 if channel==10 else 1)*(-1 if opposite else 1)*int(math.floor(cfg['amplitude']*u+.5))
        frames.append(validate_pulses(q))
    return frames


def validate_plan(p):
    keys={'schema','session_id','new_request_id','boot_id','channel','expected_sequence',
          'expected_pulse_us','route_sha256','prior_log_path','prior_log_sha256',
          'camera_required','onsite_observer','new_hardware_request','mechanism_visible'}
    if isinstance(p,dict) and p.get('schema') in (LARGER_SCHEMA,OPPOSITE_SCHEMA):
        keys=keys|{'larger_amplitude_acknowledged'}
    if isinstance(p,dict) and p.get('schema')==OPPOSITE_SCHEMA:
        keys=keys|{'continued_diagnostics_requested'}
    if not isinstance(p,dict) or set(p)!=keys or p['schema'] not in (SCHEMA,LARGER_SCHEMA,OPPOSITE_SCHEMA):
        raise ValueError('Dedicated one-axis diagnostic plan required')
    larger=p['schema'] in (LARGER_SCHEMA,OPPOSITE_SCHEMA);opposite=p['schema']==OPPOSITE_SCHEMA;cfg=profile(larger,opposite)
    if opposite and p['continued_diagnostics_requested'] is not True:
        raise ValueError('New request for continued diagnosis required')
    if larger and p['larger_amplitude_acknowledged'] is not True:
        raise ValueError('Explicit request for the 40us check required')
    channel=p['channel'];frames=route(channel,larger,opposite);index=cfg['order'].index(channel)
    if (p['boot_id']!=BOOT or type(p['expected_sequence']) is not int
            or p['expected_sequence']!=cfg['start_sequence']+index*(cfg['frames']+1)
            or p['expected_pulse_us']!=MIDPOINT or p['route_sha256']!=digest(frames)
            or any(p[k] is not True for k in ('camera_required','onsite_observer','new_hardware_request','mechanism_visible'))):
        raise ValueError('Inspected source, exact route and active observation required')
    if any(not isinstance(p[k],str) or not re.fullmatch('[a-f0-9]{32}',p[k]) for k in ('session_id','new_request_id')):
        raise ValueError('Unique request and session required')
    if not isinstance(p['prior_log_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',p['prior_log_sha256']):
        raise ValueError('Source hash required')
    if index==0:
        if p['prior_log_path']!=cfg['first_log'] or p['prior_log_sha256']!=cfg['first_sha']:
            raise ValueError('Original completed evidence required')
    elif not re.fullmatch(re.escape(cfg['board']+'/axis-'+str(cfg['order'][index-1])+'-')+'[a-f0-9]{32}\\.board\\.jsonl',p['prior_log_path']):
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
    larger=p['schema'] in (LARGER_SCHEMA,OPPOSITE_SCHEMA);opposite=p['schema']==OPPOSITE_SCHEMA
    cfg=profile(larger,opposite);index=cfg['order'].index(p['channel'])
    if index:
        previous=cfg['order'][index-1];expected=route(previous,larger,opposite)
        frames=[x for x in rows if x['event']=='frame']
        if (last.get('channel')!=previous or len(frames)!=cfg['frames']
                or any(x['state']['pulse_us']!=q or x['state']['enabled_mask']!=1<<(previous-1)
                    or not x['state']['armed'] or x['state']['faults'] or x['state']['pending']
                    or x['state']['sequence']!=cfg['start_sequence']+1+(index-1)*(cfg['frames']+1)+j
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
        larger=plan['schema'] in (LARGER_SCHEMA,OPPOSITE_SCHEMA);opposite=plan['schema']==OPPOSITE_SCHEMA
        self.profile=profile(larger,opposite)
        self.frames=route(plan['channel'],larger,opposite);self.target_mask=1<<(plan['channel']-1)
        self.mask=self.index=0;self.inside=self.started=self.failed=False
        self.last_issue=self.deadline=None
        self.check()

    def begin(self):
        super().begin();self.deadline=self.clock()+self.profile['deadline_s']

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
        frames=route(plan['channel'],plan['schema'] in (LARGER_SCHEMA,OPPOSITE_SCHEMA),plan['schema']==OPPOSITE_SCHEMA)
        print(json.dumps(dict(dry_run=True,channel=plan['channel'],frames=len(frames),route_sha256=digest(frames))));return
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
