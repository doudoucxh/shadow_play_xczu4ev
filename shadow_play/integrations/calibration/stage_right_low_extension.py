"""Scoped continuation from BK: tiger farther right/lower, then lower hand.
No replay of earlier reference poses and no automatic return.
"""
import hashlib
import json
import re

PROFILE='stage-right-low-v1'
START=[1515,1252,1515,1594,1506,1720,1630,1275,1670,1720]
TARGETS=[START,
 START[:6]+[1690,1250,1730,1720],
 START[:6]+[1730,1250,1770,1740],
 [1515,1212,1515,1554,1506,1720,1730,1250,1770,1740]]
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
    if not rows or rows[0].get('profile')!='stage-low-start-v1' or rows[0].get('route_sha256')!='d72981f319c816cbeb74ddee4bd090a3ecac771a3f5cb792eab6e1773d94a790':raise ValueError('BK lineage required')
    if not any(r.get('event')=='low_start_pose_held' and r.get('level')==6 for r in rows):raise ValueError('BK incomplete')
    last=rows[-1];s=last['state']
    if last['event']!='outputs_off' or last.get('normal_frame_stop') is not True:raise ValueError('Normal stop required')
    if s['pulse_us']!=START or p['expected_pulses_us']!=START or s['sequence']!=31824 or p['expected_sequence']!=31824 or s['enabled_mask'] or s['armed'] or s['faults'] or s['pending']:raise ValueError('BK reference changed')
    for q in TARGETS:
        for v,lo,hi in zip(q,[10,95,10,50,70,50,50,100,70,50],[260,260,260,170,260,170,190,190,200,170]):
            if not 500+lo*2000/270<=v<=500+hi*2000/270:raise ValueError('Outside inset envelope')

def main():
    import stage_low_start_trial_20261014 as base
    base.PROFILE=PROFILE;base.START=START;base.TARGETS=TARGETS;base.ROUTE_SHA=ROUTE_SHA
    base.validate=validate
    base.main()

if __name__=='__main__':main()
