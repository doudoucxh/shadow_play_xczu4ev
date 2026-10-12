"""Attended fixed connected routes, with exact reference and command-log audit.

No incident lock is removed. This is not an arbitrary joint-range controller.
Every edge is separately observed before the one-use connected demonstration.
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

from person_recovery_session import HostControl, ObservationLost
if Path(__file__).with_name('tiger_center_session_20261012_r2.py').exists():
    from tiger_center_session_20261012_r2 import TigerCenterSession
else:
    from tiger_center_session import TigerCenterSession
from servo_pwm_device import PwmDevice, Registers

APPROVAL='attended-fixed-puppet-choreography-20261012'
PERSON_REFERENCE=[1537,1212,1537,1514,1508,1740]
PROFILES={
    'person-connected-guard':((0,0,0,0,0,0),(0,0,0,-40,0,0),
        (0,140,0,-40,0,0),(0,140,0,-40,0,-240),
        (0,0,0,-40,0,-240),(0,0,0,-40,0,0),(0,0,0,0,0,0)),
    'tiger-axis-map-a':((0,0,0,0),(40,0,0,0),(0,0,0,0),
        (0,40,0,0),(0,0,0,0),(0,0,40,0),(0,0,0,0)),
    'tiger-axis-map-b':((0,0,0,0),(0,0,0,-40),(0,0,0,0),
        (40,0,40,0),(0,0,0,0),(0,40,0,-40),(0,0,0,0)),
    'tiger-approach-settle':((0,0,0,0),(-40,0,-40,0),(-40,40,-40,-40),
        (-40,40,-40,40),(-40,0,-40,0),(0,0,0,0)),
    'tiger-pounce-bite':((0,0,0,0),(-40,0,-40,0),(-40,40,-40,-40),
        (-40,-40,-40,-40),(-40,0,-40,0),(0,0,0,0)),
}

def route_hash(profile):
    return hashlib.sha256(json.dumps(PROFILES[profile],separators=(',',':')).encode()).hexdigest()


def checked_log(spec,read=None):
    if (not isinstance(spec,dict) or set(spec)!={'path','sha256'}
            or not isinstance(spec['path'],str)
            or not re.fullmatch(r'/tmp/(?:person-linkage|puppet-choreography)-[a-z0-9-]+\.jsonl',spec['path'])
            or not isinstance(spec['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',spec['sha256'])):
        raise ValueError('Immutable board motion log and SHA256 required')
    raw=(Path(spec['path']).read_bytes() if read is None else read(spec['path']))
    if hashlib.sha256(raw).hexdigest()!=spec['sha256']:raise ValueError('Board log hash mismatch')
    return [json.loads(line) for line in raw.splitlines()]


def validate_plan(p,wall=None):
    fields={'approval','session_id','profile','expected_sequence','expected_pulses_us',
        'reference_held_state','reference_off_state','reference_normal_frame_stop',
        'intervening_board_logs','observer_ready','operator_unchanged_report',
        'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds',
        'tempo_step_us','repetitions'}
    if not isinstance(p,dict) or set(p)-fields-{'prior_slow_route_log'} or not fields<=set(p) or p['approval']!=APPROVAL:
        raise ValueError('Exact attended connected-route plan required')
    if not isinstance(p['session_id'],str) or not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):raise ValueError('Safe unique session ID required')
    if p['profile'] not in PROFILES:raise ValueError('Select a compiled fixed route')
    if p['observer_ready'] is not True or p['dual_view_pose_reviewed'] is not True or p['operator_unchanged_report']!='电源和机构都没动':
        raise ValueError('Fresh dual-view review, unchanged mechanism and onsite cutoff required')
    if type(p['reviewed_at_unix_ms']) is not int or p['reviewed_at_unix_ms']<=0:raise ValueError('Host review timestamp required')
    if wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000:raise ValueError('Host review expired')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=900:raise ValueError('Attended duration required')
    if type(p['tempo_step_us']) is not int or p['tempo_step_us'] not in (3,8):raise ValueError('Only separately selected slow/fast tempo')
    if type(p['repetitions']) is not int or not 1<=p['repetitions']<=3:raise ValueError('At most three route repetitions')
    if p['tempo_step_us']==8 and 'prior_slow_route_log' not in p:raise ValueError('Fast route needs the same physically reviewed slow route')
    if p['tempo_step_us']==3 and ('prior_slow_route_log' in p or p['repetitions']!=1):raise ValueError('Slow geometry diagnostic is one-use')
    values=p['expected_pulses_us'];person=p['profile'].startswith('person-');own=63 if person else 960
    if (not isinstance(values,list) or len(values)!=10 or any(type(v) is not int or not 500<=v<=2500 for v in values)
            or (values[:6]!=PERSON_REFERENCE if person else values[6:]!=[1500]*4)):
        raise ValueError('Only the established group reference may start')
    held,off=p['reference_held_state'],p['reference_off_state']
    if (p['reference_normal_frame_stop'] is not True or held['enabled_mask']!=own or held['armed'] is not True
            or off['enabled_mask']!=0 or off['armed'] is not False or held['pulse_us']!=off['pulse_us']
            or held['pending'] or held['faults'] or off['pending'] or off['faults']
            or off['sequence']!=(held['sequence']+1)%2**32):raise ValueError('Verified group held-to-normal-OFF reference required')
    sl=slice(0,6) if person else slice(6,10)
    if off['pulse_us'][sl]!=values[sl]:raise ValueError('Group reference changed')
    if type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32:raise ValueError('Inspected current sequence required')
    if not isinstance(p['intervening_board_logs'],list) or len(p['intervening_board_logs'])>6:raise ValueError('Bounded intervening log chain required')
    if not p['intervening_board_logs'] and (off['sequence']!=p['expected_sequence'] or off['pulse_us']!=values):
        raise ValueError('Current state does not follow the group reference')


def audit_logs(p,read=None):
    own=63 if p['profile'].startswith('person-') else 960
    sl=slice(0,6) if own==63 else slice(6,10)
    previous=p['reference_off_state']
    for spec in p['intervening_board_logs']:
        rows=checked_log(spec,read)
        if not rows or rows[-1].get('event')!='outputs_off' or rows[-1].get('normal_frame_stop') is not True:
            raise ValueError('Intervening session did not close normally')
        for row in rows:
            if 'state' not in row:continue
            s=row['state']
            if (s['pulse_us'][sl]!=p['expected_pulses_us'][sl] or s['enabled_mask']&own
                    or s['faults'] or s['pending'] or s['armed']!=bool(s['enabled_mask'])
                    or s['sequence'] not in (previous['sequence'],(previous['sequence']+1)%2**32)
                    or (s['sequence']==previous['sequence'] and s['pulse_us']!=previous['pulse_us'])):
                raise ValueError('Intervening command chain changed this group or skipped a frame')
            previous=s
    if previous['sequence']!=p['expected_sequence'] or previous['pulse_us']!=p['expected_pulses_us']:
        raise ValueError('Audited command chain does not reach current OFF state')
    if p['tempo_step_us']==8:
        rows=checked_log(p['prior_slow_route_log'],read)
        first=next(r for r in rows if r['event']=='reference_held')
        count=len(PROFILES[p['profile']])-1
        if (first.get('profile')!=p['profile'] or first.get('route_sha256')!=route_hash(p['profile']) or first.get('tempo_step_us')!=3
                or {r['axis'] for r in rows if r['event']=='path_reviewed'}!=set(range(1,count+1))
                or rows[-1]['event']!='outputs_off' or rows[-1].get('normal_frame_stop') is not True
                or rows[-1]['state']['pulse_us'][sl]!=p['expected_pulses_us'][sl]):
            raise ValueError('Same complete slow route was not physically reviewed and closed')


class ChoreographySession(TigerCenterSession):
    def __init__(self,r,p,host,*,motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel',clock=time.monotonic,wall=None,read=None):
        validate_plan(p,wall);audit_logs(p,read);PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=json.loads(json.dumps(p));self.host=host;self.clock=clock
        self.deadline=clock()+p['duration_seconds'];self.cancel=Path(cancel_path);self.hashes=self.lock_hashes()
        self.pulses=p['expected_pulses_us'][:];self.sequence=p['expected_sequence'];self.mask=0
        self.inside=False;self.failed=False;self.last_start=None;self.next_command=None
        self.phase='resume';self.cursor=0;self.completed=set();self.reviewed=set();self.demo_used=False
        self.own=63 if p['profile'].startswith('person-') else 960
        self.indices=range(6) if self.own==63 else range(6,10)
        self.targets=[]
        for vector in PROFILES[p['profile']]:
            q=self.pulses[:]
            for i,v in zip(self.indices,vector):q[i]+=v
            self.targets.append(q)

    def center(self,*args,**kwargs):raise RuntimeError('Centering is not part of a connected route')

    def adopt(self,pulses):
        self.check()
        if self.phase=='resume':
            if pulses!=self.pulses or self.mask:raise RuntimeError('Only the inspected static reference can arm')
        else:
            if pulses!=self.next_command or self.mask!=self.own:raise RuntimeError('Only the next compiled route step can execute')
            if max(abs(a-b) for a,b in zip(pulses,self.pulses))>self.plan['tempo_step_us']:raise RuntimeError('Step limit exceeded')
            if self.last_start is not None and self.clock()-self.last_start<.02-1e-9:raise RuntimeError('No accelerated catch-up')
        started=self.clock();self.inside=True
        try:s=super(TigerCenterSession,self).commit(pulses,self.own,allow_arm=self.mask==0)
        except BaseException:self.failed=True;raise
        finally:self.inside=False
        self.pulses=pulses[:];self.mask=self.own;self.sequence=s['sequence'];self.last_start=started
        return s

    def advance(self,stage,emit,sleep):
        if stage!=self.cursor+1 or stage>=len(self.targets):raise RuntimeError('Only the next fixed edge, once')
        begin=self.targets[stage-1];target=self.targets[stage]
        if self.pulses!=begin:raise RuntimeError('Current pose is not the preceding route waypoint')
        self.phase='route';extent=max(abs(a-b) for a,b in zip(begin,target));count=max(1,math.ceil(extent*math.pi/(1.8*self.plan['tempo_step_us'])))
        emit({'event':'probe_started','axis':stage,'target_pulses_us':target,'steps':count,'state':self.check()})
        for step in range(1,count+1):
            self.wait(max(0,.02-(self.clock()-self.last_start)),sleep)
            u=.5*(1-math.cos(math.pi*step/count));q=[a+round((b-a)*u) for a,b in zip(begin,target)]
            self.next_command=q
            emit({'event':'probe_step','axis':stage,'step':step,'state':self.adopt(q)})
        self.cursor=stage;self.completed.add(stage);self.phase='holding';self.next_command=None
        emit({'event':'probe_complete','axis':stage,'state':self.check()})


def run_session(d,emit,*,sleep=time.sleep):
    normal=False
    try:
        emit({'event':'reference_held','profile':d.plan['profile'],'route_sha256':route_hash(d.plan['profile']),'tempo_step_us':d.plan['tempo_step_us'],
              'state':d.adopt(d.pulses[:]),'position_feedback':None,'incident_locks_removed':False})
        d.phase='holding';d.wait(2,sleep);report=d.clock()
        while d.clock()<d.deadline:
            d.check();d.kick()
            if d.host.action is not None:
                action,sequence=d.host.action;d.host.action=None
                if sequence!=d.sequence:raise RuntimeError('Stale action; no retry')
                if action=='finish':normal=True;break
                if action.startswith('probe_'):
                    if d.completed-d.reviewed:raise RuntimeError('Review the current edge before advancing')
                    d.advance(int(action[-1]),emit,sleep)
                elif action.startswith('review_'):
                    n=int(action[-1])
                    if n not in d.completed or n in d.reviewed:raise RuntimeError('No new completed edge to review')
                    d.reviewed.add(n);emit({'event':'path_reviewed','axis':n,'state':d.check()})
                elif action=='demo':
                    count=len(d.targets)-1
                    if d.demo_used or d.reviewed!=set(range(1,count+1)) or d.pulses!=d.targets[0]:raise RuntimeError('Entire closed route must be observed before one-use demo')
                    d.demo_used=True;emit({'event':'demo_started','state':d.check()})
                    for repetition in range(d.plan['repetitions']):
                        d.cursor=0
                        for n in range(1,count+1):
                            d.advance(n,emit,sleep);d.wait(.1,sleep)
                        emit({'event':'route_cycle_complete','cycle':repetition+1,'state':d.check()})
                    emit({'event':'demo_complete','state':d.check()})
                else:raise RuntimeError('Unsupported route action')
            if d.clock()>=report:
                emit({'event':'hold_alive','state':d.check(),'waypoint':d.cursor,'remaining_seconds':max(0,d.deadline-d.clock())});report=d.clock()+1
            d.wait(.03,sleep)
        normal=True
    except ObservationLost:normal=True;raise
    finally:emit({'event':'outputs_off','state':d.stop_after_frame() if normal else d.off(),'normal_frame_stop':normal,'incident_locks_removed':False})


def motion_emitter(log):
    last=-math.inf
    def emit(row):
        nonlocal last
        now=time.monotonic();row=dict(row,board_monotonic_seconds=now);log.write(json.dumps(row)+'\n')
        if row['event']!='probe_step' or now-last>=.2:
            log.flush();print(json.dumps(row),flush=True)
            if row['event']=='probe_step':last=now
    return emit


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path)
    p.add_argument('--expected-plan-sha256',required=True);p.add_argument('--execute-attended-fixed-choreography',action='store_true');a=p.parse_args()
    raw=a.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.expected_plan_sha256:raise ValueError('Host-reviewed plan hash mismatch')
    plan=json.loads(raw);validate_plan(plan);audit_logs(plan)
    if not a.execute_attended_fixed_choreography:print(json.dumps({'dry_run':True,'profile':plan['profile'],'route':PROFILES[plan['profile']]}));return
    def interrupt(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=HostControl(sys.stdin.fileno());print(json.dumps({'event':'await_host_lease'}),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=Registers()
    try:
        d=ChoreographySession(r,plan,host)
        with (Path('/tmp')/('puppet-choreography-'+plan['session_id']+'.jsonl')).open('x') as log:
            run_session(d,motion_emitter(log))
    finally:r.close()


if __name__=='__main__':main()
