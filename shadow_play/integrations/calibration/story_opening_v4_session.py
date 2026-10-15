"""One attended R-endpoint rehearsal: five reviewed components, then audio.

New pose combinations are candidates until viewed. No generic reset or replay.
"""
import argparse,hashlib,json,re,signal,sys,time
from pathlib import Path
import story_midpoint_session as m
import story_motion_opening_v4 as score

PROFILE='story-opening-v4-attended'
SOURCE='/tmp/puppet_choreography_hip_inside_lift_20261015_r.events.jsonl'
SOURCE_SHA='d7d0380090e603bbcf3e0d4e348280438f39098ac1913bc5d58cfa29af549ba5'
BOOT='7eea2c53-e104-45cf-88fe-439f1821e5d4'
START=[1570,1242,1565,1414,1416,1600,1730,1250,1770,1740]
TARGETS=[START,score.H_POINT+START[6:],START,score.H_UP+START[6:],score.H_HAMMER+START[6:],START]
LABELS=['pointing','return_hip','double_lift_candidate','same_side_hammer_candidate','return_start']
FRAMES=[START[:]]+[q for a,b in zip(TARGETS,TARGETS[1:]) for q in m.transition_frames(a,b)]
ENTRY_SHA=hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()

def validate(p,raw,wall=None):
    if score.STATUS.startswith('withdrawn_'):
        raise ValueError('S high-head candidate withdrawn after operator correction; no replay')
    if (p.get('profile')!=PROFILE or p.get('approval')!=m.c.APPROVAL
        or p.get('expected_sequence')!=43685 or p.get('expected_pulses_us')!=START
        or p.get('source_sha256')!=SOURCE_SHA or p.get('entry_sha256')!=ENTRY_SHA
        or p.get('story_route_sha256')!=score.check_envelope()['route_sha256']
        or p.get('boot_id')!=BOOT or p.get('duration_seconds')!=600 or p.get('story_mode')!='full'
        or p.get('observer_ready') is not True or p.get('dual_view_pose_reviewed') is not True
        or p.get('endpoint_comparison')!='overall_pose_retained_small_passive_wrist_shift'):
        raise ValueError('Exact reviewed R endpoint and five-component rehearsal required')
    stamp=p.get('reviewed_at_unix_ms')
    if type(stamp) is not int or stamp<=0 or (wall and not 0<=wall()*1000-stamp<120000):
        raise ValueError('Fresh review required')
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('R evidence changed')
    rows=[json.loads(x) for x in raw.splitlines()];last=rows[-1];s=last['state']
    if (last['event']!='outputs_off' or last.get('normal_frame_stop') is not False
        or [r['axis'] for r in rows if r['event']=='probe_complete']!=[1,2,3]
        or rows[-2].get('awaiting')!='review_3' or rows[-2]['state']['pulse_us']!=START
        or s['sequence']!=43685 or s['pulse_us']!=START or s['armed'] or s['enabled_mask'] or s['pending'] or s['faults']):
        raise ValueError('Not the inspected static R timeout endpoint')
    if score.START!=START:raise ValueError('Score startup changed')
    for q in FRAMES:
        if q[6:]!=START[6:]:raise ValueError('Tiger static during component review')
        if any(not 500+lo*2000/270<=v<=500+hi*2000/270 for v,(lo,hi) in zip(q,m.DEGREE_LIMITS)):
            raise ValueError('Inset bounds exceeded')
    if max(abs(x-y) for a,b in zip(FRAMES,FRAMES[1:]) for x,y in zip(a,b))>3:
        raise ValueError('Component step exceeds 3us')

