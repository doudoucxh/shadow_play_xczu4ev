"""Offline choreography candidate: no device imports, runner or deployment hook.

The accepted BN opening is retained; feet touching the bottom is not claimed.
All poses are within the component-wise envelope of the four trial phrases.
This envelope is a command bound, not proof of loaded mechanical clearance.
"""
import bisect
import hashlib
import json
import math

import duel_interaction_trial as trial

DURATION = 2959360 / 44100
MOTOR_READY = False
AUTOMATIC_REPLAY_ALLOWED = False
STATUS = 'offline_candidate_not_executed'
# Flatten the cosine velocity peak without moving audio accents. Acceleration
# and deceleration each occupy 18% of an edge; velocity is continuous at joins.
RAMP_FRACTION = .18
INTERPOLATION = 'trapezoidal_velocity_quadratic_ramps_18_percent_v1'
START = trial.START[:]
HITS = [46.38, 47.78, 50.21, 51.68, 53.35, 54.56, 56.82, 57.44]
H0 = START[:6]
R, U, L, A, C, G = (trial.H_READY, trial.H_UP, trial.H_LOW,
                     trial.H_HIT, trial.H_COUNTER, trial.H_GUARD)
T0, TA, TR, TO, TP, TX, TS = (trial.T_LOW, trial.T_ALERT, trial.T_RISE,
                              trial.T_ROAR, trial.T_POUNCE,
                              trial.T_RECOIL, trial.T_SETTLE)


def blend(a, b, u):
    return [round(x + (y - x) * u) for x, y in zip(a, b)]


def make_tracks():
    human, tiger = {}, {}

    def h(t, q, label):
        human[round(t, 8)] = (list(q), label)

    def g(t, q, label):
        tiger[round(t, 8)] = (list(q), label)

    # Interleaved probes: one character initiates, the other responds.
    for t, q, label in [
        (0,H0,'accepted low opening; floor contact unverified'),
        (1.0,H0,'leave centre empty'),(1.8,blend(H0,R,.35),'notice probe'),
        (2.6,H0,'low hand release'),(3.5,blend(H0,R,.55),'tighten guard'),
        (4.3,R,'notice roar'),(5.1,G,'guard enlarged shadow'),
        (6.0,L,'lower under bite'),(6.9,C,'short reply'),(7.7,R,'recover'),
        (8.6,blend(R,L,.3),'watch'),(9.3,H0,'low hands'),
        (10,H0,'opening held'),(10.8,R,'body leads restrained entrance'),
        (11.8,G,'look toward tiger'),(12.8,R,'release hand'),
        (13.8,blend(R,U,.5),'single readable lift candidate'),
        (14.8,L,'lower hands'),(16,G,'notice threat'),(17,R,'dialogue'),
        (18,C,'point toward opponent'),(19,R,'retract'),
        (20,blend(R,U,.5),'open hands'),(21,L,'release'),
        (22,G,'watch tiger'),(23,R,'local tension, no rails'),
        (24,L,'lower guard'),(25,G,'answer high probe'),
        (26,R,'recover'),(27,L,'sink'),(28,G,'prepare'),
        (29,G,'observe crouch'),(29.8,U,'upper block'),
        (30.6,L,'duck downward bite'),(31.3,C,'counter after bite'),
        (32,G,'recover'),(33,R,'invite probe'),(34,G,'close guard'),
        (35,R,'feint'),(36.2,G,'first block only'),(37,R,'release'),
        (38.0,L,'duck second threat'),(38.6,C,'change-hand reply'),
        (39.4,G,'recover'),(40.4,U,'double lift'),(41.1,A,'double hammer'),
        (41.9,G,'recover guard'),(42.7,L,'lower evade'),
        (43.5,C,'counter toward tiger'),(44.2,R,'recover'),(45,G,'take initiative'),
        (45.8,U,'first strike preparation')]:
        h(t,q,label)

    # Different intentions use the existing candidate poses; labels do not
    # claim independently controlled fists or a completed overhead crossing.
    attacks = [A,C,A,C,C,C,A,C]
    labels = ['near punch','other hand punch','double hammer','paired push',
              'block and counter','sink then upper strike','short double hammer','last strike']
    for i,(t,q,label) in enumerate(zip(HITS,attacks,labels)):
        prep = U if i in (0,2,6) else (L if i == 5 else G)
        h(t-.30,prep,'prepare '+label)
        h(t,q,'P%02d '%(i+1)+label)
        h(t+.08,q,'readable attack accent')
        h(t+.32,G,'recover other hand to guard')
    for t,q,label in [(58.2,R,'release attacks'),(59.2,L,'low finish'),
                       (60.1,R,'breath'),(61,L,'low pull intent'),
                       (62.4,G,'pull'),(63.2,L,'release'),(64.3,G,'second pull'),
                       (65.2,L,'settle'),(66.5,H0,'return accepted opening'),
                       (DURATION,H0,'final hold')]:
        h(t,q,label)

    for t,q,label in [(0,T0,'tree-side low'),(1,T0,'watch'),
        (1.5,blend(T0,TA,.5),'first probe'),(2.1,T0,'withdraw'),
        (2.7,TA,'deeper probe'),(3.2,blend(T0,TA,.35),'short retract'),
        (3.5,blend(T0,TA,.5),'bounded tremor'),(3.8,blend(T0,TA,.3),'bounded tremor release'),
        (4.3,TR,'head rises'),(5.1,TO,'shadow roar'),(5.4,TO,'brief suspension'),
        (6.1,TP,'roar must lead into bite'),(6.8,TS,'rear lands'),
        (7.7,TA,'seek another opening'),(8.5,T0,'low'),(9.2,blend(T0,TA,.2),'tension'),
        (10,T0,'watch human'),(11,TA,'turn toward human'),(12,T0,'retract at gaze'),
        (13,blend(T0,TA,.5),'probe'),(13.4,blend(T0,TA,.3),'short recoil'),
        (13.8,blend(T0,TA,.6),'second probe'),(14.5,T0,'yield dialogue'),
        (16,TA,'trigger notice'),(17,T0,'withdraw'),(18,blend(T0,TA,.25),'breath'),
        (19,T0,'release'),(20,blend(T0,TA,.45),'search'),(21,T0,'release'),
        (22,TA,'notice pointing'),(23,T0,'low'),(24,TA,'high feint'),
        (25,TS,'leave rear behind'),(26,TA,'second feint'),(27,T0,'crouch'),
        (28,TS,'stretch before leap'),(29,TS,'ready'),(29.65,TR,'head leads up'),
        (30.05,TO,'rear follows high'),(30.7,TP,'head dives first'),
        (31.35,TS,'rear lands'),(32,T0,'recover'),(32.6,TA,'search'),
        (33.1,blend(T0,TA,.3),'withdraw'),(33.4,blend(T0,TA,.5),'double tremor'),
        (33.7,blend(T0,TA,.3),'release'),(34.4,T0,'low'),(35.5,TR,'first short threat'),
        (36.2,TP,'short bite'),(37,TS,'withdraw'),(37.65,TO,'second larger shadow threat'),
        (38.4,TP,'second bite'),(39.15,TX,'human counter recoil'),(40,T0,'low'),
        (40.6,TA,'press into lift'),(41.2,TX,'double hammer reaction'),
        (41.9,TR,'raise threat'),(42.6,TP,'bite after raise'),
        (43.3,TX,'recoil'),(44,TS,'recover'),(45,T0,'low tension')]:
        g(t,q,label)
    for i,t in enumerate(HITS):
        # Short impact windows cannot contain the full pounce displacement.
        # Keep large motion in the longer roar/leap phrases, not sharp jumps.
        strength=.58*(1-.07*i)
        g(t-.25,TS,'prepare reaction')
        head=blend(TS,TX,strength);head[2:]=TS[2:]
        g(t+.06,head,'head reacts P%02d'%(i+1))
        g(t+.20,blend(TS,TX,strength),'rear follows')
        # No new large lunge between the two closest final hits.
        g(t+.36,TS,'low recovery')
        if i+1<len(HITS) and HITS[i+1]-t>1.5:
            g((t+.36+HITS[i+1]-.25)/2,blend(TS,TA,.25),
              'search opening between impacts')
    for t,q,label in [(58.36,T0,'low collapse intent; fall unverified'),
                      (59.2,T0,'weak finish'),(60.1,blend(T0,TA,.1),'last breath'),
                      (61,T0,'still'),(62.4,blend(T0,TA,.15),'follow pull'),
                      (63.2,T0,'settle'),(64.3,blend(T0,TA,.1),'weaker second pull'),
                      (65.2,T0,'settle'),(66.5,T0,'final'),(DURATION,T0,'hold')]:
        g(t,q,label)
    return [ [(t,q,label) for t,(q,label) in sorted(track.items())] for track in (human,tiger)]


