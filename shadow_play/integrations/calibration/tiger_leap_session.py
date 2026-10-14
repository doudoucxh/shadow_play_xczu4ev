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
STAGGERED='tiger-operator-staggered-right-start'
PARK='tiger-operator-tree-position'
PRESS='tiger-operator-head-lower-at-tree'
LOWER5='tiger-operator-head-lower-five'
LOWER_LEFT='tiger-operator-head-lower-ten-left'
SCREEN='tiger-operator-screen-approach'
SCREEN_LEAP='tiger-operator-screen-leap-bite'
UPLEFT='tiger-operator-up-left-leap'
INTERRUPTED_AI_SHA='b0fbd146897f875d15d0e96a7921c19aeea0fcdab309a7c217633cb63bf538e1'
ROUTES={PROFILE:ROUTE,STAGGERED:((0,0,0,0),(40,0,40,0),(40,-20,40,20),
    (10,80,10,20),(-30,80,-30,-80),(-60,-60,-60,-80),
    (-60,-20,-60,-20),(40,0,40,0),(0,0,0,0))}
ROUTES[PARK]=tuple((v,0,v,0) for v in (40,100,180,260,340))
ROUTES[PRESS]=((340,0,340,0),(340,-20,340,0),(340,-40,340,0))
ROUTES[LOWER5]=((340,-40,340,0),(340,-77,340,0))
ROUTES[LOWER_LEFT]=((340,-77,340,0),(310,-151,310,0))
ROUTES[SCREEN]=((310,-151,310,0),(270,-188,270,0),(230,-225,230,0))
ROUTES[SCREEN_LEAP]=((230,-225,230,0),(220,-225,220,20),(150,-135,150,20),(100,-115,100,-65),(40,-210,40,-65),(40,-200,40,-10),(140,-210,140,0),(230,-225,230,0))
ROUTES[UPLEFT]=((230,-225,230,0),(220,-225,220,60),(150,-75,150,60),(100,-45,100,-50),(40,-200,40,-50),(40,-200,40,10),(140,-210,140,0),(230,-225,230,0))
STEP_TABLE={UPLEFT:(0,5,10,10,10,5,5,5),SCREEN_LEAP:(0,3,10,10,10,5,5,5),SCREEN:(0,2,2),LOWER_LEFT:(0,2),LOWER5:(0,2),PRESS:(0,2,2),PARK:(0,3,3,3,3),PROFILE:STEPS,STAGGERED:(0,3,3,12,12,12,3,3,3)}
HOLD_TABLE={UPLEFT:(0,.18,.18,.08,.2,.1,.05,.15),SCREEN_LEAP:(0,.15,.06,.08,.2,.1,.05,.15),SCREEN:(0,.4,.4),LOWER_LEFT:(0,.5),LOWER5:(0,.5),PRESS:(0,.3,.3),PARK:(0,.2,.2,.2,.2),PROFILE:HOLDS,STAGGERED:(0,.2,.18,.02,.05,.25,.15,.2,.1)}
def digest(profile=PROFILE):return hashlib.sha256(json.dumps(ROUTES[profile],separators=(',',':')).encode()).hexdigest()
def closed_tiger_reference(rows):
    first,last=rows[0],rows[-1];profile=first.get('profile')
    if profile not in ROUTES:return False
    if (first.get('event')!='reference_held' or first.get('route_sha256')!=digest(profile)
        or sum(r['event']=='operator_trial_started' for r in rows)!=1
        or sum(r['event']=='operator_trial_complete' for r in rows)!=1
        or [r['axis'] for r in rows if r['event']=='probe_complete']!=list(range(1,len(ROUTES[profile])))
        or last.get('event')!='outputs_off' or not last.get('normal_frame_stop')
        or first['state']['pulse_us']!=BASE[:6]+[1500+v for v in ROUTES[profile][0]]
        or last['state']['pulse_us']!=BASE[:6]+[1500+v for v in ROUTES[profile][-1]]):
        raise ValueError('Incomplete tiger reference')
    prior=first['state'];stage=0
    for r in rows:
        if r['event']=='probe_started':stage=r['axis']
        if 'state' not in r:continue
        q=r['state'];off=r['event']=='outputs_off'
        if (q['faults'] or q['pending'] or q['enabled_mask']!=(0 if off else 960)
            or q['armed'] is not (not off) or q['pulse_us'][:6]!=BASE[:6]
            or q['sequence'] not in (prior['sequence'],(prior['sequence']+1)%2**32)
            or (q['sequence']==prior['sequence'] and q['pulse_us']!=prior['pulse_us'])
            or max(abs(a-b) for a,b in zip(q['pulse_us'],prior['pulse_us']))>(STEP_TABLE[profile][stage] if stage else 3)
            or any(not 1500+min(v[i] for v in ROUTES[profile])<=q['pulse_us'][6+i]<=1500+max(v[i] for v in ROUTES[profile]) for i in range(4))):
            raise ValueError('Tiger reference discontinuity')
        prior=q
    return True
