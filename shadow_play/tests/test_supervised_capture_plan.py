import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from supervised_capture_plan import HostLease, run_plan, validate_plan
from test_supervised_servo_trial import FakeDevice

class Device(FakeDevice):
    def __init__(self):
        super().__init__(); self.state['sequence'] = 14
    def commit(self, pulses, mask, allow_arm=False):
        super().commit(pulses, mask, allow_arm)
        self.state['sequence'] += 1
        return self.status()

def plan():
    return dict(observer_present=True, estimated_start_authorized=True,
        expected_sequence=14, expected_pulses_us=[1500]*10,
        local_bounds_us={'1':[1500,1537],'2':[1500,1537]}, steps=[
            dict(label='first',channel=1,pulse_us=1500,hold_seconds=1),
            dict(label='second',channel=2,pulse_us=1500,hold_seconds=1),
            dict(label='move',channel=2,pulse_us=1537,hold_seconds=1)])

class Tests(unittest.TestCase):
    def run_fast(self, d, p, emit=lambda row:None):
        now=[0.0]
        return run_plan(d,p,emit,clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
    def test_gradual_one_axis_steps_and_final_off(self):
        d=Device(); events=[]; self.run_fast(d,plan(),events.append)
        self.assertEqual(d.commits[0][1:],(1,True))
        self.assertEqual(d.commits[1][1:],(3,False))
        prior=[1500]*10
        for pulses,mask,arm in d.commits:
            changed=[i for i in range(10) if pulses[i]!=prior[i]]
            self.assertLessEqual(len(changed),1)
            self.assertTrue(all(abs(pulses[i]-prior[i])<=4 for i in changed))
            self.assertEqual(pulses[6:],[1500]*4);prior=pulses
        self.assertEqual(d.off_count,1)
        self.assertEqual(events[-1]['event'],'outputs_off')
    def test_reject_stale_state_before_writes(self):
        for key,value in [('sequence',15),('faults',1),('armed',True)]:
            d=Device();d.state[key]=value
            with self.assertRaises(RuntimeError):self.run_fast(d,plan())
            self.assertEqual(d.commits,[])
    def test_reject_invalid_plans(self):
        variants=[]
        p=plan();p['observer_present']=False;variants.append(p)
        p=plan();p['steps'][0]['pulse_us']=1501;variants.append(p)
        p=plan();p['steps'][2]['pulse_us']=1600;variants.append(p)
        p=plan();p['local_bounds_us']['7']=[1500,1537];variants.append(p)
        p=plan();p['steps'][1]['label']='first';variants.append(p)
        p=plan();p['steps'][0]['hold_seconds']=float('nan');variants.append(p)
        for p in variants:
            with self.assertRaises(ValueError):validate_plan(p)
    def test_commit_failure_and_watchdog_never_rearm(self):
        d=Device();d.commit_error=True
        with self.assertRaises(TimeoutError):self.run_fast(d,plan())
        self.assertEqual(len(d.commits),1);self.assertEqual(d.off_count,1)
        d=Device();d.watchdog=True
        with self.assertRaises(RuntimeError):self.run_fast(d,plan())
        self.assertEqual(len(d.commits),1);self.assertEqual(d.off_count,1)
    def test_observer_error_turns_off(self):
        d=Device()
        def emit(row):
            if row['event']=='sample_begin':raise RuntimeError('host observer failed')
        with self.assertRaises(RuntimeError):self.run_fast(d,plan(),emit)
        self.assertEqual(d.off_count,1)
    def test_host_lease_expiry_turns_off_without_retry(self):
        d=Device();now=[0.0]
        def lease():
            if now[0]>.3:raise RuntimeError('host disconnected')
        with self.assertRaises(RuntimeError):
            run_plan(d,plan(),lambda row:None,clock=lambda:now[0],
                     sleep=lambda s:now.__setitem__(0,now[0]+s),lease_check=lease)
        self.assertEqual(len(d.commits),1);self.assertEqual(d.off_count,1)
    def test_lease_partial_input_does_not_refresh_deadline(self):
        now=[0.0];lease=HostLease(9,clock=lambda:now[0])
        with patch('supervised_capture_plan.select.select',return_value=([9],[],[])), \
                patch('supervised_capture_plan.os.read',return_value=b': # CAPTURE_'):
            now[0]=1.6
            with self.assertRaises(RuntimeError):lease.check()
    def test_lease_complete_token_refreshes_deadline(self):
        now=[0.0];lease=HostLease(9,clock=lambda:now[0])
        with patch('supervised_capture_plan.select.select',return_value=([9],[],[])), \
                patch('supervised_capture_plan.os.read',return_value=b': # CAPTURE_LEASE\n'):
            now[0]=1.4;lease.check()
        with patch('supervised_capture_plan.select.select',return_value=([],[],[])):
            now[0]=2.0;lease.check()
            now[0]=3.0
            with self.assertRaises(RuntimeError):lease.check()

if __name__=='__main__':unittest.main()
