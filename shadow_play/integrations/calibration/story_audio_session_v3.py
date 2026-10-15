"""One attended full candidate trial from BO 32296, not general playback.
Retains transport locks/lease/stop checks. Errors stop in place without return.
The source choreography remains unverified; execution does not certify effects.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time

import story_motion_v3_candidate as score
import duel_interaction_trial as trial

PROFILE = "story-audio-v3"
ROUTE_SHA = score.check_envelope()["route_sha256"]

MODES = {
 'full': (0.,score.DURATION,'/tmp/wusong-2-48k-20261014.mp3',
          'e001fb858ab32e4d0217bd7c5262667f8f077025e12be19fb21b82a1a8bd13e7')}


def validate(p, rows, wall=None):
    required={'approval','session_id','profile','story_mode','story_route_sha256',
              'expected_sequence','expected_pulses_us','observer_ready','operator_hardware_unmoved',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds','boot_id','baseline_source'}
    if set(p)!=required or p['profile']!=PROFILE or p['approval']!='attended-fixed-puppet-choreography-20261012':
        raise ValueError('Exact one-use attended candidate plan required')
    if p['story_mode']!='full' or p['story_route_sha256']!=ROUTE_SHA:
        raise ValueError('Compiled full candidate only')
    if not isinstance(p['session_id'],str) or not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']):raise ValueError('Invalid ID')
    if any(p[k] is not True for k in ('observer_ready','operator_hardware_unmoved','dual_view_pose_reviewed')):
        raise ValueError('Attended unchanged geometry and dual-view review required')
    if type(p['reviewed_at_unix_ms']) is not int or (wall and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000):
        raise ValueError('Stale review')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600:raise ValueError('Bounded session required')
    if not isinstance(p['boot_id'],str) or not re.fullmatch('[a-f0-9-]{36}',p['boot_id']):raise ValueError('Invalid boot')
    if not rows or rows[0].get('profile')!=trial.PROFILE or rows[0].get('route_sha256')!=trial.ROUTE_SHA:
        raise ValueError('BO fixed interaction lineage required')
    if {r.get('index') for r in rows if r.get('event')=='interaction_phrase_complete'}!={0,1,2,3} or not any(r.get('event')=='interaction_complete' for r in rows):
        raise ValueError('Four BO phrases must be complete')
    last=rows[-1];s=last['state']
    if last.get('event')!='outputs_off' or last.get('normal_frame_stop') is not True:raise ValueError('Normal stop required')
    if (s['pulse_us']!=score.START or p['expected_pulses_us']!=score.START or
        type(p['expected_sequence']) is not int or p['expected_sequence']!=32296 or s['sequence']!=32296 or
        s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']):
        raise ValueError('BO 32296 reference changed; commands are not feedback')
    score.check_envelope()


def run(d,emit,audio,sleep=time.sleep):
    normal=False
    original_check=d.check
    try:
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=ROUTE_SHA,
                  state=d.adopt(score.START[:]),story_mode='full',candidate_trial=True,
                  position_feedback=None,incident_locks_removed=False))
        report=0
        while True:
            d.check()
            if d.host.action is not None:
                action,seq=d.host.action;d.host.action=None
                if action!='demo' or seq!=d.sequence:raise RuntimeError('Fresh one-use review required')
                break
            if d.clock()>=report:
                emit(dict(event='hold_alive',awaiting='demo',state=d.check()))
                report=d.clock()+.5
            d.wait(.03,sleep)
        def guarded():
            audio.check()
            state=original_check()
            if d.host.action is not None:raise RuntimeError('No repeat or additional action during timeline')
            return state
        d.check=guarded
        onset=audio.start(d,sleep)
        emit(dict(event='audio_running_observed',audio_original_start_s=0,
                  board_monotonic_onset=onset,acoustic_latency_measured=False,state=d.check()))
        d.phase='timeline';d.plan['tempo_step_us']=24
        checkpoints=sorted(set([0,score.DURATION]+[t for track in (score.HUMAN,score.TIGER) for t,_,_ in track]))
        checkpoint=0;last_tick=onset
        while True:
            d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
            now=d.clock()
            # Never rush missed samples or jump forward after a scheduling stall.
            if now-last_tick>.060:raise RuntimeError('Timeline stalled; no catch-up permitted')
            t=min(score.DURATION,max(0,now-onset))
            if audio.finished and t<score.DURATION-.1:raise RuntimeError('Audio ended early')
            target=score.sample(t)
            if max(abs(x-y) for x,y in zip(target,d.pulses))>24:raise RuntimeError('Timeline step exceeds 24 us; no catch-up')
            d.next_command=target
            state=d.adopt(target);last_tick=now
            emit(dict(event='probe_step',phase='audio_timeline',audio_time_s=t,state=state))
            while checkpoint<len(checkpoints) and t>=checkpoints[checkpoint]:
                emit(dict(event='timeline_checkpoint',index=checkpoint,target_audio_time_s=checkpoints[checkpoint],audio_time_s=t,state=state))
                checkpoint+=1
            if t>=score.DURATION:break
        emit(dict(event='timeline_complete',original_range_s=[0,score.DURATION],state=d.check()))
        while not audio.finished:
            d.check()
            if d.clock()-onset>score.DURATION+1.5:raise RuntimeError('Audio completion overdue')
            d.wait(.02,sleep)
        emit(dict(event='audio_complete',player_output=audio.output,state=d.check()))
        emit(dict(event='story_complete',mode='full',full_show_executed=True,
                  actual_stage_effect_verified=False,candidate_trial=True,state=d.check()))
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