def validate(p,read=None,wall=None):
    extras={'tiger_hardware_unchanged','historical_tiger_reference','static_reference_review_required'}
    if not extras<=set(p) or any(p[k] is not True for k in extras-{'historical_tiger_reference'}):
        raise ValueError('Unchanged tiger linkage and static visual review required')
    q={k:v for k,v in p.items() if k not in extras}
    if q['profile'] not in ROUTES:raise ValueError('Only compiled tiger leap')
    rows=c.checked_log(q['baseline_source'],read)
    if rows[0].get('profile') in ROUTES:
        required={'approval','session_id','profile','expected_sequence','expected_pulses_us','observer_ready',
            'operator_hardware_unmoved','dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds',
            'tempo_step_us','repetitions','boot_id','restore_after_power_cycle','baseline_source','execution_mode'}
        if (set(q)!=required or q['approval']!=c.APPROVAL or not c.re.fullmatch('[a-z0-9-]{1,80}',q['session_id'])
            or any(q[k] is not True for k in ('observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed'))
            or type(q['expected_sequence']) is not int or q['expected_sequence']!=rows[-1]['state']['sequence']
            or q['tempo_step_us']!=8 or q['repetitions']!=1 or q['execution_mode']!='operator-attended-one-arc-trial'
            or type(q['duration_seconds']) is not int or not 120<=q['duration_seconds']<=900
            or not c.re.fullmatch('[a-f0-9-]{36}',q['boot_id'])
            or type(q['reviewed_at_unix_ms']) is not int):raise ValueError('Exact tiger continuation required')
        if (p['profile']==PARK and q['baseline_source']['sha256']==INTERRUPTED_AI_SHA
            and rows[-1]['state']['pulse_us']==BASE[:6]+[1540,1500,1540,1500]
            and rows[-1]['event']=='outputs_off' and rows[-1]['state']['enabled_mask']==0
            and not rows[-1]['state']['armed'] and not rows[-1]['state']['faults']):
            pass # Exact camera-expiry receipt, separately observed at the current pose.
        else:closed_tiger_reference(rows)
        if wall is not None and not 0<=wall()*1000-q['reviewed_at_unix_ms']<120000:raise ValueError('Stale scene')
    else:
        q['profile']=h.TIGER_DIRECTED_PROFILE
        h.validate_plan(q,read,wall)
    if p['restore_after_power_cycle'] or p['expected_pulses_us']!=BASE[:6]+[1500+v for v in ROUTES[p['profile']][0]]:
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
        self.pulses=p['expected_pulses_us'][:];self.sequence=p['expected_sequence'];self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.cursor=0;self.completed=set();self.reviewed=set();self.demo_used=False
        self.own=960;self.indices=range(6,10);self.route_sha256=digest(p['profile'])
        self.targets=[BASE[:6]+[1500+x for x in v] for v in ROUTES[p['profile']]]
    def check(self):
        if self.boot_id_path.read_text().strip()!=self.plan['boot_id']:raise RuntimeError('Boot changed')
        return super().check()
    def advance(self,stage,emit,sleep):
        original=self.plan['tempo_step_us'];self.plan['tempo_step_us']=STEP_TABLE[self.plan['profile']][stage]
        try:return super().advance(stage,emit,sleep)
        finally:self.plan['tempo_step_us']=original

def run(d,emit,sleep=time.sleep):
    normal=False
    try:
        state=d.adopt(d.plan['expected_pulses_us'][:])
        emit(dict(event='reference_held',profile=d.plan['profile'],route_sha256=d.route_sha256,tempo_step_us=8,state=state,
                  position_feedback=None,startup_is_not_rate_limited=True,incident_locks_removed=False))
        while True:
            d.check()
            if d.host.action is not None:
                action,sequence=d.host.action;d.host.action=None
                if action!='demo' or sequence!=d.sequence:raise RuntimeError('Only fresh static-review demo may start')
                break
            d.wait(.03,sleep)
        emit(dict(event='operator_trial_started',state=d.status(),static_reference_visually_reviewed=True))
        for stage in range(1,len(d.targets)):
            d.advance(stage,emit,sleep);d.wait(HOLD_TABLE[d.plan['profile']][stage],sleep)
            if (d.plan['profile']==STAGGERED and stage==1) or (d.plan['profile'] in (PARK,PRESS,SCREEN) and stage<len(d.targets)-1):
                emit(dict(event='launch_position_held',state=d.check()))
                while True:
                    d.check()
                    if d.host.action is not None:
                        action,sequence=d.host.action;d.host.action=None
                        if action!='demo' or sequence!=d.sequence:raise RuntimeError('Fresh launch clearance review required')
                        break
                    d.wait(.03,sleep)
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
    if not args.execute_attended_fixed_choreography:print(json.dumps({'dry_run':True,'route':ROUTES[p['profile']]}));return
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
