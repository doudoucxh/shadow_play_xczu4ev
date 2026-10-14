"""Single attended tiger leap; static reference review precedes motion.
Historical reference plus operator unchanged report is not shaft feedback.
No lock removal, arbitrary targets, automatic retries or incident playback.
"""
import argparse,hashlib,json,signal,sys,time
from pathlib import Path
if Path(__file__).with_name('hand_crossing_session_20261014_r36.py').exists():
    import hand_crossing_session_20261014_r36 as h
else:
    import hand_crossing_session as h
c=h.c
PROFILE='tiger-operator-leap-bite'
BASE=h.BASE
ROUTE=((0,0,0,0),(20,-20,20,20),(-60,60,-60,-60),
       (-60,-60,-60,-30),(-60,-20,-60,-20),(-30,0,-30,0),(0,0,0,0))
STEPS=(0,3,8,8,3,3,3)
HOLDS=(0,.25,.12,.3,.15,.12,.1)
HISTORICAL_SHA='3f8547793801264ad92c4007aabfef321f6e92277f8f0662af719e3230fbd5f4'
def digest():return hashlib.sha256(json.dumps(ROUTE,separators=(',',':')).encode()).hexdigest()
def validate(p,read=None,wall=None):
    extras={'tiger_hardware_unchanged','historical_tiger_reference','static_reference_review_required'}
    if not extras<=set(p) or any(p[k] is not True for k in extras-{'historical_tiger_reference'}):
        raise ValueError('Unchanged tiger linkage and static visual review required')
    q={k:v for k,v in p.items() if k not in extras}
    if q['profile']!=PROFILE:raise ValueError('Only compiled tiger leap')
    q['profile']=h.TIGER_DIRECTED_PROFILE
    h.validate_plan(q,read,wall)
    if p['restore_after_power_cycle'] or p['expected_pulses_us']!=BASE:
        raise ValueError('Inspected current command reference required')
    spec=p['historical_tiger_reference']
    if spec!={'path':'/tmp/tiger_duet_reference_20261012.json','sha256':HISTORICAL_SHA}:
        raise ValueError('Exact historical closed tiger reference required')
    raw=Path(spec['path']).read_bytes() if read is None else read(spec['path'])
    if hashlib.sha256(raw).hexdigest()!=HISTORICAL_SHA:raise ValueError('Historical reference changed')
    report=json.loads(raw)
    end=next(r for r in reversed(report['events']) if r['event']=='outputs_off')
    if not end['normal_frame_stop'] or end['state']['pulse_us']!=BASE or end['state']['enabled_mask']:
        raise ValueError('Historical tiger reference was not normally closed')
class TigerLeapSession(c.ChoreographySession):
    def __init__(self,r,p,host,*,motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic,wall=None,read=None,boot_id_path='/proc/sys/kernel/random/boot_id',image_marker='/run/shadow-pwm-loaded.json'):
        validate(p,read,wall)
        self.boot_id_path=Path(boot_id_path)
        if self.boot_id_path.read_text().strip()!=p['boot_id'] or json.loads(Path(image_marker).read_text()).get('sha256')!=h.IMAGE_SHA:
            raise ValueError('Boot or image changed')
        c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(p));self.host=host;self.clock=clock
        self.deadline=clock()+p['duration_seconds'];self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=BASE[:];self.sequence=p['expected_sequence'];self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.cursor=0;self.completed=set();self.reviewed=set();self.demo_used=False
        self.own=960;self.indices=range(6,10);self.route_sha256=digest()
        self.targets=[BASE[:6]+[1500+x for x in v] for v in ROUTE]
    def check(self):
        if self.boot_id_path.read_text().strip()!=self.plan['boot_id']:raise RuntimeError('Boot changed')
        return super().check()
    def advance(self,stage,emit,sleep):
        original=self.plan['tempo_step_us'];self.plan['tempo_step_us']=STEPS[stage]
        try:return super().advance(stage,emit,sleep)
        finally:self.plan['tempo_step_us']=original

def run(d,emit,sleep=time.sleep):
    normal=False
    try:
        state=d.adopt(BASE[:])
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=d.route_sha256,tempo_step_us=8,state=state,
                  position_feedback=None,startup_is_not_rate_limited=True,incident_locks_removed=False))
        while True:
            d.check()
            if d.host.action is not None:
                action,sequence=d.host.action;d.host.action=None
                if action!='demo' or sequence!=d.sequence:raise RuntimeError('Only fresh static-review demo may start')
                break
            d.wait(.03,sleep)
        emit(dict(event='operator_trial_started',state=d.status(),static_reference_visually_reviewed=True))
        for stage in range(1,len(ROUTE)):
            d.advance(stage,emit,sleep);d.wait(HOLDS[stage],sleep)
        emit(dict(event='operator_trial_complete',state=d.status(),automatic_replay_allowed=False))
        normal=True
    finally:
        state=d.stop_after_frame() if normal else d.off()
        emit(dict(event='outputs_off',state=state,normal_frame_stop=normal,incident_locks_removed=False))
def main():
    a=argparse.ArgumentParser();a.add_argument('plan',type=Path);a.add_argument('--expected-plan-sha256',required=True);a.add_argument('--execute-attended-fixed-choreography',action='store_true');args=a.parse_args()
    raw=args.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Plan changed')
    p=json.loads(raw);validate(p)
    if not args.execute_attended_fixed_choreography:print(json.dumps({'dry_run':True,'route':ROUTE}));return
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=TigerLeapSession(r,p,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:
            run(d,c.motion_emitter(log))
    finally:r.close()
if __name__=='__main__':main()
