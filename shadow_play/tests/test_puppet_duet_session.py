import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import puppet_duet_session as duet
from test_servo_commissioning import FakeRegisters

class Host:
    action=None
    def check(self):pass

class DuetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lock=self.root/'lock';self.lock.write_text('incident')
        self.now=0;self.host=Host();self.logs={}
        self.r=FakeRegisters()
        for i,v in enumerate(duet.BASE):self.r.values[0x80+i*4]=v
        self.r.values[0x20]=1
        self.tiger=self.component(duet.TIGER,960,1)
        self.person=self.component(duet.PERSON,63,self.tiger[-1]['state']['sequence'])
        tiger_spec=self.spec('tiger',self.tiger);person_spec=self.spec('person',self.person)
        self.plan=dict(approval=duet.c.APPROVAL,session_id='test-duet',profile=duet.PROFILE,
            expected_sequence=self.person[-1]['state']['sequence'],expected_pulses_us=duet.BASE,
            observer_ready=True,operator_unchanged_report='电源和机构都没动',dual_view_pose_reviewed=True,
            reviewed_at_unix_ms=1000000,duration_seconds=120,tempo_step_us=8,repetitions=3,
            person_completed_log=person_spec,tiger_completed_log=tiger_spec,tiger_intervening_logs=[person_spec])

    def sleep(self,dt):self.now+=dt

    def spec(self,name,rows):
        path='/tmp/puppet-choreography-'+name+'.jsonl';raw='\n'.join(json.dumps(r) for r in rows).encode()
        self.logs[path]=raw
        return dict(path=path,sha256=hashlib.sha256(raw).hexdigest())

    def component(self,profile,mask,seq):
        off=dict(sequence=seq,pulse_us=duet.BASE,enabled_mask=0,armed=False,pending=False,faults=0)
        p=dict(approval=duet.c.APPROVAL,session_id='component',profile=profile,expected_sequence=seq,
            expected_pulses_us=duet.BASE,reference_held_state=dict(off,sequence=seq-1,enabled_mask=mask,armed=True),
            reference_off_state=off,reference_normal_frame_stop=True,intervening_board_logs=[],
            observer_ready=True,operator_unchanged_report='电源和机构都没动',dual_view_pose_reviewed=True,
            reviewed_at_unix_ms=1000000,duration_seconds=120,tempo_step_us=3,repetitions=1)
        d=duet.c.ChoreographySession(self.r,p,self.host,motion_inhibit_paths=[self.lock],cancel_path=self.root/'cancel',clock=lambda:self.now)
        d.plan['tempo_step_us']=8
        rows=[dict(event='reference_held',profile=profile,route_sha256=duet.c.route_hash(profile),tempo_step_us=8,state=d.adopt(d.pulses[:]))]
        d.phase='holding';rows.append(dict(event='demo_started',state=d.check()))
        for cycle in range(1,4):
            d.cursor=0
            for n in range(1,len(d.targets)):d.advance(n,rows.append,self.sleep)
            rows.append(dict(event='route_cycle_complete',cycle=cycle,state=d.check()))
        rows.append(dict(event='demo_complete',state=d.check()))
        rows.append(dict(event='outputs_off',normal_frame_stop=True,state=d.stop_after_frame()))
        return rows

    def device(self):
        return duet.DuetSession(self.r,self.plan,self.host,motion_inhibit_paths=[self.lock],cancel_path=self.root/'cancel',clock=lambda:self.now,wall=lambda:1000,read=self.logs.__getitem__)

    def test_duet_preserves_each_component_path_and_atomic_mask(self):
        d=self.device();d.adopt(d.pulses[:]);d.phase='holding';events=[]
        for n in range(1,len(d.targets)):d.advance(n,events.append,self.sleep)
        prior=duet.BASE
        for row in events:
            if row['event']!='probe_step':continue
            state=row['state'];self.assertEqual(state['enabled_mask'],1023)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(prior,state['pulse_us'])),8);prior=state['pulse_us']
        for i,target in enumerate(d.targets):
            self.assertEqual(target[:6],[a+b for a,b in zip(duet.BASE[:6],duet.c.PROFILES[duet.PERSON][i])])
            self.assertEqual(target[6:],[1500+b for b in duet.c.PROFILES[duet.TIGER][min(i,5)]])
        self.assertEqual(d.pulses,duet.BASE);self.assertEqual(self.lock.read_text(),'incident')

    def test_changed_component_hash_and_current_sequence_reject_before_arm(self):
        self.plan['expected_sequence']+=1
        with self.assertRaises(ValueError):self.device()
        self.plan['expected_sequence']-=1
        path=self.plan['tiger_completed_log']['path'];self.logs[path]+=b' '
        with self.assertRaises(ValueError):self.device()

    def test_missing_intervening_frame_rejects_combined_motion(self):
        broken=copy.deepcopy(self.person)
        broken.pop(next(i for i,r in enumerate(broken) if r['event']=='probe_step'))
        self.plan['tiger_intervening_logs']=[self.spec('broken',broken)]
        with self.assertRaises(ValueError):self.device()

if __name__=='__main__':unittest.main()
