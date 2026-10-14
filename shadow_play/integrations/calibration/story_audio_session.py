"""Explicit attended fixed story trial. Locks retained; no arbitrary pose input.

Full mode holds its final pose until audio finishes, then stops outputs. It never
automatically centers. Fight-only rehearsal has a separately logged exit route.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time

import story_motion as score

MODES = {
 'fight': (44.,58.,'/tmp/fight-44-58-20261014.mp3',
           '107fcd9d8e10d5b2fa19979974aacef07557381e611fbe0fcec200cc2314cfcd'),
 'full': (0.,score.DURATION,'/tmp/wusong-2-48k-20261014.mp3',
          'e001fb858ab32e4d0217bd7c5262667f8f077025e12be19fb21b82a1a8bd13e7')}


def validate(p, rows, wall=None):
    required={'approval','session_id','profile','story_mode','story_route_sha256',
              'expected_sequence','expected_pulses_us','observer_ready','operator_hardware_unmoved',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds','boot_id','baseline_source'}
    if set(p)!=required or p['profile']!='story-audio-v1' or p['approval']!='attended-fixed-puppet-choreography-20261012':
        raise ValueError('Exact attended story plan required')
    if p['story_mode'] not in MODES or p['story_route_sha256']!=score.route_digest():
        raise ValueError('Only compiled story version and modes')
    if not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):raise ValueError('Invalid session ID')
    if any(p[x] is not True for x in ['observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed']):
        raise ValueError('Onsite cutoff, unchanged mechanism and fresh dual-view review required')
    if type(p['reviewed_at_unix_ms']) is not int or (wall and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000):
        raise ValueError('Stale review')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600:
        raise ValueError('Bounded attended session required')
    if not re.fullmatch('[a-f0-9-]{36}',p['boot_id']):raise ValueError('Boot ID required')
    if not rows or rows[-1]['event']!='outputs_off' or rows[-1].get('normal_frame_stop') is not True:
        raise ValueError('Reference did not close normally')
    s=rows[-1]['state']
    if (s['pulse_us']!=score.BASE or p['expected_pulses_us']!=score.BASE or s['sequence']!=p['expected_sequence']
        or s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']):
        raise ValueError('Only recently inspected unchanged BASE may start; registers are not feedback')
    if rows[0].get('profile') not in ('tiger-operator-low-rear-fast','story-audio-v1'):
        raise ValueError('Unsupported reference lineage')
    if rows[0].get('profile')=='story-audio-v1':
        if rows[0].get('route_sha256')!=score.route_digest() or not any(r['event']=='story_complete' for r in rows):
            raise ValueError('Incomplete story reference')
    elif not any(r['event']=='operator_trial_complete' for r in rows):
        raise ValueError('Incomplete tiger reference')
    score.check_envelope()


def run(d,emit,audio,sleep=time.sleep):
    normal=False
    original_check=d.check
    try:
        emit(dict(event='reference_held',profile='story-audio-v1',route_sha256=score.route_digest(),
                  state=d.adopt(score.BASE[:]),story_mode=d.plan['story_mode'],
                  position_feedback=None,incident_locks_removed=False))
        while True:
            d.check()
            if d.host.action is not None:
                action,sequence=d.host.action;d.host.action=None
                if action!='demo' or sequence!=d.sequence:raise RuntimeError('Fresh one-use static review required')
                break
            d.wait(.03,sleep)
        def travel(targets,label):
            emit(dict(event=label+'_started',state=d.check()))
            d.targets=[d.pulses[:]]+targets;d.cursor=0
            d.plan['tempo_step_us']=8
            for i in range(1,len(d.targets)):
                d.advance(i,emit,sleep);d.wait(.10,sleep)
            emit(dict(event=label+'_complete',state=d.check()))
        if d.plan['story_mode']=='fight':
            travel([h+score.T[0] for h in (score.H[1],score.H[2],score.H[3])],'entry')
        def guarded():
            audio.check()
            return original_check()
        d.check=guarded
        onset=audio.start(d,sleep)
        begin,end,*_=MODES[d.plan['story_mode']]
        emit(dict(event='audio_running_observed',audio_original_start_s=begin,board_monotonic_onset=onset,
                  acoustic_latency_measured=False,state=d.check()))
        d.phase='timeline';d.plan['tempo_step_us']=24
        checkpoints=sorted(set([begin,end]+[t for track in (score.HUMAN,score.TIGER) for t,_,_ in track if begin<t<end]))
        checkpoint=0
        while True:
            d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
            t=min(end,begin+d.clock()-onset)
            if audio.finished and t<end-.1:raise RuntimeError('Audio ended before story deadline')
            d.next_command=score.sample(t)
            state=d.adopt(d.next_command)
            emit(dict(event='probe_step',phase='audio_timeline',audio_time_s=t,state=state))
            while checkpoint<len(checkpoints) and t>=checkpoints[checkpoint]:
                emit(dict(event='timeline_checkpoint',index=checkpoint,target_audio_time_s=checkpoints[checkpoint],
                          audio_time_s=t,state=state));checkpoint+=1
            if t>=end:break
        emit(dict(event='timeline_complete',original_range_s=[begin,end],state=d.check()))
        while not audio.finished:
            d.check()
            if d.clock()-onset>end-begin+1.5:raise RuntimeError('Audio completion overdue')
            d.wait(.02,sleep)
        emit(dict(event='audio_complete',player_output=audio.output,state=d.check()))
        d.check=original_check
        if d.plan['story_mode']=='fight':
            # Return through the observed AG exit corridor; not an automatic center.
            travel([score.H[3]+score.T[6],score.H[3]+score.T[0],score.H[6]+score.T[0],
                    score.H[7]+score.T[0],score.BASE[:]],'segment_exit')
        emit(dict(event='story_complete',mode=d.plan['story_mode'],full_show_executed=d.plan['story_mode']=='full',
                  actual_stage_effect_verified=False,state=d.check()))
        normal=True
    finally:
        d.check=original_check
        try:
            emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),
                      normal_frame_stop=normal,incident_locks_removed=False))
        finally:audio.close()


def main():
    import hand_crossing_session_20261014_r36 as h
    import tiger_audio_segment_20261014 as audio_module
    c=h.c
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path)
    parser.add_argument('--expected-plan-sha256',required=True)
    parser.add_argument('--execute-attended-fixed-choreography',action='store_true');args=parser.parse_args()
    raw=args.plan.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_plan_sha256:raise ValueError('Reviewed plan changed')
    p=json.loads(raw);rows=c.checked_log(p['baseline_source']);validate(p,rows)
    if not args.execute_attended_fixed_choreography:
        print(json.dumps(dict(dry_run=True,mode=p['story_mode'],**score.check_envelope())));return
    class StorySession(c.ChoreographySession):
        def __init__(self,r,host):
            c.PwmDevice.__init__(self,r)
            self.boot=Path('/proc/sys/kernel/random/boot_id')
            marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
            if self.boot.read_text().strip()!=p['boot_id'] or marker.get('sha256')!=h.IMAGE_SHA:
                raise RuntimeError('Boot/image changed')
            self.plan=dict(p,tempo_step_us=8);self.host=host;self.clock=time.monotonic
            self.deadline=self.clock()+p['duration_seconds'];self.cancel=Path('/run/shadow-pwm-recovery-cancel')
            self.hashes=self.lock_hashes();self.pulses=p['expected_pulses_us'][:]
            self.sequence=p['expected_sequence'];self.mask=0;self.inside=False;self.failed=False
            self.last_start=None;self.next_command=None;self.phase='resume';self.cursor=0
            self.completed=set();self.reviewed=set();self.demo_used=False;self.own=1023
            self.indices=range(10);self.targets=[]
        def check(self):
            if self.boot.read_text().strip()!=p['boot_id']:raise RuntimeError('Boot changed')
            return super().check()
    def interrupt(*unused):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    _,_,audio_module.CLIP,audio_module.CLIP_SHA=MODES[p['story_mode']]
    audio=audio_module.AudioClip()
    host=c.HostControl(sys.stdin.fileno());print(json.dumps(dict(event='await_host_lease')),flush=True)
    while not host.received:host.check();time.sleep(.02)
    r=c.Registers()
    try:
        d=StorySession(r,host)
        with (Path('/tmp')/('puppet-choreography-'+p['session_id']+'.jsonl')).open('x') as log:
            run(d,c.motion_emitter(log),audio)
    finally:r.close();audio.close()


if __name__=='__main__':main()
