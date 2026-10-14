import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
m=importlib.import_module('tiger_height_trial')


class Fake:
    def __init__(self,levels,fail=False):
        self.sequence=1;self.pulses=m.START[:];self.visited=[];self.fail=fail
        self.actions=['demo']*levels+['finish'];self.host=SimpleNamespace(action=None)
        self.normal=False;self.stopped=False
    def check(self):return dict(sequence=self.sequence,pulse_us=self.pulses[:])
    def adopt(self,p):self.pulses=p[:];self.sequence+=1;self.queue();return self.check()
    def queue(self):
        if self.actions:self.host.action=(self.actions.pop(0),self.sequence)
    def advance(self,i,emit,sleep):
        if self.fail:raise RuntimeError('camera lease expired')
        self.pulses=self.targets[i][:];self.sequence+=1;self.visited.append(self.pulses[:]);self.queue()
    def wait(self,*args):raise AssertionError('Unexpected idle in fake')
    def off(self):self.stopped=True;return self.check()
    def stop_after_frame(self):self.normal=True;return self.off()


class Tests(unittest.TestCase):
    def test_partial_trial_reverses_only_visited_levels(self):
        d=Fake(2);ev=[];m.run(d,ev.append)
        self.assertEqual(d.visited,[m.TARGETS[1],m.TARGETS[2],m.TARGETS[1],m.TARGETS[0]])
        self.assertTrue(d.normal and d.stopped)
        self.assertEqual(next(e for e in ev if e['event']=='height_trial_complete')['highest_stage'],2)
    def test_failure_stops_without_returning(self):
        d=Fake(2,True)
        with self.assertRaisesRegex(RuntimeError,'camera lease'):m.run(d,lambda e:None)
        self.assertTrue(d.stopped);self.assertFalse(d.normal);self.assertEqual(d.visited,[])
    def test_vertical_trial_does_not_change_human_or_yaw(self):
        for p in m.TARGETS:
            self.assertEqual(p[:7],m.START[:7]);self.assertEqual(p[8],m.START[8])
            self.assertTrue(500+100*2000/270<=p[7]<=500+190*2000/270)
            self.assertTrue(500+50*2000/270<=p[9]<=500+170*2000/270)
    def test_unknown_or_stale_reference_is_rejected(self):
        p=dict(approval='attended-fixed-puppet-choreography-20261012',session_id='test',profile=m.PROFILE,
               route_sha256=m.ROUTE_SHA,expected_sequence=10,expected_pulses_us=m.START[:],observer_ready=True,
               operator_hardware_unmoved=True,dual_view_pose_reviewed=True,reviewed_at_unix_ms=100000,
               duration_seconds=300,boot_id='7eea2c53-e104-45cf-88fe-439f1821e5d4',baseline_source={})
        rows=[dict(event='reference_held',profile='story-audio-v1',route_sha256=m.AW_ROUTE_SHA),
              dict(event='story_complete',full_show_executed=True),dict(event='outputs_off',normal_frame_stop=True,
              state=dict(pulse_us=m.START[:],sequence=10,enabled_mask=0,armed=False,faults=0,pending=False))]
        m.validate(p,rows,lambda:100)
        with self.assertRaisesRegex(ValueError,'expired'):m.validate(p,rows,lambda:221)
        rows[-1]['state']['pulse_us'][7]+=1
        with self.assertRaisesRegex(ValueError,'reference'):m.validate(p,rows,lambda:100)


if __name__=='__main__':unittest.main()
