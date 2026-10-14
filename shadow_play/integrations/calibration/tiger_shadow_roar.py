"""One attended 4–7 second audio excerpt using the observed AZ shadow poses.

Only timing is new. No rails, new positions, repeats or automatic recentering.
"""
import bisect
import hashlib
import json
import math
import time

PROFILE='tiger-shadow-roar-v1'
START=[1515,1372,1515,1514,1506,1660,1510,1275,1550,1640]
LEVELS=[START[:7]+[a,START[8],b] for a,b in [(1275,1640),(1455,1640),(1535,1600),(1615,1520),(1695,1440)]]
TRACK=[(0,0),(.15,0),(.47,1),(.65,2),(.83,3),(1.01,4),(1.14,4),(1.32,3),(1.50,2),(1.68,1),(2.14,0),(3,0)]
ROUTE_SHA=hashlib.sha256(json.dumps([LEVELS,TRACK],separators=(',',':')).encode()).hexdigest()
CLIP='/tmp/roar-4-7-20261014.mp3'
CLIP_SHA='95b30fa8569cd87f441902fb58459e1c13e52f085448a24131b248c0f41d92c3'


def sample(t):
    if t<=0:return START[:]
    if t>=3:return START[:]
    i=bisect.bisect_right([x[0] for x in TRACK],t)-1
    (a,ia),(b,ib)=TRACK[i:i+2];u=.5-.5*math.cos(math.pi*(t-a)/(b-a))
    return [round(x+(y-x)*u) for x,y in zip(LEVELS[ia],LEVELS[ib])]


def run(d,emit,audio_factory,sleep=time.sleep):
    normal=False;audio=None;original_check=d.check
    try:
        audio=audio_factory()
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=ROUTE_SHA,
                  state=d.adopt(START[:]),position_feedback=None,incident_locks_removed=False))
        while d.host.action is None:d.wait(.03,sleep)
        action,sequence=d.host.action;d.host.action=None
        if action!='demo' or sequence!=d.sequence:raise RuntimeError('Fresh one-use static review required')
        def guarded():audio.check();return original_check()
        d.check=guarded
        onset=audio.start(d,sleep)
        emit(dict(event='audio_running_observed',original_audio_start_s=4,board_monotonic_onset=onset,
                  acoustic_latency_measured=False))
        d.phase='timeline';d.plan['tempo_step_us']=24;index=0
        while True:
            d.wait(max(0,.02-(d.clock()-d.last_start)),sleep)
            t=min(3,d.clock()-onset)
            if audio.finished and t<2.9:raise RuntimeError('Audio ended early')
            d.next_command=sample(t);s=d.adopt(d.next_command)
            emit(dict(event='probe_step',phase='shadow_roar',audio_time_s=4+t,state=s))
            while index<len(TRACK) and t>=TRACK[index][0]:
                emit(dict(event='roar_checkpoint',index=index,target_audio_time_s=4+TRACK[index][0],
                          audio_time_s=4+t,level=TRACK[index][1],state=s));index+=1
            if t>=3:break
        while not audio.finished:
            if d.clock()-onset>4.5:raise RuntimeError('Audio completion overdue')
            d.wait(.02,sleep)
        emit(dict(event='shadow_roar_complete',state=d.check(),original_audio_range_s=[4,7],
                  player_output=audio.output,actual_stage_effect_verified=False))
        normal=True
    finally:
        d.check=original_check
        try:emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),
                      normal_frame_stop=normal,incident_locks_removed=False))
        finally:
            if audio is not None:audio.close()


def main():
    import tiger_height_trial_20261014_r3 as actor
    import tiger_audio_segment_20261014 as sound
    validate_height=actor.validate
    def validate(p,rows,wall=None):
        if p.get('profile')!=PROFILE or p.get('route_sha256')!=ROUTE_SHA:raise ValueError('Exact shadow-roar plan required')
        if not rows or rows[0].get('profile')!=actor.PROFILE or not any(
            r['event']=='height_trial_complete' and r.get('highest_stage')==4 for r in rows):
            raise ValueError('Observed full AZ height route required')
        q=dict(p,profile=actor.PROFILE,route_sha256=actor.ROUTE_SHA);validate_height(q,rows,wall)
    actor.validate=validate
    sound.CLIP=CLIP;sound.CLIP_SHA=CLIP_SHA
    actor.run=lambda d,e:run(d,e,sound.AudioClip)
    actor.main()


if __name__=='__main__':main()
