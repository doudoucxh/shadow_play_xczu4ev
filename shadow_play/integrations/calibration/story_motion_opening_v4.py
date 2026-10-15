"""Offline R-based opening and duel candidate; no hardware or playback entry.

The R wrist pose is accepted for continuation, not certified as elbow-up hip.
The paired lift/hammer is a same-side intention, not a completed overhead
crossing or proof of loaded clearance. Head yaw stays at its reviewed value;
no global offset is applied to an old human route. Tiger and audio are retained.
"""
import hashlib
import json
import math

import story_motion_v3_candidate as previous

DURATION = previous.DURATION
HITS = previous.HITS[:]
MOTOR_READY = False
AUTOMATIC_REPLAY_ALLOWED = False
STATUS = 'withdrawn_after_S_component_review_head_too_high'
RAMP_FRACTION = previous.RAMP_FRACTION
INTERPOLATION = previous.INTERPOLATION
START = [1570,1242,1565,1414,1416,1600,1730,1250,1770,1740]
H0 = START[:6]
H_POINT = [1570,1242,1565,1414,1500,1580]
H_POINT_RETRACT = [1570,1242,1565,1414,1460,1660]
H_UP = [1570,1372,1565,1434,1500,1500]
H_HAMMER = [1570,1242,1565,1474,1540,1660]
H_GUARD = [1550,1292,1565,1454,1460,1600]
H_COUNTER = [1530,1272,1565,1434,1540,1580]
H_DUCK = [1510,1242,1565,1514,1460,1660]
H_READY = [1550,1262,1565,1434,1460,1620]
DEGREE_LIMITS = [(10,260),(95,260),(10,260),(50,170),(70,260),
                 (50,170),(50,190),(100,190),(70,200),(50,170)]
sample_track = previous.sample_track
blend = previous.blend


def make_human():
    track = {}
    def h(t, q, label):
        track[round(t,8)] = (list(q),label)

    for t,q,label in [
        (0,H0,'R wrist-near-side opening; hip effect unverified'),
        (1,H0,'read opening'),(2,H_READY,'notice tiger'),
        (3,H0,'watch'),(4.3,H_GUARD,'guard answering head rise'),
        (5.1,H_UP,'paired lift candidate against roar'),
        (6.1,H_DUCK,'lower under bite'),(6.9,H_COUNTER,'counter after bite'),
        (7.7,H_GUARD,'recover'),(9,H0,'release to dialogue'),
        (10,H0,'begin hill walk without rails'),
        (10.8,blend(H0,H_DUCK,.25),'step sink'),(11.6,H0,'step rise'),
        (12.4,blend(H0,H_DUCK,.25),'step sink'),(13.2,H0,'step rise'),
        (14,blend(H0,H_DUCK,.25),'step sink'),(14.8,H0,'step rise'),
        (16,H0,'hold wrist beside torso'),
        (17.5,H_POINT,'dialogue pointing 1'),(18.1,H_POINT_RETRACT,'point retract 1'),
        (19,H_POINT,'dialogue pointing 2'),(19.6,H_POINT_RETRACT,'point retract 2'),
        (20.6,H_POINT,'dialogue pointing 3'),(21.2,H_POINT_RETRACT,'point retract 3'),
        (22.3,H_POINT,'dialogue final point'),(23,H0,'release dialogue'),
        (23.7,blend(H0,H_DUCK,.25),'walk sink'),(24.4,H0,'walk rise'),
        (25.1,blend(H0,H_DUCK,.25),'walk sink'),(25.8,H0,'walk rise'),
        (26.5,blend(H0,H_DUCK,.25),'walk sink'),(27.2,H0,'walk rise'),
        (28,H_READY,'notice low tiger'),(29,H_GUARD,'read crouch'),
        (29.8,H_UP,'high paired block'),(30.7,H_DUCK,'duck pounce'),
        (31.35,H_COUNTER,'reply as rear lands'),(32,H_GUARD,'recover'),
        (33,H_READY,'invite feint'),(34,H_GUARD,'close guard'),
        (35,H_READY,'release feint'),(36.2,H_GUARD,'block short bite'),
        (37,H_READY,'release'),(38,H_DUCK,'duck renewed threat'),
        (38.65,H_COUNTER,'counter'),(39.4,H_GUARD,'guard'),
        (40.4,H_UP,'same-side paired lift candidate; no overhead crossing'),
        (41.1,H_HAMMER,'paired downward strike candidate'),
        (41.9,H_GUARD,'guard'),(42.7,H_DUCK,'lower evade'),
        (43.5,H_COUNTER,'answer bite'),(44.2,H_READY,'recover'),
        (45,H_GUARD,'take initiative'),(45.8,H_UP,'prepare accent')]:
        h(t,q,label)
    attacks = [H_HAMMER,H_COUNTER,H_HAMMER,H_COUNTER,
               H_COUNTER,H_UP,H_HAMMER,H_COUNTER]
    labels = ['paired hammer','counter punch','paired hammer','push reply',
              'block counter','rising reply','short paired hammer','final counter']
    for i,(t,q,label) in enumerate(zip(HITS,attacks,labels)):
        prep = H_UP if i in (0,2,6) else (H_DUCK if i==5 else H_GUARD)
        h(t-.30,prep,'prepare '+label)
        h(t,q,'P%02d '%(i+1)+label)
        h(t+.08,q,'readable attack accent')
        h(t+.32,H_GUARD,'recover guard')
    for t,q,label in [
        (58.2,H_READY,'release attacks'),(59.2,H_DUCK,'low finish'),
        (60.1,H_READY,'breath'),(61,H_DUCK,'low pull intention'),
        (62.4,H_GUARD,'pull'),(63.2,H_DUCK,'release'),
        (64.3,H_GUARD,'second pull'),(65.2,H_READY,'settle'),
        (66.5,H0,'return R-based command opening'),(DURATION,H0,'final hold')]:
        h(t,q,label)
    return [(t,q,label) for t,(q,label) in sorted(track.items())]


