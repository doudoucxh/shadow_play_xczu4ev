"""Attended fixed gesture diagnostics; never performs an unreviewed crossing.

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
 # Revisit the observed 210-us lift before testing one extra 70-us level.
 # This only measures lift clearance; it never commands an overhead crossing.
 'person-overhead-lift-280-probe':(ZERO,(0,0,0,-40,0,0),(0,210,0,-40,0,0),
     (0,280,0,-40,0,0),(0,210,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 # Keep the hand raised while restoring the body's original support height.
 # Review that coupling separately before any lateral move.
 'person-overhead-body-clearance-probe':(ZERO,(0,0,0,-40,0,0),(0,280,0,-40,0,0),
     (0,280,0,0,0,0),(0,280,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 # Inspect one hand's high-pose inward response, with the body at reference.
 # Each lateral edge is a separate attended review, not an approved crossing.
 'person-overhead-high280-yaw80-probe':(ZERO,(0,280,0,0,0,0),(40,280,0,0,0,0),
     (80,280,0,0,0,0),(40,280,0,0,0,0),(0,280,0,0,0,0),ZERO),
 'person-overhead-high280-yaw160-probe':(ZERO,(0,280,0,0,0,0),(80,280,0,0,0,0),
     (160,280,0,0,0,0),(80,280,0,0,0,0),(0,280,0,0,0,0),ZERO),
 # A bounded two-axis arc entry: test one 70-us pitch edge at the reviewed
 # inward yaw. This is an exploratory geometry, not an inferred semicircle.
 'person-overhead-arc-entry-probe':(ZERO,(0,280,0,0,0,0),(160,280,0,0,0,0),
     (160,210,0,0,0,0),(160,280,0,0,0,0),(0,280,0,0,0,0),ZERO),
 # Explicitly requested, operator-observed single trial. This wider candidate
 # is not represented as a calibrated semicircle or an automatically reusable path.
 'person-overhead-operator-arc-trial':(ZERO,(0,280,0,0,0,0),(240,280,0,0,0,0),
     (240,140,0,0,0,0),(240,280,0,0,0,0),(0,280,0,0,0,0),ZERO),
 'person-overhead-high-map-positive':(ZERO,(0,0,0,-40,0,0),(0,210,0,-40,0,0),
     (60,210,0,-40,0,0),(0,210,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 'person-overhead-high-map-negative':(ZERO,(0,0,0,-40,0,0),(0,210,0,-40,0,0),
     (-60,210,0,-40,0,0),(0,210,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 'person-script-hand-b-strike-probe':(ZERO,(0,0,0,-40,0,0),(0,0,0,-40,0,-120),
     (0,0,0,-40,0,-240),(0,0,0,-40,0,-120),(0,0,0,-40,0,0),ZERO),
 'person-script-double-hit-probe':(ZERO,(0,0,0,-40,0,0),(0,70,0,-40,0,-120),
     (0,140,0,-40,0,-240),(0,70,0,-40,0,-120),(0,0,0,-40,0,0),ZERO),
 # The observed hand A remained raised at +70 on descent. Return it to its
 # reference during the first descending edge, alongside hand B's -120 pose.
 # This is a new combined path and requires its own slow review before tempo 8.
 'person-script-double-drop-sync-probe':(ZERO,(0,0,0,-40,0,0),(0,70,0,-40,0,-120),
     (0,140,0,-40,0,-240),(0,0,0,-40,0,-120),(0,0,0,-40,0,0),ZERO),
 # Isolate hand B's lateral response at the low hand pose. This does not
 # cross the torso and is not an overhead clearance test.
 'person-script-hand-b-local-yaw-probe':(ZERO,(0,0,0,-40,0,0),(0,0,0,-40,40,0),
     (0,0,0,-40,0,0),(0,0,0,-40,-40,0),(0,0,0,-40,0,0),ZERO),
 # Following the observed inward -40 response, review a second negative level
 # separately. No pitch increase, head yaw, other hand motion or replay.
 'person-script-hand-b-inward-80-probe':(ZERO,(0,0,0,-40,0,0),(0,0,0,-40,-40,0),
     (0,0,0,-40,-80,0),(0,0,0,-40,-40,0),(0,0,0,-40,0,0),ZERO),
 # Review a modest pitch change at the smaller inward yaw pose. The previous
 # -80 yaw edge turned the body; do not expand yaw further or call it a crossing.
 'person-script-hand-b-inward-fold-probe':(ZERO,(0,0,0,-40,0,0),(0,0,0,-40,-40,0),
     (0,0,0,-40,-40,-60),(0,0,0,-40,-40,0),(0,0,0,-40,0,0),ZERO),
 # Identify the other hand's own low-pose yaw response. Do not mirror the
 # observed direction of hand B or infer the same global mounting orientation.
 'person-script-hand-a-local-yaw-probe':(ZERO,(0,0,0,-40,0,0),(40,0,0,-40,0,0),
     (0,0,0,-40,0,0),(-40,0,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 # The observed positive direction brings hand A inward. Revisit +40 first,
 # then inspect one additional +40 edge; unrelated yaw/pitch axes stay fixed.
 'person-script-hand-a-inward-80-probe':(ZERO,(0,0,0,-40,0,0),(40,0,0,-40,0,0),
     (80,0,0,-40,0,0),(40,0,0,-40,0,0),(0,0,0,-40,0,0),ZERO),
 # Reference-video-inspired phase order, not video-to-servo angle estimation:
 # body support, leading hand guard, other hand counter, early leading-hand
 # recovery, second hand recovery, then body. All yaw axes remain fixed.
 'person-reference-guard-counter-probe':(ZERO,(0,0,0,-40,0,0),(0,70,0,-40,0,0),
     (0,140,0,-40,0,-240),(0,0,0,-40,0,-120),(0,0,0,-40,0,0),ZERO)
}
HAND_B_YAW_PROFILES=frozenset(('person-script-hand-b-local-yaw-probe','person-script-hand-b-inward-80-probe'))
HAND_B_DIAGNOSTIC_PROFILES=HAND_B_YAW_PROFILES|frozenset(('person-script-hand-b-inward-fold-probe',))
HAND_A_YAW_PROFILES=frozenset(('person-script-hand-a-local-yaw-probe','person-script-hand-a-inward-80-probe'))
SLOW_YAW_PROFILES=HAND_B_YAW_PROFILES|HAND_A_YAW_PROFILES
OVERHEAD_LIFT_PROFILES=frozenset(('person-overhead-lift-280-probe',))
OVERHEAD_BODY_PROFILES=frozenset(('person-overhead-body-clearance-probe',))
OVERHEAD_APPROACH_PROFILES=frozenset(('person-overhead-high280-yaw80-probe',))
OVERHEAD_WIDER_PROFILES=frozenset(('person-overhead-high280-yaw160-probe',))
OVERHEAD_ARC_PROFILES=frozenset(('person-overhead-arc-entry-probe',))
OPERATOR_ARC_PROFILES=frozenset(('person-overhead-operator-arc-trial',))
SLOW_DIAGNOSTIC_PROFILES=HAND_B_DIAGNOSTIC_PROFILES|SLOW_YAW_PROFILES|OVERHEAD_LIFT_PROFILES|OVERHEAD_BODY_PROFILES|OVERHEAD_APPROACH_PROFILES|OVERHEAD_WIDER_PROFILES|OVERHEAD_ARC_PROFILES
FAST_GESTURE_PROFILES=frozenset(('person-script-hand-b-strike-probe','person-script-double-hit-probe',
                               'person-script-double-drop-sync-probe','person-reference-guard-counter-probe'))
CONTINUOUS_PRESENTATION_PROFILES=frozenset(('person-reference-guard-counter-probe',))

def digest(profile):
    return hashlib.sha256(json.dumps(ROUTES[profile],separators=(',',':')).encode()).hexdigest()

def reference_sequence(p,rows,read=None):
    sequence=rows[-1]['state']['sequence']
    if 'held_reference_log' not in p:return sequence
    holds=c.checked_log(p['held_reference_log'],read)
    if (p['profile'] not in OPERATOR_ARC_PROFILES or p['restore_after_power_cycle']
            or holds[0].get('event')!='reference_held' or holds[0].get('profile')!='person-overhead-operator-arc-trial'
            or holds[0].get('route_sha256')!=digest('person-overhead-operator-arc-trial')
            or any(r.get('event') not in ('reference_held','hold_alive') for r in holds)):
        raise ValueError('Only a failed static hold without any trial movement may advance the reference sequence')
    sequence=(sequence+1)%2**32
    for row in holds:
        state=row['state']
        if (state['sequence']!=sequence or state['pulse_us']!=BASE or state['enabled_mask']!=63
                or not state['armed'] or state['pending'] or state['faults']):
            raise ValueError('Static hold continuity is inconsistent')
    return sequence

def checked_reviews(p,rows,read=None,wall=None):
    reviewed={r['axis'] for r in rows if r['event']=='path_reviewed'}
    if 'post_stop_closure_review' not in p:return reviewed
    proof=c.checked_log(p['post_stop_closure_review'],read)
    if len(proof)!=1:raise ValueError('Single post-stop closure review required')
    witness=proof[0];first,last=rows[0],rows[-1]
    final_state=dict(last['state'],sequence=reference_sequence(p,rows,read))
    if (p['profile'] not in (OVERHEAD_ARC_PROFILES|OPERATOR_ARC_PROFILES) or p['restore_after_power_cycle'] or reviewed!=set(range(1,6))
            or first.get('profile')!='person-overhead-high280-yaw160-probe'
            or [r['axis'] for r in rows if r['event']=='probe_complete']!=list(range(1,7))
            or witness.get('event')!='post_stop_closure_review' or witness.get('reviewed_stage')!=6
            or witness.get('source_log_sha256')!=p['baseline_source']['sha256']
            or witness.get('boot_id')!=p['boot_id'] or witness.get('state')!=final_state
            or witness.get('fresh_dual_view_reviewed') is not True
            or not isinstance(witness.get('views'),dict) or set(witness['views'])!={'front','top'}
            or any(not v.get('frame_id') or not c.re.fullmatch('[a-f0-9]{64}',v.get('jpeg_sha256','')) for v in witness['views'].values())):
        raise ValueError('Post-stop review must bind only the completed high-160 final reference')
    # Board UTC is not synchronized with Windows. On hardware, use uptime from
    # the same verified boot; host-side validation uses its own UTC timestamp.
    if wall is not None:
        age=wall()*1000-witness.get('reviewed_at_unix_ms',-1)
    else:
        stamp=witness.get('board_monotonic_seconds')
        if type(stamp) not in (int,float):raise ValueError('Board monotonic closure timestamp required')
        age=(time.monotonic()-stamp)*1000
    if type(witness.get('reviewed_at_unix_ms')) is not int or not 0<=age<120000:
        raise ValueError('Post-stop closure review expired')
    return reviewed|{6}

def audit_support_prefix(p,baseline,read=None):
    """Only the interrupted support edge of this frontal gesture may resume."""
    rows=c.checked_log(p['resume_route_log'],read)
    target=BASE[:]
    for i,offset in enumerate(ROUTES[p['profile']][1]):target[i]+=offset
    first,last=rows[0],rows[-1]
    if (first.get('event')!='reference_held' or first.get('profile')!=p['profile']
            or first.get('route_sha256')!=digest(p['profile']) or first.get('tempo_step_us')!=3
            or [r['axis'] for r in rows if r['event']=='probe_complete']!=[1]
            or [r['axis'] for r in rows if r['event']=='probe_started']!=[1]
            or any(r['event'] in ('path_reviewed','demo_started','demo_complete','route_cycle_complete') for r in rows)
            or last.get('event')!='outputs_off' or last.get('normal_frame_stop') is not True
            or last['state']['pulse_us']!=target or p['expected_pulses_us']!=target
            or last['state']['sequence']!=p['expected_sequence']):
        raise ValueError('Only the immutable interrupted support prefix may resume')
    previous=baseline
    for index,row in enumerate(r for r in rows if 'state' in r):
        state=row['state'];is_off=row['event']=='outputs_off'
        if (state['pending'] or state['faults'] or state['enabled_mask']!=(0 if is_off else 63)
                or state['armed'] is not (not is_off)
                or state['sequence'] not in (previous['sequence'],(previous['sequence']+1)%2**32)
                or (index==0 and (state['sequence']!=(previous['sequence']+1)%2**32 or state['pulse_us']!=BASE))
                or (state['sequence']==previous['sequence'] and state['pulse_us']!=previous['pulse_us'])
                or max(abs(a-b) for a,b in zip(previous['pulse_us'],state['pulse_us']))>3
                or any(state['pulse_us'][i]!=BASE[i] for i in (0,1,2,4,5,6,7,8,9))
                or not target[3]<=state['pulse_us'][3]<=BASE[3]):
            raise ValueError('Interrupted support command chain is inconsistent')
        previous=state

def validate_plan(p,read=None,wall=None):
    fields={'approval','session_id','profile','expected_sequence','expected_pulses_us',
     'observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed','reviewed_at_unix_ms',
     'duration_seconds','tempo_step_us','repetitions','boot_id','restore_after_power_cycle','baseline_source'}
    if (not isinstance(p,dict) or not fields<=set(p) or set(p)-fields-{'prior_slow_route_log','prior_high_route_log','post_stop_closure_review','held_reference_log','execution_mode','resume_waypoint','resume_route_log'}
            or p['approval']!=c.APPROVAL or p['profile'] not in ROUTES
            or not c.re.fullmatch('[a-z0-9-]{1,80}',p['session_id'])
            or type(p['expected_sequence']) is not int or not 0<=p['expected_sequence']<2**32
            or any(p[k] is not True for k in ('observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed'))
            or type(p['restore_after_power_cycle']) is not bool
            or type(p['tempo_step_us']) is not int or p['tempo_step_us'] not in (3,8) or p['repetitions']!=1
            or type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=900
            or not c.re.fullmatch('[a-f0-9-]{36}',p['boot_id'])
            or type(p['reviewed_at_unix_ms']) is not int):
        raise ValueError('Exact attended overhead mapping plan required')
    trial=p['profile'] in OPERATOR_ARC_PROFILES
    if (trial and (p.get('execution_mode')!='operator-attended-one-arc-trial' or p['tempo_step_us']!=8
                  or p['restore_after_power_cycle'] or 'prior_slow_route_log' in p)
            or not trial and 'execution_mode' in p):
        raise ValueError('Operator arc trial requires its explicit single-trial mode')
    resume=p.get('resume_waypoint',0)
    if (type(resume) is not int or resume not in (0,1)
            or ('resume_waypoint' in p)!=('resume_route_log' in p)
            or ('resume_waypoint' in p and (resume!=1 or p['profile']!='person-reference-guard-counter-probe'
                or p['restore_after_power_cycle'] or p['tempo_step_us']!=3))):
        raise ValueError('Only current-boot slow support-prefix continuation is allowed')
    if p['tempo_step_us']==3 and 'prior_slow_route_log' in p:
        raise ValueError('Slow diagnostic cannot include a fast-route receipt')
    if p['profile'] in (SLOW_DIAGNOSTIC_PROFILES|CONTINUOUS_PRESENTATION_PROFILES|OPERATOR_ARC_PROFILES) and p['restore_after_power_cycle']:
        raise ValueError('Local hand yaw review requires the current-boot closed reference')
    if p['tempo_step_us']==8 and not trial:
        if (p['profile'] not in FAST_GESTURE_PROFILES or p['restore_after_power_cycle']
                or 'prior_slow_route_log' not in p):
            raise ValueError('Faster gesture requires an unchanged boot and its completed slow-route receipt')
        slow=c.checked_log(p['prior_slow_route_log'],read)
        first_slow=next(r for r in slow if r['event']=='reference_held')
        last_slow=slow[-1]
        if (first_slow.get('profile')!=p['profile'] or first_slow.get('route_sha256')!=digest(p['profile'])
                or first_slow.get('tempo_step_us')!=3
                or [r['axis'] for r in slow if r['event']=='probe_complete']!=list(range(1,7))
                or {r['axis'] for r in slow if r['event']=='path_reviewed'}!=set(range(1,7))
                or last_slow['event']!='outputs_off' or last_slow.get('normal_frame_stop') is not True
                or last_slow['state']['pulse_us']!=BASE or last_slow['state']['enabled_mask']!=0
                or last_slow['state']['armed'] or last_slow['state']['pending'] or last_slow['state']['faults']):
            raise ValueError('The same complete slow gesture must be reviewed and closed at the reference')
    if wall is not None and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000:
        raise ValueError('Fresh dual-view pose review required')
    rows=c.checked_log(p['baseline_source'],read)
    expected_reference_sequence=reference_sequence(p,rows,read)
    reviewed=checked_reviews(p,rows,read,wall)
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
            or (not resume and (p['expected_pulses_us']!=BASE or p['expected_sequence']!=expected_reference_sequence))
            or reviewed!=set(range(1,7))):
        raise ValueError('Continuation requires the complete reviewed mapping route')
    if resume:audit_support_prefix(p,final['state'],read)
    if p['profile']=='person-script-hand-b-inward-80-probe' and first.get('profile') not in HAND_B_YAW_PROFILES:
        raise ValueError('Second inward level requires the completed local hand-B yaw review')
    if p['profile']=='person-script-hand-b-inward-fold-probe' and first.get('profile') not in HAND_B_DIAGNOSTIC_PROFILES:
        raise ValueError('Combined hand pitch review requires the completed local hand-B yaw review')
    if p['profile']=='person-script-hand-a-inward-80-probe' and first.get('profile') not in HAND_A_YAW_PROFILES:
        raise ValueError('Second inward level requires the completed local hand-A yaw review')
    if p['profile'] in OVERHEAD_LIFT_PROFILES and first.get('profile') not in (OVERHEAD_LIFT_PROFILES|{'person-overhead-lift-clearance'}):
        raise ValueError('Additional overhead lift requires the completed 210-us lift review')
    if p['profile'] in OVERHEAD_BODY_PROFILES and first.get('profile') not in (OVERHEAD_BODY_PROFILES|OVERHEAD_LIFT_PROFILES):
        raise ValueError('Overhead body coupling requires the completed 280-us lift review')
    if p['profile'] in OVERHEAD_APPROACH_PROFILES and first.get('profile') not in (OVERHEAD_APPROACH_PROFILES|OVERHEAD_BODY_PROFILES):
        raise ValueError('High lateral approach requires the completed overhead body review')
    if ('prior_high_route_log' in p)!=(p['profile'] in OVERHEAD_WIDER_PROFILES):
        raise ValueError('Wider high approach requires its explicit prior high-route receipt')
    if p['profile'] in OVERHEAD_WIDER_PROFILES:
        high=c.checked_log(p['prior_high_route_log'],read);hf,hl=high[0],high[-1]
        if (first.get('profile') not in (HAND_A_YAW_PROFILES|OVERHEAD_WIDER_PROFILES)
                or hf.get('event')!='reference_held' or hf.get('profile') not in (OVERHEAD_APPROACH_PROFILES|OVERHEAD_WIDER_PROFILES)
                or hf.get('route_sha256')!=digest(hf['profile']) or hf.get('tempo_step_us')!=3
                or [r['axis'] for r in high if r['event']=='probe_complete']!=list(range(1,7))
                or {r['axis'] for r in high if r['event']=='path_reviewed'}!=set(range(1,7))
                or hl['event']!='outputs_off' or hl.get('normal_frame_stop') is not True
                or hl['state']['pulse_us']!=BASE or hl['state']['enabled_mask'] or hl['state']['armed']
                or hl['state']['pending'] or hl['state']['faults']):
            raise ValueError('Wider approach requires closed low-yaw and high-80 reviews')
    if p['profile'] in OVERHEAD_ARC_PROFILES and first.get('profile') not in (OVERHEAD_ARC_PROFILES|OVERHEAD_WIDER_PROFILES):
        raise ValueError('Arc entry requires the completed high-160 review')
    if trial and first.get('profile') not in (OVERHEAD_WIDER_PROFILES|OVERHEAD_ARC_PROFILES|OPERATOR_ARC_PROFILES):
        raise ValueError('Operator arc trial requires the observed high-160 reference')


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
        self.cursor=p.get('resume_waypoint',0);self.completed=set(range(1,self.cursor+1));self.reviewed=set();self.demo_used=False
        self.own=63;self.indices=range(6);self.route_sha256=digest(p['profile'])
        self.targets=[BASE[:] for _ in ROUTES[p['profile']]]
        for target,vector in zip(self.targets,ROUTES[p['profile']]):
            for i,v in enumerate(vector):target[i]+=v

    def check(self):
        if self.boot_id_path.read_text().strip()!=self.plan['boot_id']:
            raise RuntimeError('Boot changed; do not rearm')
        if self.demo_used:
            if (self.plan['profile'] not in CONTINUOUS_PRESENTATION_PROFILES
                    or self.plan['tempo_step_us']!=8
                    or self.reviewed!=set(range(1,7)) or self.completed!=set(range(1,7))):
                raise RuntimeError('Overhead mapping is diagnostic-only; only the specific slow-and-fast-reviewed frontal presentation may run once')
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


def run_operator_arc_trial(d,emit,sleep=time.sleep):
    """One user-triggered candidate trial; never fabricates visual review events."""
    if d.plan.get('execution_mode')!='operator-attended-one-arc-trial' or d.plan['profile'] not in OPERATOR_ARC_PROFILES:
        raise ValueError('Explicit operator trial required')
    if getattr(d,'operator_trial_used',False):raise RuntimeError('Operator trial already used')
    d.operator_trial_used=True
    normal=False
    try:
        state=d.adopt(d.plan['expected_pulses_us'][:])
        emit(dict(event='reference_held',profile=d.plan['profile'],route_sha256=d.route_sha256,
                  tempo_step_us=8,execution_mode=d.plan['execution_mode'],state=state,position_feedback=None,
                  incident_locks_removed=False))
        d.wait(.25,sleep)
        emit(dict(event='operator_trial_started',state=d.status(),visual_reviews_performed=False))
        for stage in range(1,7):
            d.advance(stage,emit,sleep);d.wait(.12,sleep)
        emit(dict(event='operator_trial_complete',state=d.status(),visual_reviews_performed=False,
                  overhead_crossing_verified=False,automatic_replay_allowed=False))
        normal=True
    finally:
        state=d.stop_after_frame() if normal else d.off()
        emit(dict(event='outputs_off',state=state,normal_frame_stop=normal,incident_locks_removed=False))

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
            if p.get('execution_mode')=='operator-attended-one-arc-trial':run_operator_arc_trial(d,c.motion_emitter(log))
            else:c.run_session(d,c.motion_emitter(log))
    finally:r.close()

if __name__=='__main__':main()
