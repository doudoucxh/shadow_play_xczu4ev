"""Attended overhead direction mapping; never performs an unreviewed crossing.

After an unchanged, operator-confirmed power cycle, explicitly adopt the last
observed reference, not the reset registers. That first activation has no shaft
feedback and is not a rate-limited move. Every later edge needs live review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

if Path(__file__).with_name('puppet_choreography_session_20261013_r1.py').exists():
    import puppet_choreography_session_20261013_r1 as c
else:
    import puppet_choreography_session as c

BASE=c.PERSON_REFERENCE+[1500]*4
IMAGE_SHA='824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
DUET_SHA='183b063d4deff7a4cab2f86a136bef63b11714a2c7cb9cfddb8f447465e21dc5'
ZERO=(0,0,0,0,0,0)
ROUTES={
 'person-overhead-map-positive':(ZERO,(0,0,0,-40,0,0),(0,140,0,-40,0,0),
     (30,140,0,-40,0,0),(0,140,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 'person-overhead-map-negative':(ZERO,(0,0,0,-40,0,0),(0,140,0,-40,0,0),
     (-30,140,0,-40,0,0),(0,140,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 'person-overhead-lift-clearance':(ZERO,(0,0,0,-40,0,0),(0,140,0,-40,0,0),
     (0,210,0,-40,0,0),(0,140,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 'person-overhead-high-map-positive':(ZERO,(0,0,0,-40,0,0),(0,210,0,-40,0,0),
     (60,210,0,-40,0,0),(0,210,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 'person-overhead-high-map-negative':(ZERO,(0,0,0,-40,0,0),(0,210,0,-40,0,0),
     (-60,210,0,-40,0,0),(0,210,0,-40,0,0),(0,0,0,-40,0,0),ZERO)
}

def digest(profile):
    return hashlib.sha256(json.dumps(ROUTES[profile],separators=(',',':')).encode()).hexdigest()

def validate_plan(p,read=None,wall=None):
    fields={'approval','session_id','profile','expected_sequence','expected_pulses_us',
     'observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed','reviewed_at_unix_ms',
     'duration_seconds','tempo_step_us','repetitions','boot_id','restore_after_power_cycle','baseline_source'}
    if (not isinstance(p,dict) or set(p)!=fields or p['approval']!=c.APPROVAL or p['profile'] not in ROUTES
            or not c.re.fullmatch('[a-z0-9-]{1,80}',p['session_id'])
            or type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32
            or any(p[k] is not True for k in ('observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed'))
            or type(p['restore_after_power_cycle']) is not bool
            or p['tempo_step_us']!=3 or p['repetitions']!=1
            or type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=900
            or not c.re.fullmatch('[a-f0-9-]{36}',p['boot_id'])
            or type(p['reviewed_at_unix_ms']) is not int):
        raise ValueError('Exact attended overhead mapping plan required')
    if wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000:
        raise ValueError('Fresh dual-view pose review required')
    rows=c.checked_log(p['baseline_source'],read)
    first=next(r for r in rows if r['event']=='reference_held')
    final=rows[-1]
    if (final['event']!='outputs_off' or final.get('normal_frame_stop') is not True
            or final['state']['enabled_mask']!=0 or final['state']['armed'] or final['state']['pending']
            or final['state']['faults'] or final['state']['pulse_us']!=BASE):
        raise ValueError('Baseline source did not finish at the observed reference')
    if p['restore_after_power_cycle']:
        if (p['expected_sequence']!=0 or p['expected_pulses_us']!=[1500]*10
                or first.get('profile')!='person-tiger-duet' or first.get('route_sha256')!=DUET_SHA
                or {r['axis'] for r in rows if r['event']=='path_reviewed'}!=set(range(1,7))
                or [r['cycle'] for r in rows if r['event']=='route_cycle_complete']!=[1,2,3]):
            raise ValueError('Power-cycle restoration needs the completed original duet and fresh reset state')
    elif (first.get('profile') not in ROUTES or first.get('route_sha256')!=digest(first['profile'])
            or p['expected_pulses_us']!=BASE or p['expected_sequence']!=final['state']['sequence']
            or {r['axis'] for r in rows if r['event']=='path_reviewed'}!=set(range(1,7))):
        raise ValueError('Continuation requires the complete reviewed mapping route')


class CrossingSession(c.ChoreographySession):
    def __init__(self,r,p,host,*,motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel',
                 clock=time.monotonic,wall=None,read=None,
                 boot_id_path='/proc/sys/kernel/random/boot_id',image_marker='/run/shadow-pwm-loaded.json'):
        validate_plan(p,read,wall)
        self.boot_id_path=Path(boot_id_path);self.image_marker=Path(image_marker)
        if (self.boot_id_path.read_text().strip()!=p['boot_id']
                or json.loads(self.image_marker.read_text())['sha256']!=IMAGE_SHA):
            raise ValueError('Current boot or PWM image does not match the reviewed plan')
        c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(p));self.host=host;self.clock=clock
        self.deadline=clock()+p['duration_seconds'];self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=p['expected_pulses_us'][:];self.sequence=p['expected_sequence'];self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='restore' if p['restore_after_power_cycle'] else 'resume'
        self.cursor=0;self.completed=set();self.reviewed=set();self.demo_used=False
        self.own=63;self.indices=range(6);self.route_sha256=digest(p['profile'])
        self.targets=[BASE[:] for _ in ROUTES[p['profile']]]
        for target,vector in zip(self.targets,ROUTES[p['profile']]):
            for i,v in enumerate(vector):target[i]+=v

    def check(self):
        if self.boot_id_path.read_text().strip()!=self.plan['boot_id']:
            raise RuntimeError('Boot changed; do not rearm')
        if self.demo_used:
            raise RuntimeError('Overhead mapping is diagnostic-only; path review does not validate motion response or authorize replay')
        return super().check()

    def adopt(self,pulses):
        if self.phase!='restore':return super().adopt(pulses)
        self.check()
        if pulses!=self.plan['expected_pulses_us'] or self.mask:
            raise RuntimeError('Only one explicit last-reference activation may start')
        self.inside=True
        try:s=c.PwmDevice.commit(self,BASE[:],63,allow_arm=True)
        except BaseException:self.failed=True;raise
        finally:self.inside=False
        self.pulses=BASE[:];self.mask=63;self.sequence=s['sequence'];self.last_start=self.clock()
        self.phase='holding'
        return s


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true');a=parser.parse_args()
    raw=a.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.expected_plan_sha256:raise ValueError('Reviewed plan hash mismatch')
    p=json.loads(raw);validate_plan(p)
    if not a.execute_attended_fixed_choreography:print(json.dumps({'dry_run':True,'route':ROUTES[p['profile']]}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=CrossingSession(r,p,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:
            c.run_session(d,c.motion_emitter(log))
    finally:r.close()

if __name__=='__main__':main()
