"""Finite hand-axis direction checks before A02; no hand crossing or audio.

All ten channels support the assembly at midpoint; exactly one hand axis makes
the recorded +40us excursion. Each next axis requires its completed predecessor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time

from fixed_v20_probe import BOOT,IMAGE
from other_axes_check import OtherAxesDevice,route as original_route,run
from servo_pwm_device import Registers,PwmDevice,PINS
from v20_first_direction import HostLease,MIDPOINT,PREFIX,digest

SCHEMA='attended-fixed-v20-a02-hand-directions-v1'
BOARD='/run/media/mmcblk0p2/piying/fixed-v20-a02-directions-20261019'
CHANNELS=(1,2,5,6)
STARTS={ch:1831+227*i for i,ch in enumerate(CHANNELS)}
PRIOR='/run/media/mmcblk0p2/piying/fixed-v20-a01-audio-20261019/A01-ffedc978a84d43799d249481233c59fb.board.jsonl'
PRIOR_SHA='9e27ae4c58d4b9e034c1d5672d7c6f0bfe3b402f07f2e80f007979a89649b7dd'


def route(channel):
    if type(channel) is not int or channel not in CHANNELS:raise ValueError('Only four reviewed hand axes')
    return original_route(channel,rewire=True)


def validate_plan(p):
    fields={'schema','session_id','new_request_id','boot_id','channel','expected_sequence',
            'expected_pulse_us','route_sha256','prior_log_path','prior_log_sha256',
            'camera_required','onsite_observer','new_hardware_request','mechanism_visible'}
    if not isinstance(p,dict) or set(p)!=fields or p['schema']!=SCHEMA:raise ValueError('Exact A02 preparation plan required')
    ch=p['channel'];frames=route(ch)
    if (p['boot_id']!=BOOT or type(p['expected_sequence']) is not int or p['expected_sequence']!=STARTS[ch]
            or p['expected_pulse_us']!=MIDPOINT or p['route_sha256']!=digest(frames)
            or any(p[k] is not True for k in ('camera_required','onsite_observer','new_hardware_request','mechanism_visible'))):
        raise ValueError('Current attended state and exact route required')
    if any(not isinstance(p[k],str) or not re.fullmatch('[a-f0-9]{32}',p[k]) for k in ('session_id','new_request_id')):
        raise ValueError('Unique request/session IDs required')
    if ch==1:
        if p['prior_log_path']!=PRIOR or p['prior_log_sha256']!=PRIOR_SHA:raise ValueError('Actual completed A01 audio source required')
    else:
        previous=CHANNELS[CHANNELS.index(ch)-1]
        if (not re.fullmatch(re.escape(BOARD)+r'/axis-'+str(previous)+r'-[a-f0-9]{32}\.board\.jsonl',p['prior_log_path'])
                or not re.fullmatch('[a-f0-9]{64}',p['prior_log_sha256'])):
            raise ValueError('Actual completed preceding hand-axis log required')


def validate_prior(p,raw):
    if hashlib.sha256(raw).hexdigest()!=p['prior_log_sha256']:raise ValueError('Original predecessor changed')
    rows=[json.loads(line) for line in raw.splitlines()]
    last=rows[-1];s=last['state']
    if (last.get('event')!='outputs_off' or last.get('route_complete') is not True
            or s['sequence']!=p['expected_sequence'] or s['pulse_us']!=MIDPOINT
            or any(s[k] for k in ('armed','enabled_mask','faults','pending'))):
        raise ValueError('Completed clean midpoint predecessor required')
    frames=[r for r in rows if r.get('event')=='frame']
    if p['channel']==1:
        from fixed_v20_a01_audio import sample
        if (len(frames)!=288 or frames[-1].get('audio_time_s')!=6.3
                or not any(r.get('event')=='audio_complete' and 'PLAY_COMPLETE frames=302400 ' in r['player_output'] for r in rows)):
            raise ValueError('A01 original audio completion required')
        expected=[sample(r['audio_time_s']) for r in frames];start=1542;channel='tiger4'
    else:
        channel=CHANNELS[CHANNELS.index(p['channel'])-1];start=STARTS[channel];expected=route(channel)
        if len(rows)!=227 or len(frames)!=226:raise ValueError('Whole previous direction route required')
    for index,(row,pulses) in enumerate(zip(frames,expected)):
        s=row['state']
        if (row.get('index')!=index or row.get('channel')!=channel or s['sequence']!=start+index+1
                or s['pulse_us']!=pulses or s['enabled_mask']!=1023 or not s['armed'] or s['faults'] or s['pending']):
            raise ValueError('Previous frame chain differs')


class A02DirectionsDevice(OtherAxesDevice):
    def __init__(self,registers,plan,host,*,boot_id,marker,used_path,
                 motion_inhibit_paths=None,cancel_path='/run/fixed-v20-a02-directions-stop',clock=time.monotonic):
        validate_plan(plan)
        if (boot_id!=BOOT or marker.get('boot_id')!=BOOT or marker.get('sha256')!=IMAGE
                or marker.get('pins')!=list(PINS) or marker.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS'):
            raise ValueError('Reviewed current image, boot and pins required')
        PwmDevice.__init__(self,registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.used_path=Path(used_path);self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.sequence=STARTS[plan['channel']];self.pulses=MIDPOINT[:];self.profile={'deadline_s':12}
        self.frames=route(plan['channel']);self.target_mask=1023
        self.mask=self.index=0;self.inside=self.started=self.failed=False
        self.last_issue=self.deadline=None;self.check()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path);parser.add_argument('--execute-one-hand-direction',action='store_true')
    args=parser.parse_args();p=json.loads(args.plan.read_text());validate_plan(p)
    if not args.execute_one_hand_direction:
        print(json.dumps(dict(dry_run=True,frames=226,audio=False,rail_motion=False,hand_crossing=False)));return
    validate_prior(p,Path(p['prior_log_path']).read_bytes())
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostLease(sys.stdin.fileno(),p['session_id']);r=Registers()
    try:
        d=A02DirectionsDevice(r,p,host,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()),
            used_path='/run/fixed-v20-a02-direction-{}-{}.used'.format(BOOT,p['expected_sequence']))
        path=args.plan.with_suffix('.board.jsonl')
        with path.open('x') as log:
            def emit(row):
                log.write(json.dumps(row)+'\n');log.flush()
                if row['event']!='frame' or row['index']%25==0:print(PREFIX+json.dumps(row),flush=True)
            print(PREFIX+json.dumps(dict(event='ready',session_id=p['session_id'],state=d.check())),flush=True)
            while not host.begun:host.check();time.sleep(.01)
            run(d,emit)
        print(PREFIX+json.dumps(dict(event='audit',board_log=str(path),board_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())),flush=True)
    finally:r.close()


if __name__=='__main__':main()
