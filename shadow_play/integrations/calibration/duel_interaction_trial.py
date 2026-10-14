"""Four distinct attended interaction phrases; every phrase requires fresh review.
Initial feet-to-floor pose remains unresolved, not silently declared complete.
"""
import hashlib
import json
import re

PROFILE='duel-interaction-v1'
START=[1470,1212,1425,1514,1416,1740,1730,1250,1770,1740]
H_READY=[1470,1252,1465,1554,1460,1660]
H_UP=[1470,1372,1465,1514,1460,1500]
H_LOW=[1470,1212,1465,1594,1460,1720]
H_HIT=[1470,1212,1485,1594,1500,1660]
H_COUNTER=[1470,1252,1485,1554,1540,1580]
H_GUARD=[1530,1272,1485,1554,1440,1650]
T_LOW=START[6:]
T_ALERT=[1690,1335,1730,1700]
T_RISE=[1630,1535,1670,1640]
T_ROAR=[1570,1695,1610,1440]
T_POUNCE=[1510,1275,1550,1440]
T_RECOIL=[1630,1415,1670,1580]
T_SETTLE=[1690,1250,1730,1740]
def offset(q,changes):
    out=q[:]
    for i,v in changes.items():out[i]+=v
    return out
PHRASES=[
 ('watch_and_feint',[
  H_READY+T_LOW,
  offset(H_READY,{1:24,3:-12})+T_ALERT,
  offset(H_READY,{3:8,5:-20})+[1710,1280,1750,1720],
  H_GUARD+[1690,1360,1730,1700],
  H_READY+T_LOW]),
 ('shadow_roar_guard_pounce_counter',[
  H_READY+T_RISE,
  H_UP+T_ROAR,
  H_LOW+T_POUNCE,
  H_COUNTER+T_RECOIL,
  H_GUARD+T_SETTLE]),
 ('double_hammer_and_tiger_reaction',[
  H_UP+T_ALERT,
  H_HIT+T_RECOIL,
  H_GUARD+T_LOW,
  H_COUNTER+T_POUNCE,
  H_GUARD+T_SETTLE]),
 ('false_attack_recover_and_watch',[
  offset(H_GUARD,{1:20,3:-12})+T_ALERT,
  H_COUNTER+T_RISE,
  H_GUARD+T_SETTLE,
  H_READY+T_LOW,
  START])]
TARGETS=[START]+[q for _,phrase in PHRASES for q in phrase]
ROUTE_SHA=hashlib.sha256(json.dumps(TARGETS,separators=(',',':')).encode()).hexdigest()

def validate(p,rows,wall=None):
    required={'approval','session_id','profile','route_sha256','expected_sequence',
              'expected_pulses_us','observer_ready','operator_tiger_unmoved',
              'person_rods_shortened_mm','operator_axes_unmoved','power_on',
              'dual_view_pose_reviewed','reviewed_at_unix_ms','duration_seconds',
              'boot_id','baseline_source'}
    if set(p)!=required or p['profile']!=PROFILE or p['route_sha256']!=ROUTE_SHA:raise ValueError('Exact extension required')
    if p['approval']!='attended-fixed-puppet-choreography-20261012':raise ValueError('Attended trial required')
    if not re.fullmatch('[a-z0-9-]{1,80}',p['session_id']) or not re.fullmatch('[a-f0-9-]{36}',p['boot_id']):raise ValueError('Invalid identity')
    for k in ['observer_ready','operator_tiger_unmoved','operator_axes_unmoved','power_on','dual_view_pose_reviewed']:
        if p[k] is not True:raise ValueError('Missing condition')
    if p['person_rods_shortened_mm']!={'head':5,'right_hand':5}:raise ValueError('Geometry changed')
    if type(p['reviewed_at_unix_ms']) is not int or (wall and not 0<=wall()*1000-p['reviewed_at_unix_ms']<120000):raise ValueError('Expired review')
    if type(p['duration_seconds']) is not int or not 120<=p['duration_seconds']<=600:raise ValueError('Bounded session required')
    if not rows or rows[0].get('profile')!='person-hand-lower-v1' or rows[0].get('route_sha256')!='978dc54ab93ee1ced1bcd898606427091c53b143ae7c0fed053023d72bd6aa00':raise ValueError('BN lineage required')
    if not any(r.get('event')=='low_start_pose_held' and r.get('level')==2 for r in rows):raise ValueError('BN incomplete')
    last=rows[-1];s=last['state']
    if last['event']!='outputs_off' or last.get('normal_frame_stop') is not True:raise ValueError('Normal stop required')
    if s['pulse_us']!=START or p['expected_pulses_us']!=START or s['sequence']!=31900 or p['expected_sequence']!=31900 or s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']:raise ValueError('BN reference changed')
    for q in TARGETS:
        for v,lo,hi in zip(q,[10,95,10,50,70,50,50,100,70,50],[260,260,260,170,260,170,190,190,200,170]):
            if not 500+lo*2000/270<=v<=500+hi*2000/270:raise ValueError('Outside inset envelope')

def run(d,emit,sleep=__import__('time').sleep):
    normal=False
    try:
        emit(dict(event='reference_held',profile=PROFILE,route_sha256=ROUTE_SHA,state=d.adopt(START[:]),incident_locks_removed=False,position_feedback=None))
        phrase_index=0
        while True:
            d.check()
            if d.host.action is None:d.wait(.03,sleep);continue
            action,seq=d.host.action;d.host.action=None
            if seq!=d.sequence:raise RuntimeError('Stale command')
            if action=='finish':normal=True;break
            if action!='demo' or phrase_index>=len(PHRASES):raise RuntimeError('Next fixed phrase only')
            label,targets=PHRASES[phrase_index]
            d.plan['tempo_step_us']=12 if phrase_index==0 else 16
            d.targets=[d.pulses[:]]+targets;d.cursor=0
            emit(dict(event='interaction_phrase_started',index=phrase_index,label=label,state=d.check()))
            for i in range(1,len(d.targets)):
                d.advance(i,emit,sleep)
                emit(dict(event='interaction_checkpoint',phrase=phrase_index,index=i,label=label,state=d.check()))
                if phrase_index==0:d.wait([.13,.07,.19,.09,.04][i-1],sleep)
            emit(dict(event='interaction_phrase_complete',index=phrase_index,label=label,state=d.check(),visual_effect_verified=False))
            phrase_index+=1
            if phrase_index==len(PHRASES):
                emit(dict(event='interaction_complete',state=d.check()));normal=True;break
    finally:
        emit(dict(event='outputs_off',state=d.stop_after_frame() if normal else d.off(),normal_frame_stop=normal,incident_locks_removed=False))

def main():
    import stage_low_start_trial_20261014 as base
    base.PROFILE=PROFILE;base.START=START;base.TARGETS=TARGETS;base.ROUTE_SHA=ROUTE_SHA
    base.validate=validate;base.run=run
    base.main()

if __name__=='__main__':main()
