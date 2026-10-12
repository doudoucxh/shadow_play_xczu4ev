import copy
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import puppet_choreography_session as c
from test_servo_commissioning import FakeRegisters

class Host:
    action=None
    def check(self):pass

class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lock=self.root/'lock';self.lock.write_text('incident')
        self.now=0;self.host=Host();self.events=[]

    def build(self,profile):
        r=FakeRegisters();values=c.PERSON_REFERENCE+[1500]*4
        for i,v in enumerate(values):r.values[0x80+i*4]=v
        r.values[0x20]=1
        off=dict(sequence=1,pulse_us=values,enabled_mask=0,armed=False,pending=False,faults=0)
        held=dict(off,sequence=0,enabled_mask=63 if profile.startswith('person-') else 960,armed=True)
        p=dict(approval=c.APPROVAL,session_id='test',profile=profile,expected_sequence=1,
            expected_pulses_us=values,reference_held_state=held,reference_off_state=off,
            reference_normal_frame_stop=True,intervening_board_logs=[],observer_ready=True,
            operator_unchanged_report='电源和机构都没动',dual_view_pose_reviewed=True,
            reviewed_at_unix_ms=1000000,duration_seconds=120,tempo_step_us=3,repetitions=1)
        d=c.ChoreographySession(r,p,self.host,motion_inhibit_paths=[self.lock],
            cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000)
        return r,p,d

    def sleep(self,dt):self.now+=dt

    def test_closed_routes_keep_other_group_static_and_bound_steps(self):
        for profile in c.PROFILES:
            self.now=0;self.events=[];self.host=Host();r,p,d=self.build(profile)
            d.adopt(d.pulses[:]);d.phase='holding'
            for n in range(1,len(d.targets)):d.advance(n,self.events.append,self.sleep)
            states=[e['state'] for e in self.events if e['event']=='probe_step']
            prior=p['expected_pulses_us']
            for s in states:
                self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,s['pulse_us'])),3)
                self.assertEqual(s['enabled_mask'],d.own)
                sl=slice(6,10) if d.own==63 else slice(0,6)
                self.assertEqual(s['pulse_us'][sl],p['expected_pulses_us'][sl]);prior=s['pulse_us']
            self.assertEqual(d.pulses,p['expected_pulses_us']);self.assertEqual(self.lock.read_text(),'incident')

    def test_unreviewed_edge_stops_and_does_not_return_automatically(self):
        r,p,d=self.build('person-connected-guard')
        def emit(e):
            self.events.append(e)
            if e['event']=='reference_held':self.host.action=('probe_1',d.sequence)
            elif e['event']=='probe_complete':self.host.action=('probe_2',d.sequence)
        with self.assertRaises(RuntimeError):c.run_session(d,emit,sleep=self.sleep)
        self.assertEqual(d.pulses,d.targets[1]);self.assertFalse(self.events[-1]['state']['armed'])

    def test_stale_state_and_changed_lock_cannot_arm(self):
        r,p,d=self.build('tiger-axis-map-a');r.values[0x20]=2
        with self.assertRaises(RuntimeError):d.adopt(d.pulses[:])
        r.values[0x20]=1;self.lock.write_text('changed')
        with self.assertRaises(RuntimeError):d.adopt(d.pulses[:])
        self.assertEqual(r.writes,[])

    def test_fast_route_needs_all_slow_reviews_and_exact_hash(self):
        r,p,d=self.build('tiger-axis-map-a');p['tempo_step_us']=8
        with self.assertRaises(ValueError):c.validate_plan(p)
        rows=[dict(event='reference_held',profile=p['profile'],route_sha256=c.route_hash(p['profile']),tempo_step_us=3)]
        rows += [dict(event='path_reviewed',axis=n) for n in range(1,7)]
        rows += [dict(event='outputs_off',normal_frame_stop=True,state=p['reference_off_state'])]
        raw='\n'.join(json.dumps(x) for x in rows).encode()
        p['prior_slow_route_log']=dict(path='/tmp/puppet-choreography-slow.jsonl',sha256=hashlib.sha256(raw).hexdigest())
        c.validate_plan(p);c.audit_logs(p,lambda path:raw)
        with self.assertRaises(ValueError):c.audit_logs(p,lambda path:raw+b' ')
        rows.pop(1);raw='\n'.join(json.dumps(x) for x in rows).encode()
        p['prior_slow_route_log']['sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):c.audit_logs(p,lambda path:raw)

    def test_resume_keeps_route_origin_and_rejects_missing_prefix_frame(self):
        r,p,d=self.build('person-martial-linked')
        p['tempo_step_us']=8;d.plan['tempo_step_us']=8
        self.events=[dict(event='reference_held',profile=p['profile'],route_sha256=c.route_hash(p['profile']),tempo_step_us=8,state=d.adopt(d.pulses[:]))]
        d.phase='holding';d.advance(1,self.events.append,self.sleep)
        held=d.check();off=d.stop_after_frame()
        self.events.append(dict(event='outputs_off',normal_frame_stop=True,state=off))
        base=c.PERSON_REFERENCE+[1500]*4
        slow=[dict(event='reference_held',profile=p['profile'],route_sha256=c.route_hash(p['profile']),tempo_step_us=3)]
        slow += [dict(event='path_reviewed',axis=n) for n in range(1,7)]
        slow += [dict(event='outputs_off',normal_frame_stop=True,state=dict(off,pulse_us=base))]
        logs={}
        def spec(name,rows):
            path='/tmp/puppet-choreography-'+name+'.jsonl';raw='\n'.join(json.dumps(x) for x in rows).encode();logs[path]=raw
            return dict(path=path,sha256=hashlib.sha256(raw).hexdigest())
        p.update(expected_sequence=off['sequence'],expected_pulses_us=off['pulse_us'],reference_held_state=held,
                 reference_off_state=off,resume_waypoint=1,resume_route_log=spec('prefix',self.events),prior_slow_route_log=spec('slow',slow))
        resumed=c.ChoreographySession(r,p,self.host,motion_inhibit_paths=[self.lock],cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000,read=logs.__getitem__)
        self.assertEqual(resumed.cursor,1);self.assertEqual(resumed.targets[0],base)
        self.assertEqual(resumed.targets[1],off['pulse_us'])
        resumed.adopt(resumed.pulses[:]);resumed.phase='holding'
        for n in range(2,7):resumed.advance(n,lambda e:None,self.sleep)
        self.assertEqual(resumed.pulses,base)
        missing=self.events[:];missing.pop(2)
        p['resume_route_log']=spec('missing',missing)
        with self.assertRaises(ValueError):c.audit_logs(p,logs.__getitem__)

if __name__=='__main__':unittest.main()