HUMAN,TIGER=make_tracks()


def sample_track(track,t):
    if t<=track[0][0]:return track[0][1][:]
    if t>=track[-1][0]:return track[-1][1][:]
    i=bisect.bisect_right([row[0] for row in track],t)-1
    a,b=track[i:i+2]
    x=(t-a[0])/(b[0]-a[0]);r=RAMP_FRACTION
    if x<r:u=x*x/(2*r*(1-r))
    elif x>1-r:u=1-(1-x)*(1-x)/(2*r*(1-r))
    else:u=(x-r/2)/(1-r)
    return blend(a[1],b[1],u)


def sample(t):
    return sample_track(HUMAN,t)+sample_track(TIGER,t)


def check_envelope():
    bounds=list(zip(*trial.TARGETS))
    lower=[min(values) for values in bounds]
    upper=[max(values) for values in bounds]
    rows=[sample(min(i*.02,DURATION)) for i in range(math.ceil(DURATION/.02)+1)]
    assert all(lo<=v<=hi for q in rows for v,lo,hi in zip(q,lower,upper))
    peak=max(abs(x-y) for a,b in zip(rows,rows[1:]) for x,y in zip(a,b))
    if peak>22:raise ValueError('20 ms step exceeds 22 us: '+str(peak))
    # Global Lipschitz bound covers every phase, including intervals crossing
    # keyframes. Two nearest-integer roundings add less than one microsecond.
    velocity=max(max(abs(x-y) for x,y in zip(a[1],b[1]))/
                 ((b[0]-a[0])*(1-RAMP_FRACTION))
                 for track in (HUMAN,TIGER) for a,b in zip(track,track[1:]))
    certified_25ms=math.ceil(velocity*.025+1)
    if certified_25ms>22:raise ValueError('Any-phase 25 ms bound exceeds 22 us')
    return {'status':STATUS,'motor_ready':False,'automatic_replay_allowed':False,
            'duration_s':DURATION,'peak_20ms_step_us':peak,'lower_us':lower,'upper_us':upper,
            'maximum_continuous_velocity_us_per_s':velocity,
            'certified_any_phase_25ms_step_us':certified_25ms,
            'interpolation':INTERPOLATION,
            'route_sha256':hashlib.sha256(json.dumps([INTERPOLATION,RAMP_FRACTION,HUMAN,TIGER],separators=(',',':')).encode()).hexdigest(),
            'loaded_clearance_proven':False,'feet_at_bottom_verified':False}


if __name__=='__main__':
    print(json.dumps(check_envelope()))
