"""One attended duet of the two previously reviewed fixed routes.

Both groups share atomic PWM frames. No arbitrary new range or incident replay.
The slower group sets each edge duration; component paths remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

if Path(__file__).with_name('puppet_choreography_session_20261012_r6.py').exists():
    import puppet_choreography_session_20261012_r6 as c
else:
    import puppet_choreography_session as c

BASE=c.PERSON_REFERENCE+[1500]*4
PERSON='person-martial-linked'
TIGER='tiger-pounce-bite'
PROFILE='person-tiger-duet'
ROUTE=tuple(p+c.PROFILES[TIGER][min(i,5)] for i,p in enumerate(c.PROFILES[PERSON]))
DIGEST=hashlib.sha256(json.dumps(ROUTE,separators=(',',':')).encode()).hexdigest()


def completed_route(spec,profile,mask,read=None):
    rows=c.checked_log(spec,read)
    first=rows[0]
    starts=[r for r in rows if r['event']=='demo_started']
    ends=[r for r in rows if r['event']=='demo_complete']
    if (first.get('profile')!=profile or first.get('route_sha256')!=c.route_hash(profile)
            or first.get('tempo_step_us')!=8 or len(starts)!=1 or len(ends)!=1
            or starts[0]['state']['pulse_us']!=BASE or ends[0]['state']['pulse_us']!=BASE
            or [r['cycle'] for r in rows if r['event']=='route_cycle_complete']!=[1,2,3]
            or rows[-1]['event']!='outputs_off' or rows[-1].get('normal_frame_stop') is not True
            or rows[-1]['state']['enabled_mask']!=0 or rows[-1]['state']['pulse_us']!=BASE):
        raise ValueError('Each component requires its completed, physically reviewed fast demonstration')
    states=[r['state'] for r in rows if 'state' in r]
    for a,b in zip(states,states[1:]):
        if (b['faults'] or b['pending'] or b['enabled_mask'] not in (0,mask)
                or b['sequence'] not in (a['sequence'],(a['sequence']+1)%2**32)
                or max(abs(x-y) for x,y in zip(a['pulse_us'],b['pulse_us']))>8):
            raise ValueError('Component log contains a fault, gap or oversized step')
    if states[-2]['enabled_mask']!=mask or states[-1]['sequence']!=(states[-2]['sequence']+1)%2**32:
        raise ValueError('Component did not hold its reference before normal OFF')
    return states[-2],states[-1]


def validate_plan(p,read=None,wall=None):
    fields={'approval','session_id','profile','expected_sequence','expected_pulses_us',
            'observer_ready','operator_unchanged_report','dual_view_pose_reviewed',
            'reviewed_at_unix_ms','duration_seconds','tempo_step_us','repetitions',
            'person_completed_log','tiger_completed_log','tiger_intervening_logs'}
    if (not isinstance(p,dict) or set(p)!=fields or p['approval']!=c.APPROVAL or p['profile']!=PROFILE
            or not c.re.fullmatch('[a-z0-9-]{1,80}',p['session_id']) or p['expected_pulses_us']!=BASE
            or p['observer_ready'] is not True or p['dual_view_pose_reviewed'] is not True
            or p['operator_unchanged_report']!='电源和机构都没动'
            or type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32
            or type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600
            or p['tempo_step_us']!=8 or type(p['repetitions']) is not int or not 1<=p['repetitions']<=3
            or type(p['reviewed_at_unix_ms']) is not int):
        raise ValueError('Exact attended fixed duet plan required')
    if wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000:
        raise ValueError('Fresh dual-view review required')
    _,person_off=completed_route(p['person_completed_log'],PERSON,63,read)
    tiger_held,tiger_off=completed_route(p['tiger_completed_log'],TIGER,960,read)
    if person_off['sequence']!=p['expected_sequence']:
        raise ValueError('Latest person demonstration is not the inspected current state')
    audit=dict(profile=TIGER,reference_off_state=tiger_off,reference_held_state=tiger_held,
               expected_sequence=p['expected_sequence'],expected_pulses_us=BASE,
               intervening_board_logs=p['tiger_intervening_logs'],tempo_step_us=3)
    if not isinstance(audit['intervening_board_logs'],list) or not 1<=len(audit['intervening_board_logs'])<=6:
        raise ValueError('Complete tiger-static intervening chain required')
    c.audit_logs(audit,read)


class DuetSession(c.ChoreographySession):
    def __init__(self,r,p,host,*,motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic,wall=None,read=None):
        validate_plan(p,read,wall);c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(p));self.host=host;self.clock=clock
        self.deadline=clock()+p['duration_seconds'];self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=BASE[:];self.sequence=p['expected_sequence'];self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.cursor=0;self.completed=set();self.reviewed=set();self.demo_used=False
        self.own=1023;self.indices=range(10);self.route_sha256=DIGEST
        self.targets=[[a+b for a,b in zip(BASE,v)] for v in ROUTE]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true');a=parser.parse_args()
    raw=a.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.expected_plan_sha256:raise ValueError('Reviewed plan hash mismatch')
    p=json.loads(raw);validate_plan(p)
    if not a.execute_attended_fixed_choreography:print(json.dumps({'dry_run':True,'route':ROUTE}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=c.HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=DuetSession(r,p,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:
            c.run_session(d,c.motion_emitter(log))
    finally:r.close()


if __name__=='__main__':main()
