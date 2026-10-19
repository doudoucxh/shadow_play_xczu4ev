"""One quarter-speed A01 candidate, with current all-ten midpoint support.

Only recorded tiger endpoints within 40us are used. This finite exercise has no
audio, rail transport, full-show branch or automatic next action.
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

from fixed_v20_probe import BOOT,IMAGE
from other_axes_check import OtherAxesDevice,run
from servo_pwm_device import Registers,PwmDevice,PINS
from v20_first_direction import HostLease,MIDPOINT,PREFIX,digest

SCHEMA='attended-fixed-v20-a01-quarter-v1'
BOARD='/run/media/mmcblk0p2/piying/fixed-v20-a01-quarter-20261019'
DATA_SHA='a223cb03364e0d9dcb43cf4b6ab65ff489c4be2dcd2be0c90fd67258edc359d5'
PRIOR='/run/media/mmcblk0p2/piying/fixed-v20-supported-20261019/axis-8-ce60b247371d48bcb1c6c5076b744f6a.board.jsonl'
PRIOR_SHA='f9dcfe501956de6e6b5206251120b62583a26b42fcb02f9401da7ca0bc73a5b7'
KEYS=((0.,(1500,1500,1500,1500)),(.7,(1540,1500,1500,1500)),
      (1.4333106576,(1500,1540,1500,1500)),(2.1,(1500,1540,1500,1460)),
      (2.7,(1500,1540,1500,1460)),(3.4333106576,(1500,1500,1500,1500)),
      (4.3,(1540,1500,1540,1500)),(5.3,(1500,1500,1500,1500)),
      (6.3,(1500,1500,1500,1500)))


def frames():
    rows=[]
    for index in range(631):
        t=min(index*.04*.25,6.3)
        if t>=6.3:q=KEYS[-1][1]
        else:
            edge=next(i for i in range(len(KEYS)-1) if KEYS[i][0]<=t<KEYS[i+1][0])
            (start,a),(end,b)=KEYS[edge:edge+2]
            u=.5-.5*math.cos(math.pi*(t-start)/(end-start))
            q=tuple(int(math.floor(x+(y-x)*u+.5)) for x,y in zip(a,b))
        rows.append(MIDPOINT[:6]+list(q))
    return rows


def validate_source(raw):
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Original A01 data changed')
    candidate=json.loads(raw)['candidate']
    if [(key['time_s'],tuple(key['pulse_us'][6:])) for key in candidate['keyframes']]!=list(KEYS):
        raise ValueError('Recorded A01 keyframes differ')
    if any(key['pulse_us'][:6]!=MIDPOINT[:6] for key in candidate['keyframes']):
        raise ValueError('No person pulse changes in this exercise')


def validate_plan(p):
    fields={'schema','session_id','new_request_id','boot_id','channel','expected_sequence',
            'expected_pulse_us','route_sha256','prior_log_path','prior_log_sha256',
            'camera_required','onsite_observer','new_hardware_request','mechanism_visible'}
    if (not isinstance(p,dict) or set(p)!=fields or p['schema']!=SCHEMA
            or p['channel']!='tiger4' or p['boot_id']!=BOOT
            or type(p['expected_sequence']) is not int or p['expected_sequence']!=910
            or p['expected_pulse_us']!=MIDPOINT or p['route_sha256']!=digest(frames())
            or p['prior_log_path']!=PRIOR or p['prior_log_sha256']!=PRIOR_SHA
            or any(p[k] is not True for k in ('camera_required','onsite_observer',
                                             'new_hardware_request','mechanism_visible'))):
        raise ValueError('Exact quarter-speed A01 and completed supported-state binding required')
    if any(not re.fullmatch('[a-f0-9]{32}',p[k]) for k in ('session_id','new_request_id')):
        raise ValueError('New request/session IDs required')


def validate_prior(raw):
    if hashlib.sha256(raw).hexdigest()!=PRIOR_SHA:raise ValueError('Supported-axis8 original log changed')
    from fixed_v20_probe import route
    rows=[json.loads(line) for line in raw.splitlines()]
    if len(rows)!=227:raise ValueError('Supported-axis8 frame count differs')
    for index,(row,pulses) in enumerate(zip(rows[:-1],route(8))):
        s=row['state']
        if (row.get('event')!='frame' or row.get('index')!=index or row.get('channel')!=8
                or s['sequence']!=684+index or s['pulse_us']!=pulses or s['enabled_mask']!=1023
                or not s['armed'] or s['faults'] or s['pending']):
            raise ValueError('Supported-axis8 route differs')
    last=rows[-1];s=last['state']
    if (last.get('event')!='outputs_off' or last.get('route_complete') is not True
            or s['sequence']!=910 or s['pulse_us']!=MIDPOINT
            or any(s[k] for k in ('armed','enabled_mask','faults','pending'))):
        raise ValueError('Supported-axis8 final state differs')


class A01Device(OtherAxesDevice):
    def __init__(self,registers,plan,host,*,boot_id,marker,used_path,
                 motion_inhibit_paths=None,cancel_path='/run/fixed-v20-a01-stop',clock=time.monotonic):
        validate_plan(plan)
        if (boot_id!=BOOT or marker.get('boot_id')!=BOOT or marker.get('sha256')!=IMAGE
                or marker.get('pins')!=list(PINS)
                or marker.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS'):
            raise ValueError('Reviewed current image, boot and pins required')
        PwmDevice.__init__(self,registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.used_path=Path(used_path);self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.sequence=910;self.pulses=MIDPOINT[:];self.profile={'deadline_s':35}
        self.frames=frames();self.target_mask=1023
        self.mask=self.index=0;self.inside=self.started=self.failed=False
        self.last_issue=self.deadline=None
        self.check()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path);parser.add_argument('--execute-one-a01-slow',action='store_true')
    args=parser.parse_args();p=json.loads(args.plan.read_text());validate_plan(p)
    if not args.execute_one_a01_slow:
        print(json.dumps(dict(dry_run=True,frames=631,nominal_duration_s=25.2,audio=False,rail_motion=False)))
        return
    validate_source((Path(BOARD)/'a01-data.json').read_bytes());validate_prior(Path(PRIOR).read_bytes())
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostLease(sys.stdin.fileno(),p['session_id']);r=Registers()
    try:
        d=A01Device(r,p,host,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()),
            used_path='/run/fixed-v20-a01-quarter-{}-910.used'.format(BOOT))
        path=args.plan.with_suffix('.board.jsonl')
        with path.open('x') as log:
            def emit(row):
                log.write(json.dumps(row)+'\n');log.flush()
                if row['event']!='frame' or row['index']%25==0:
                    print(PREFIX+json.dumps(row),flush=True)
            print(PREFIX+json.dumps(dict(event='ready',session_id=p['session_id'],state=d.check())),flush=True)
            while not host.begun:host.check();time.sleep(.01)
            run(d,emit)
        print(PREFIX+json.dumps(dict(event='audit',board_log=str(path),
            board_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())),flush=True)
    finally:r.close()


if __name__=='__main__':main()
