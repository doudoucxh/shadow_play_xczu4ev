import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from test_story_audio_session import Device, Audio
import story_audio_session_v3 as a
import story_motion_v3_candidate as s


def fixtures():
    state=dict(pulse_us=s.START[:],sequence=32296,enabled_mask=0,armed=False,faults=0,pending=False)
    rows=[dict(event='reference_held',profile=a.trial.PROFILE,route_sha256=a.trial.ROUTE_SHA)]
    rows += [dict(event='interaction_phrase_complete',index=i) for i in range(4)]
    rows += [dict(event='interaction_complete'),dict(event='outputs_off',normal_frame_stop=True,state=state)]
    plan=dict(approval='attended-fixed-puppet-choreography-20261012',session_id='story-v3-test',
        profile=a.PROFILE,story_mode='full',story_route_sha256=a.ROUTE_SHA,
        expected_sequence=32296,expected_pulses_us=s.START[:],observer_ready=True,
        operator_hardware_unmoved=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=100000,
        duration_seconds=120,boot_id='7eea2c53-e104-45cf-88fe-439f1821e5d4',baseline_source={})
    return plan,rows


class TrackedDevice(Device):
    def __init__(self,failure=None):
        super().__init__('full');self.pulses=s.START[:];self.commands=[];self.failure=failure
    def adopt(self,p):
        if self.commands:
            assert self.t-self.last_start>=.02-1e-9
            assert max(abs(x-y) for x,y in zip(p,self.pulses))<=24
        result=super().adopt(p);self.commands.append((self.t,p[:]));return result
    def wait(self,n,sleep):
        self.t+=max(n,.000001)
        if self.t>.8:
            if self.failure=='stall':self.t+=.1;self.failure=None
            elif self.failure=='lease':raise RuntimeError('camera lease lost')
            elif self.failure=='stop':raise RuntimeError('operator stop')
            elif self.failure=='repeat':self.host.action=('demo',self.sequence)
        self.check()


class Tests(unittest.TestCase):
    def test_exact_bo_lineage_and_review(self):
        p,rows=fixtures();a.validate(p,rows,wall=lambda:101)
        for name,value in [('expected_sequence',32295),('story_route_sha256','x'),
                           ('observer_ready',False),('story_mode','fight'),
                           ('reviewed_at_unix_ms',0)]:
            q=copy.deepcopy(p);q[name]=value
            with self.assertRaises(ValueError):a.validate(q,rows,wall=lambda:150)
        for change in ('incomplete','bad_stop','wrong_lineage'):
            rr=copy.deepcopy(rows)
            if change=='incomplete':rr.pop(2)
            if change=='bad_stop':rr[-1]['normal_frame_stop']=False
            if change=='wrong_lineage':rr[0]['profile']='story-audio-v2'
            with self.assertRaises(ValueError):a.validate(p,rr)

    def test_full_candidate_stops_and_never_certifies_effect(self):
        d=TrackedDevice();audio=Audio('full');events=[];a.run(d,events.append,audio)
        self.assertTrue(d.normal and d.stopped and audio.closed)
        self.assertEqual(d.pulses,s.START)
        done=next(e for e in events if e['event']=='story_complete')
        self.assertFalse(done['actual_stage_effect_verified'])
        self.assertTrue(done['candidate_trial'])
        self.assertTrue(all(e.get('incident_locks_removed',False) is False for e in events))
        self.assertEqual(len([e for e in events if e['event']=='timeline_checkpoint']),
                         len(set([0,s.DURATION]+[t for tr in (s.HUMAN,s.TIGER) for t,_,_ in tr])))

    def test_stall_lease_stop_repeat_have_no_return(self):
        for mode in ('stall','lease','stop','repeat'):
            with self.subTest(mode=mode):
                d=TrackedDevice(mode);audio=Audio('full');events=[]
                with self.assertRaises(RuntimeError):a.run(d,events.append,audio)
                self.assertTrue(d.stopped and audio.closed);self.assertFalse(d.normal)
                self.assertNotIn('story_complete',[e['event'] for e in events])
                self.assertEqual(events[-1]['state']['pulse_us'],d.commands[-1][1])

    def test_audio_failure_stops_in_place(self):
        d=TrackedDevice();audio=Audio('full',True);events=[]
        with self.assertRaisesRegex(RuntimeError,'speaker lost'):a.run(d,events.append,audio)
        self.assertTrue(d.stopped and audio.closed);self.assertFalse(d.normal)
        self.assertEqual(d.pulses,d.commands[-1][1])


if __name__=='__main__':unittest.main()
