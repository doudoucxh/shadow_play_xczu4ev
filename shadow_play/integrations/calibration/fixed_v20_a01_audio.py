"""One A01 trial against its 6.3-second original clip, after slow-route review."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from fixed_v20_a01 import KEYS,validate_source,BOOT,IMAGE
from other_axes_check import OtherAxesDevice
from servo_pwm_device import Registers,PwmDevice,PINS
from v20_first_direction import HostLease,MIDPOINT,PREFIX,digest

SCHEMA='attended-fixed-v20-a01-original-audio-v1'
BOARD='/run/media/mmcblk0p2/piying/fixed-v20-a01-audio-20261019'
PRIOR='/run/media/mmcblk0p2/piying/fixed-v20-a01-quarter-20261019/A01-3808393aa5354c1986abae6c0b0baff9.board.jsonl'
PRIOR_SHA='957dfb1f0be9b8f5b0d66e8ce6a513e75e394a95e3b2aaeab9e5894b979b0ee5'
PLAYER='/run/media/mmcblk0p2/piying/shadow-theatre-board-20261017-r4-runtime/shadow_play/hdmi_ui/runtime/audio/usb_audio_play'
PLAYER_SHA='8684834abfc45f2823c4f3992ccd15b8c5bf3150b2757d7000b7a462cd59866d'
CLIP_SHA='7a02e6f78f99db4a14744a872ee051512d639ffd1cc366952a20136bab2399de'


def sample(t):
    if t<=0:return MIDPOINT[:]
    if t>=6.3:return MIDPOINT[:]
    edge=next(i for i in range(len(KEYS)-1) if KEYS[i][0]<=t<KEYS[i+1][0])
    (start,a),(end,b)=KEYS[edge:edge+2]
    u=.5-.5*math.cos(math.pi*(t-start)/(end-start))
    return MIDPOINT[:6]+[int(math.floor(x+(y-x)*u+.5)) for x,y in zip(a,b)]


def frames():
    return [sample(i*.02) for i in range(316)]


def validate_plan(p):
    fields={'schema','session_id','new_request_id','boot_id','channel','expected_sequence',
            'expected_pulse_us','route_sha256','prior_log_path','prior_log_sha256',
            'camera_required','onsite_observer','new_hardware_request','mechanism_visible'}
    if (not isinstance(p,dict) or set(p)!=fields or p['schema']!=SCHEMA or p['channel']!='tiger4'
            or p['boot_id']!=BOOT or type(p['expected_sequence']) is not int or p['expected_sequence']!=1542
            or p['expected_pulse_us']!=MIDPOINT or p['route_sha256']!=digest(frames())
            or p['prior_log_path']!=PRIOR or p['prior_log_sha256']!=PRIOR_SHA
            or any(p[k] is not True for k in ('camera_required','onsite_observer','new_hardware_request','mechanism_visible'))):
        raise ValueError('Exact A01 original-audio trial after the completed slow route required')
    if any(not re.fullmatch('[a-f0-9]{32}',p[k]) for k in ('session_id','new_request_id')):
        raise ValueError('New request/session IDs required')


def validate_prior(raw):
    if hashlib.sha256(raw).hexdigest()!=PRIOR_SHA:raise ValueError('Original slow-route log changed')
    from fixed_v20_a01 import frames as slow_frames
    rows=[json.loads(line) for line in raw.splitlines()]
    if len(rows)!=632:raise ValueError('Slow route is incomplete')
    for i,(row,pulses) in enumerate(zip(rows[:-1],slow_frames())):
        s=row['state']
        if (row['event']!='frame' or row['index']!=i or row['channel']!='tiger4'
                or s['sequence']!=911+i or s['pulse_us']!=pulses or s['enabled_mask']!=1023
                or not s['armed'] or s['faults'] or s['pending']):
            raise ValueError('Slow-route frame chain differs')
    last=rows[-1];s=last['state']
    if (last['event']!='outputs_off' or last['route_complete'] is not True or s['sequence']!=1542
            or s['pulse_us']!=MIDPOINT or any(s[k] for k in ('armed','enabled_mask','faults','pending'))):
        raise ValueError('Slow-route final state differs')


class AudioClip:
    def __init__(self):
        self.process=None;self.output=b'';self.finished=False

    def check(self):
        if self.process is None:return
        while True:
            try:chunk=os.read(self.process.stdout.fileno(),4096)
            except BlockingIOError:break
            if not chunk:break
            self.output+=chunk
            if len(self.output)>16384:raise RuntimeError('Oversized audio output')
        rc=self.process.poll()
        if rc is not None:
            if rc or b'PLAY_COMPLETE frames=302400 ' not in self.output:
                raise RuntimeError('A01 audio failed or decoded length differs')
            self.finished=True

    def start(self,d,sleep):
        if self.process is not None:raise RuntimeError('Audio is single use')
        for path,sha in ((Path(PLAYER),PLAYER_SHA),(Path(BOARD)/'a01.mp3',CLIP_SHA)):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('Audio/player hash mismatch')
        outputs=[]
        for p in Path('/proc/asound').glob('card[0-9]*/pcm[0-9]*p/info'):
            if 'USB Audio' in p.read_text():
                outputs.append((int(p.parent.parent.name[4:]),int(p.parent.name[3:-1])))
        if len(outputs)!=1:raise RuntimeError('Exactly one USB playback output required')
        card,device=outputs[0]
        self.process=subprocess.Popen([PLAYER,str(card),str(device),'0.60',BOARD+'/a01.mp3'],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        os.set_blocking(self.process.stdout.fileno(),False)
        deadline=d.clock()+2
        while b'PLAY_START ' not in self.output:
            d.check();d.kick();self.check()
            if d.clock()>=deadline:raise RuntimeError('Audio start timeout')
            sleep(.003)
        return d.clock()

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
            self.process.stdout.close()


class A01AudioDevice(OtherAxesDevice):
    def __init__(self,registers,plan,host,*,boot_id,marker,used_path,
                 motion_inhibit_paths=None,cancel_path='/run/fixed-v20-a01-audio-stop',clock=time.monotonic):
        validate_plan(plan)
        if (boot_id!=BOOT or marker.get('boot_id')!=BOOT or marker.get('sha256')!=IMAGE
                or marker.get('pins')!=list(PINS) or marker.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS'):
            raise ValueError('Reviewed current image, boot and pins required')
        PwmDevice.__init__(self,registers,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(plan));self.host=host;self.clock=clock
        self.used_path=Path(used_path);self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.sequence=1542;self.pulses=MIDPOINT[:];self.profile={'deadline_s':12}
        self.target_mask=1023;self.mask=self.index=0;self.inside=self.started=self.failed=False
        self.last_issue=self.deadline=self.onset=None;self.final_sample=False;self.check()

    def commit(self,*args,**kwargs):
        raise RuntimeError('No arbitrary frames; use the owned audio clock sample')

    def set_onset(self,onset):
        self.check()
        if self.index!=1 or self.onset is not None or not 0<=self.clock()-onset<=.1:
            raise RuntimeError('Only the observed first audio onset may start the timeline')
        self.onset=onset

    def adopt_sample(self):
        self.check();now=self.clock()
        if not self.started or self.final_sample or self.index>=400:
            raise RuntimeError('No further sample in this one-use trial')
        if self.last_issue is not None and not .02-1e-8<=now-self.last_issue<=.15:
            raise RuntimeError('No accelerated catch-up or stalled timeline')
        if self.index==0:t=0.
        elif self.onset is None:raise RuntimeError('Observed audio onset required')
        else:t=min(6.3,now-self.onset)
        pulses=sample(t)
        if max(abs(a-b) for a,b in zip(pulses,self.pulses))>4:
            raise RuntimeError('Audio-clock sample exceeds the 4us adoption bound')
        self.inside=True
        try:state=PwmDevice.commit(self,pulses,1023,allow_arm=self.index==0)
        except BaseException:self.failed=True;raise
        finally:self.inside=False
        self.sequence=state['sequence'];self.pulses=pulses[:];self.mask=1023
        self.last_issue=now;self.index+=1;self.final_sample=self.onset is not None and t>=6.3
        return state,t


def run_audio(d,emit,audio,sleep=time.sleep):
    complete=False
    try:
        d.begin();state,t=d.adopt_sample()
        emit(dict(event='frame',index=0,channel='tiger4',audio_time_s=t,state=state))
        onset=audio.start(d,sleep);d.set_onset(onset)
        emit(dict(event='audio_started',board_monotonic_onset=onset,source_range_s=[2.7,9.0],
                  acoustic_latency_measured=False))
        while not d.final_sample:
            while d.clock()<d.last_issue+.02:
                d.check();d.kick();audio.check();sleep(min(.003,max(0.,d.last_issue+.02-d.clock())))
            audio.check()
            if audio.finished and d.clock()-onset<6.2:raise RuntimeError('Audio ended early')
            state,t=d.adopt_sample()
            emit(dict(event='frame',index=d.index-1,channel='tiger4',audio_time_s=t,state=state))
        while not audio.finished:
            d.check();d.kick();audio.check()
            if d.clock()-onset>7.8:raise RuntimeError('Audio completion overdue')
            sleep(.003)
        emit(dict(event='audio_complete',player_output=audio.output.decode('utf-8','replace')))
        complete=True
    finally:
        try:
            state=d.stop_after_frame() if complete else d.off()
            emit(dict(event='outputs_off',channel='tiger4',route_complete=complete,state=state,
                      incident_locks_removed=False,position_feedback=None))
        finally:audio.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path);parser.add_argument('--execute-one-a01-audio',action='store_true')
    args=parser.parse_args();p=json.loads(args.plan.read_text());validate_plan(p)
    if not args.execute_one_a01_audio:
        print(json.dumps(dict(dry_run=True,duration_s=6.3,rails_moved=False)));return
    validate_source((Path(BOARD)/'a01-data.json').read_bytes());validate_prior(Path(PRIOR).read_bytes())
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostLease(sys.stdin.fileno(),p['session_id']);r=Registers();audio=AudioClip()
    try:
        d=A01AudioDevice(r,p,host,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()),
            used_path='/run/fixed-v20-a01-audio-{}-1542.used'.format(BOOT))
        path=args.plan.with_suffix('.board.jsonl')
        with path.open('x') as log:
            def emit(row):
                log.write(json.dumps(row)+'\n');log.flush()
                if row['event']!='frame' or row['index']%25==0:
                    print(PREFIX+json.dumps(row),flush=True)
            print(PREFIX+json.dumps(dict(event='ready',session_id=p['session_id'],state=d.check())),flush=True)
            while not host.begun:host.check();time.sleep(.01)
            run_audio(d,emit,audio)
        print(PREFIX+json.dumps(dict(event='audit',board_log=str(path),
            board_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())),flush=True)
    finally:audio.close();r.close()


if __name__=='__main__':main()
