import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_demo_once as demo
from test_servo_commissioning import FakeRegisters


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lock=self.root/'incident';self.lock.write_text('preserved')
        self.reg=FakeRegisters();self.now=0.;self.events=[]
        for i,v in enumerate(demo.REFERENCE):self.reg.values[0x80+4*i]=v
        self.plan=dict(approval=demo.APPROVAL,expected_sequence=0,expected_pulses_us=demo.REFERENCE[:],
                      reference_session='unit-test',observer_ready=True,views_reviewed=True,mechanism_unchanged=True)

    def device(self,lease=lambda:None):
        return demo.DemoDevice(self.reg,self.plan,lease_check=lease,motion_inhibit_paths=[self.lock],
                               cancel_path=self.root/'cancel',clock=lambda:self.now)
    def sleep(self,dt):self.now+=dt

    def test_paths_stay_on_tested_single_axis_intervals(self):
        rows=demo.trajectory();self.assertEqual(len(rows),561)
        bounds=[(0,24),(-24,0),(0,24),(0,48),(0,24),(0,24)]+[(0,0)]*4
        for (_,old),(_,new) in zip(rows,rows[1:]):
            self.assertLessEqual(max(abs(a-b) for a,b in zip(old,new)),1)
            self.assertLessEqual(sum(v!=b for v,b in zip(new,demo.REFERENCE)),1)
            for value,base,(lo,hi) in zip(new,demo.REFERENCE,bounds):self.assertTrue(lo<=value-base<=hi)
        self.assertEqual(rows[-1][1],demo.REFERENCE)

    def test_complete_and_frame_stop_keep_locks_and_tiger_off(self):
        demo.run_once(self.device(),self.events.append,clock=lambda:self.now,sleep=self.sleep)
        states=[e['state'] for e in self.events if e['event']=='demo_step']
        self.assertEqual(len(states),561);self.assertTrue(all(s['enabled_mask']==63 for s in states))
        self.assertEqual(self.events[-1]['state']['sequence'],562)
        self.assertFalse(self.events[-1]['state']['armed']);self.assertAlmostEqual(self.now,71.)
        self.assertEqual(self.lock.read_text(),'preserved')

    def test_camera_lease_loss_stops_without_return(self):
        def lease():
            if self.now>2.:raise demo.VideoLeaseUnavailable('lost camera')
        with self.assertRaises(demo.VideoLeaseUnavailable):demo.run_once(self.device(lease),self.events.append,clock=lambda:self.now,sleep=self.sleep)
        self.assertTrue(self.events[-1]['normal_frame_stop']);self.assertFalse(self.events[-1]['state']['armed'])
        last=self.events[-2]['state']
        self.assertNotEqual(last['pulse_us'],demo.REFERENCE)
        self.assertEqual(self.events[-1]['state']['pulse_us'],last['pulse_us'])
        self.assertEqual(self.events[-1]['state']['sequence'],last['sequence']+1)
        self.assertEqual(self.lock.read_text(),'preserved')
        self.assertLess(self.events[-1]['state']['sequence'],20)

    def test_operator_interrupt_stops_immediately_without_disable_commit(self):
        def lease():
            if self.now>.8:raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            demo.run_once(self.device(lease),self.events.append,clock=lambda:self.now,sleep=self.sleep)
        self.assertFalse(self.events[-1]['normal_frame_stop'])
        self.assertFalse(self.events[-1]['state']['armed'])
        self.assertEqual(self.events[-1]['state']['sequence'],self.events[-2]['state']['sequence'])

    def test_hardware_fault_takes_priority_over_video_loss(self):
        def sleep(dt):
            self.now+=dt
            if self.now>.8:self.reg.values[0x0c]=1
        def lease():
            if self.now>.8:raise demo.VideoLeaseUnavailable('lost camera')
        with self.assertRaisesRegex(RuntimeError,'Demo state changed'):
            demo.run_once(self.device(lease),self.events.append,clock=lambda:self.now,sleep=sleep)
        self.assertFalse(self.events[-1]['normal_frame_stop'])
        self.assertEqual(self.events[-1]['state']['sequence'],self.events[-2]['state']['sequence'])
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_cancel_takes_priority_over_video_loss(self):
        def sleep(dt):
            self.now+=dt
            if self.now>.8:(self.root/'cancel').touch()
        def lease():
            if self.now>.8:raise demo.VideoLeaseUnavailable('lost camera')
        with self.assertRaisesRegex(RuntimeError,'Demo cancelled'):
            demo.run_once(self.device(lease),self.events.append,clock=lambda:self.now,sleep=sleep)
        self.assertFalse(self.events[-1]['normal_frame_stop'])
        self.assertFalse(self.events[-1]['state']['armed'])

    def test_frame_drain_fault_falls_back_to_off_without_rearm(self):
        def lease():
            if self.now>.8:raise demo.VideoLeaseUnavailable('lost camera')
        original=self.reg.write
        def write(address,value):
            original(address,value)
            if address==0x18 and self.reg.read(0x14)==0:self.reg.values[0x0c]=1
        with patch.object(self.reg,'write',side_effect=write):
            with self.assertRaisesRegex(RuntimeError,'stopped unexpectedly'):
                demo.run_once(self.device(lease),self.events.append,clock=lambda:self.now,sleep=self.sleep)
        self.assertEqual(self.reg.read(8),0);self.assertEqual(self.reg.read(0x10),0)
        self.assertEqual(sum(address==0x10 for address,_ in self.reg.writes),1)
        self.assertEqual(self.lock.read_text(),'preserved')

    def test_stale_sequence_does_not_arm(self):
        self.plan['expected_sequence']=1
        with self.assertRaises(RuntimeError):demo.run_once(self.device(),self.events.append,clock=lambda:self.now,sleep=self.sleep)
        self.assertFalse(any(a==0x10 for a,v in self.reg.writes))

    def test_wrong_next_step_and_rate_rejected(self):
        d=self.device();d.commit(demo.REFERENCE,63,True)
        with self.assertRaises(RuntimeError):d.commit(d.path[1][1],63)
        self.sleep(.125);wrong=demo.REFERENCE[:];wrong[7]+=1
        with self.assertRaises(RuntimeError):d.commit(wrong,63)

    def test_invalid_plan_scope(self):
        for k,v in [('mechanism_unchanged',False),('approval','other'),('expected_sequence',True),('reference_session','')]:
            p=copy.deepcopy(self.plan);p[k]=v
            with self.assertRaises(ValueError):demo.validate_plan(p)
        p=copy.deepcopy(self.plan);p['expected_pulses_us'][0]+=1
        with self.assertRaises(ValueError):demo.validate_plan(p)

    def test_host_lease_requires_exact_line_and_expires(self):
        lease=demo.HostLease(99,clock=lambda:self.now)
        with patch.object(demo.select,'select',return_value=([99],[],[])),patch.object(demo.os,'read',return_value=b': # PERSON_DEMO_LEASE\n'):
            lease.check()
        self.assertTrue(lease.received);self.now=1.6
        with patch.object(demo.select,'select',return_value=([],[],[])):
            with self.assertRaises(demo.VideoLeaseUnavailable):lease.check()
        lease=demo.HostLease(99,clock=lambda:self.now)
        with patch.object(demo.select,'select',return_value=([99],[],[])),patch.object(demo.os,'read',return_value=b'wrong\n'):
            with self.assertRaises(RuntimeError):lease.check()

    def test_host_video_stop_and_closed_input_are_frame_stop_requests(self):
        for data in (b': # PERSON_DEMO_VIDEO_STOP\n',b''):
            lease=demo.HostLease(99,clock=lambda:self.now)
            with patch.object(demo.select,'select',return_value=([99],[],[])),patch.object(demo.os,'read',return_value=data):
                with self.assertRaises(demo.VideoLeaseUnavailable):lease.check()
        lease=demo.HostLease(99,clock=lambda:self.now)
        with patch.object(demo.select,'select',return_value=([99],[],[])),patch.object(demo.os,'read',return_value=b': # PERSON_DEMO_VIDEO_STOP_WRONG\n'):
            with self.assertRaises(RuntimeError) as raised:lease.check()
        self.assertNotIsInstance(raised.exception,demo.VideoLeaseUnavailable)

    def test_uncertain_adoption_has_no_retry(self):
        self.reg.apply=False;d=self.device()
        with self.assertRaises(TimeoutError):demo.run_once(d,self.events.append,clock=lambda:self.now,sleep=self.sleep)
        with self.assertRaises(RuntimeError):d.commit(demo.REFERENCE,63,True)
        self.assertEqual(sum(a==0x18 for a,v in self.reg.writes),1)
        self.assertFalse(self.events[-1]['state']['armed'])


if __name__=='__main__':unittest.main()