class OpeningSession(m.MidpointSession):
    def __init__(self,r,p,host,*,source_raw,clock=time.monotonic,wall=None,
                 motion_inhibit_paths=None,cancel_path='/run/shadow-pwm-recovery-cancel'):
        validate(p,source_raw,wall);m.c.PwmDevice.__init__(self,r,motion_inhibit_paths=motion_inhibit_paths)
        self.plan=dict(p,tempo_step_us=3);self.host=host;self.clock=clock;self.deadline=clock()+600
        self.cancel=Path(cancel_path);self.hashes=self.lock_hashes();self.pulses=START[:]
        self.sequence=43685;self.mask=0;self.inside=False;self.failed=False
        self.last_start=None;self.next_command=None;self.phase='resume';self.own=1023
        self.cursor=0;self.components_complete=False;self.check()
    def adopt(self,q):
        if not self.components_complete and (self.cursor>=len(FRAMES) or q!=FRAMES[self.cursor]):
            raise RuntimeError('Only next component frame before full score')
        state=super().adopt(q)
        if not self.components_complete:self.cursor+=1
        return state

def review_or_finish(d,emit,edge,sleep):
    report=0
    while True:
        d.check()
        if d.host.action is not None:
            action,seq=d.host.action;d.host.action=None
            if seq!=d.sequence or action not in ('review_'+str(edge),'finish'):
                raise RuntimeError('Unexpected or stale review')
            return action
        if d.clock()>=report:
            emit(dict(event='hold_alive',awaiting='review_'+str(edge),finish_available=True,state=d.check()));report=d.clock()+.5
        d.wait(.02,sleep)

def run(d,emit,audio,sleep=time.sleep):
    handed=False;normal=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,state=d.adopt(START[:]),position_feedback=None))
        d.phase='component_review'
        for edge,(a,b) in enumerate(zip(TARGETS,TARGETS[1:]),1):
            m.await_action(d,emit,'probe_'+str(edge),sleep)
            for i,q in enumerate(m.transition_frames(a,b)):
                d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
                if i and d.clock()-d.last_start>.06:raise RuntimeError('Component scheduler stalled')
                d.next_command=q;emit(dict(event='probe_step',edge=edge,state=d.adopt(q)))
            emit(dict(event='probe_complete',axis=edge,label=LABELS[edge-1],state=d.check()))
            decision=review_or_finish(d,emit,edge,sleep)
            emit(dict(event='path_reviewed',axis=edge,decision=decision,state=d.check()))
            if decision=='finish':normal=True;return
        d.components_complete=True
        d.wait(.03,sleep);d.next_command=score.START[:]
        # Bind only this process to the new fixed timeline; old v3 remains intact.
        m.story.score=score;m.story.ROUTE_SHA=score.check_envelope()['route_sha256'];m.story.PROFILE=PROFILE
        handed=True;m.story.run(d,emit,audio,sleep)
    finally:
        if not handed:
            try:emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),normal_frame_stop=normal))
            finally:audio.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True);parser.add_argument('--execute-attended-fixed-choreography',action='store_true')
    args=parser.parse_args();raw=args.plan.read_bytes();p=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Plan changed')
    source=Path(SOURCE).read_bytes();validate(p,source)
    if not re.fullmatch('[a-z0-9-]{1,80}',p.get('session_id','')):raise ValueError('Invalid session')
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,components=TARGETS,score=score.check_envelope())));return
    if (Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=BOOT
        or json.loads(Path('/run/shadow-pwm-loaded.json').read_text()).get('sha256')!=m.IMAGE_SHA):raise ValueError('Boot/image changed')
    with args.plan.with_suffix('.used').open('x') as f:f.write('one reviewed opening/fight rehearsal\n')
    _,_,m.sound.CLIP,m.sound.CLIP_SHA=m.story.MODES['full'];audio=m.sound.AudioClip()
    def interrupt(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    host=m.c.HostControl(sys.stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=m.c.Registers()
    try:
        d=OpeningSession(r,p,host,source_raw=source)
        with args.plan.with_suffix('.events.jsonl').open('x') as log:run(d,m.rehearsal_emitter(log),audio)
    finally:r.close();audio.close()

if __name__=='__main__':main()
