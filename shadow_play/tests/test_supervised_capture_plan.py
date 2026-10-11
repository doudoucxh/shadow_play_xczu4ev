import argparse
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from supervised_capture_plan import HostLease, run_plan, validate_plan
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from capture_supervised_plan import DEFAULT_BOARD_SCRIPT, validate_board_script

class FakeDevice:
    def __init__(self):
        self.state = dict(identity='SP10', clock_hz=100000000, period_us=20000,
                          armed=False, enabled_mask=0, pending=False, faults=0,
                          pulse_us=[1500]*10)
        self.commits = []; self.off_count = 0; self.kicks = 0
        self.commit_error = False; self.watchdog = False

    def status(self): return copy.deepcopy(self.state)

    def commit(self, pulses, mask, allow_arm=False):
        self.commits.append((pulses[:], mask, allow_arm))
        self.state.update(armed=True, enabled_mask=mask, pulse_us=pulses[:])
        if self.commit_error: raise TimeoutError('uncertain commit')
        return self.status()

    def kick(self):
        self.kicks += 1
        if self.watchdog: self.state.update(armed=False, enabled_mask=0, faults=2)

    def off(self):
        self.off_count += 1
        self.state.update(armed=False, enabled_mask=0, pending=False)
        return self.status()

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
        p=plan();p['local_bounds_us']['0']=[1500,1537];variants.append(p)
        p=plan();p['steps'][1]['label']='first';variants.append(p)
        p=plan();p['steps'][0]['hold_seconds']=float('nan');variants.append(p)
        for p in variants:
            with self.assertRaises(ValueError):validate_plan(p)
    def test_tiger_pairs_preserve_other_commands_and_use_correct_bits(self):
        for first,second in [(7,8),(9,10)]:
            with self.subTest(pair=(first,second)):
                p=plan()
                p['local_bounds_us']={str(first):[1500,1537],str(second):[1500,1537]}
                for step,ch in zip(p['steps'],[first,second,second]):step['channel']=ch
                d=Device();events=[];self.run_fast(d,p,events.append)
                self.assertEqual(d.commits[0][1:],(1 << (first-1),True))
                self.assertEqual(d.commits[1][1:],((1 << (first-1)) | (1 << (second-1)),False))
                prior=[1500]*10
                for pulses,mask,arm in d.commits:
                    changed=[i for i in range(10) if pulses[i]!=prior[i]]
                    self.assertTrue(all(i==second-1 for i in changed))
                    self.assertTrue(all(abs(pulses[i]-prior[i])<=4 for i in changed))
                    self.assertEqual(pulses[:6],[1500]*6)
                    prior=pulses
                self.assertEqual(d.off_count,1)
                self.assertEqual(events[-1]['state']['enabled_mask'],0)
    def test_reject_out_of_range_or_noncanonical_channel_keys(self):
        for key in ['0','11','01','1.0',10]:
            with self.subTest(key=key):
                p=plan();p['local_bounds_us'][key]=[1500,1537]
                with self.assertRaises(ValueError):validate_plan(p)
        for ch in [0,11]:
            p=plan();p['steps'][0]['channel']=ch
            with self.assertRaises(ValueError):validate_plan(p)
    def test_tiger_first_enable_cannot_replace_current_command(self):
        for ch in [7,8,9,10]:
            p=plan();p['local_bounds_us']={str(ch):[1496,1537]}
            p['steps']=[dict(label='estimated_start',channel=ch,pulse_us=1496,hold_seconds=1)]
            d=Device()
            with self.assertRaisesRegex(ValueError,'First enable'):self.run_fast(d,p)
            self.assertEqual(d.commits,[])
    def test_tiger_existing_motion_bounds_remain_enforced(self):
        p=plan();p['local_bounds_us']={'10':[1500,1538]}
        p['steps']=[dict(label='start',channel=10,pulse_us=1500,hold_seconds=1),
                    dict(label='too_far',channel=10,pulse_us=1538,hold_seconds=1)]
        with self.assertRaisesRegex(ValueError,'37 us'):validate_plan(p)
        p['steps'][1]['pulse_us']=1537;p['local_bounds_us']['10']=[1500,1613]
        with self.assertRaisesRegex(ValueError,'112 us'):validate_plan(p)
        p['local_bounds_us']['10']=[1500,1537]
        p['steps']=[dict(label=str(i),channel=10,pulse_us=1500,hold_seconds=5) for i in range(13)]
        with self.assertRaisesRegex(ValueError,'60-second'):validate_plan(p)
    def test_board_script_path_validation(self):
        self.assertEqual(validate_board_script(DEFAULT_BOARD_SCRIPT),DEFAULT_BOARD_SCRIPT)
        self.assertEqual(validate_board_script('/tmp/supervised_capture_plan_20261011_v3.py'),
                         '/tmp/supervised_capture_plan_20261011_v3.py')
        for path in ['/tmp/test.py;reboot','/tmp/test.py\nreboot','/tmp/$(reboot).py',
                     '/tmp/test.py --execute','/tmp/../test.py','/tmp/sub/test.py',
                     '/etc/test.py','test.py','/tmp/test.json','/tmp/test.py\r']:
            with self.subTest(path=path),self.assertRaises(argparse.ArgumentTypeError):
                validate_board_script(path)
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
