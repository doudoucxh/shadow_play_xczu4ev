"""Two separately reviewed head-axis checks for this fixed-rail V20 request.

This is a preparation component, not the A01 score or an automatic next-axis
runner. The operator reference and each completed predecessor remain immutable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time

from other_axes_check import OtherAxesDevice, run
from servo_pwm_device import PwmDevice, Registers, PINS
from v20_first_direction import HostLease, MIDPOINT, PREFIX, digest

IMAGE='ea680d88d2d149157490ebbe27b253b3814d6d2df17aeebb477047bb4bc81e90'
BOOT='8b5372c2-00de-459e-ad96-371ec5ea0ef9'
BOARD='/run/media/mmcblk0p2/piying/fixed-v20-probes-20261019'
REFERENCE=BOARD+'/midpoint-reference.json'
REFERENCE_SHA='5ee811bb8cae411cec7050cdf9a1418cd60fdbc9f76a34430d9f411e750b06b8'
SCHEMA='attended-fixed-v20-head-probes-v1'
CLOSE_SCHEMA='attended-fixed-v20-head-closeup-v2'
CLOSE_BOARD='/run/media/mmcblk0p2/piying/fixed-v20-closeup-20261019'


def route(channel):
    if type(channel) is not int or channel not in (7,8):
        raise ValueError('Only the separately reviewed head axes 7 and 8')
    # Exact 40us positive excursion used in the previous rewiring checks.
    from other_axes_check import route as prior_route
    return prior_route(channel,rewire=True)


def validate_plan(p):
    fields={'schema','session_id','new_request_id','boot_id','channel','expected_sequence',
            'expected_pulse_us','route_sha256','prior_log_path','prior_log_sha256',
            'camera_required','onsite_observer','new_hardware_request','mechanism_visible'}
    if not isinstance(p,dict) or set(p)!=fields or p['schema'] not in (SCHEMA,CLOSE_SCHEMA):
        raise ValueError('Exact fixed-V20 probe plan required')
    if any(not re.fullmatch('[a-f0-9]{32}',p[k]) for k in ('session_id','new_request_id')):
        raise ValueError('Unique request/session required')
    ch=p['channel'];frames=route(ch);close=p['schema']==CLOSE_SCHEMA
    if close and ch!=8:raise ValueError('Close view is solely the separately requested axis 8 recheck')
    if (p['boot_id']!=BOOT or type(p['expected_sequence']) is not int
            or p['expected_sequence']!=(454 if close else {7:0,8:227}[ch]) or p['expected_pulse_us']!=MIDPOINT
            or p['route_sha256']!=digest(frames)
            or any(p[k] is not True for k in ('camera_required','onsite_observer',
                                             'new_hardware_request','mechanism_visible'))):
        raise ValueError('Fresh attended midpoint and dual-camera binding required')
    if close:
        if (p['prior_log_path']!=BOARD+'/axis-8-adf3ab8f37c5411ab624d3816346211c.board.jsonl'
                or p['prior_log_sha256']!='0e077d447a09c1e7cf27dd932560f34e562589983107b64884035a4112cfe15b'):
            raise ValueError('Exact completed axis-8 record required for the new view')
    elif ch==7:
        if p['prior_log_path']!=REFERENCE or p['prior_log_sha256']!=REFERENCE_SHA:
            raise ValueError('Actual new operator reference required')
    elif (not re.fullmatch(re.escape(BOARD)+r'/axis-7-[a-f0-9]{32}\.board\.jsonl',p['prior_log_path'])
          or not re.fullmatch('[a-f0-9]{64}',p['prior_log_sha256'])):
        raise ValueError('Completed new axis-7 evidence required')


def validate_prior(p,raw):
    if hashlib.sha256(raw).hexdigest()!=p['prior_log_sha256']:
        raise ValueError('Original reference/evidence changed')
    close=p['schema']==CLOSE_SCHEMA
    if p['channel']==7 and not close:
        ref=json.loads(raw);s=ref['state']
        if (ref.get('schema')!='fixed-v20-start-reference-v1' or ref.get('boot_id')!=BOOT
                or ref.get('image_sha256')!=IMAGE or ref.get('operator_midpoint_confirmed') is not True
                or ref.get('onsite_observer') is not True or ref.get('rails_fixed') is not True
                or s['sequence']!=0 or s['pulse_us']!=MIDPOINT
                or any(s[k] for k in ('armed','enabled_mask','faults','pending'))):
            raise ValueError('Original operator midpoint/state mismatch')
        return
    rows=[json.loads(line) for line in raw.splitlines()]
    frames=[r for r in rows if r['event']=='frame'];last=rows[-1]
    channel=8 if close else 7;start=227 if close else 0
    if (len(frames)!=226 or last.get('event')!='outputs_off' or last.get('route_complete') is not True
            or last.get('channel')!=channel or last['state']['sequence']!=start+227
            or last['state']['pulse_us']!=MIDPOINT
            or any(last['state'][k] for k in ('armed','enabled_mask','faults','pending'))):
        raise ValueError('Axis-7 route incomplete or stopped elsewhere')
    for index,(row,pulses) in enumerate(zip(frames,route(channel))):
        s=row['state']
        if (row['index']!=index or row['channel']!=channel or s['sequence']!=start+index+1
                or s['enabled_mask']!=1<<(channel-1) or not s['armed'] or s['pulse_us']!=pulses
                or s['faults'] or s['pending']):
            raise ValueError('Axis-7 frame chain differs')


class FixedV20ProbeDevice(OtherAxesDevice):
    def __init__(self,registers,plan,host,*,boot_id,marker,used_path,
                 motion_inhibit_paths=None,cancel_path='/run/fixed-v20-probe-stop',clock=time.monotonic):
        validate_plan(plan)
        if (boot_id!=BOOT or marker.get('boot_id')!=BOOT or marker.get('sha256')!=IMAGE
                or marker.get('pins')!=list(PINS)
                or marker.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS'):
            raise ValueError('Reviewed standard UART/servo image and pins required')
        PwmDevice.__init__(self,registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.used_path=Path(used_path);self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.sequence=plan['expected_sequence'];self.pulses=MIDPOINT[:]
        self.profile={'deadline_s':12};self.frames=route(plan['channel'])
        self.target_mask=1<<(plan['channel']-1)
        self.mask=self.index=0;self.inside=self.started=self.failed=False
        self.last_issue=self.deadline=None
        self.check()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--execute-one-axis-check',action='store_true')
    args=parser.parse_args();p=json.loads(args.plan.read_text());validate_plan(p)
    if not args.execute_one_axis_check:
        print(json.dumps(dict(dry_run=True,frames=len(route(p['channel'])),rails_moved=False)))
        return
    validate_prior(p,Path(p['prior_log_path']).read_bytes())
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostLease(sys.stdin.fileno(),p['session_id']);r=Registers()
    try:
        d=FixedV20ProbeDevice(r,p,host,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()),
            used_path='/run/fixed-v20-probe-{}-{}.used'.format(BOOT,p['expected_sequence']))
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