HUMAN = make_human()
TIGER = [(t,q[:],label) for t,q,label in previous.TIGER]


def sample(t):
    return sample_track(HUMAN,t)+sample_track(TIGER,t)


def check_envelope():
    lower = [math.ceil(500+lo*2000/270) for lo,_ in DEGREE_LIMITS]
    upper = [math.floor(500+hi*2000/270) for _,hi in DEGREE_LIMITS]
    rows = [sample(min(i*.02,DURATION)) for i in range(math.ceil(DURATION/.02)+1)]
    if not all(lo<=v<=hi for q in rows for v,lo,hi in zip(q,lower,upper)):
        raise ValueError('Outside mechanically inset command envelope')
    if any(q[2]!=1565 or not 1414<=q[3]<=1554 for q in rows):
        raise ValueError('Head-specific candidate bounds exceeded')
    peak = max(abs(x-y) for a,b in zip(rows,rows[1:]) for x,y in zip(a,b))
    velocity = max(max(abs(x-y) for x,y in zip(a[1],b[1])) /
                   ((b[0]-a[0])*(1-RAMP_FRACTION))
                   for track in (HUMAN,TIGER) for a,b in zip(track,track[1:]))
    certified = math.ceil(velocity*.025+1)
    if peak>22 or certified>22:
        raise ValueError('Candidate exceeds existing 22 us temporal step budget')
    return dict(status=STATUS,motor_ready=False,automatic_replay_allowed=False,
                duration_s=DURATION,peak_20ms_step_us=peak,
                certified_any_phase_25ms_step_us=certified,
                maximum_continuous_velocity_us_per_s=velocity,
                lower_us=lower,upper_us=upper,interpolation=INTERPOLATION,
                route_sha256=hashlib.sha256(json.dumps(
                    [INTERPOLATION,RAMP_FRACTION,HUMAN,TIGER],separators=(',',':')).encode()).hexdigest(),
                loaded_clearance_proven=False,hip_pose_verified=False,
                same_side_hammer_verified=False,overhead_crossing_verified=False)


if __name__=='__main__':
    print(json.dumps(check_envelope()))
