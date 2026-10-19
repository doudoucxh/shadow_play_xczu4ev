"""Connection-time handoff may exit known idle debug services, never move or steal active output."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from servo_center_session import await_prompt,clean_idle_debug_state


def state(**changes):
    value=dict(service='attended-angle-v1',identity='SP10',period_us=20000,
        clock_hz=100000000,armed=False,enabled_mask=0,pending=False,faults=0,
        sequence=8120,pulse_us=[1500]*10,manual_diagnostics_available=True)
    value.update(changes);return value


class Port:
    def __init__(self,value,root=True):
        self.inbox=[b'@@SP10@@'+json.dumps(dict(ready=True,state=value)).encode()+b'\r\n']
        self.writes=[];self.root=root
    def read(self,size):return self.inbox.pop(0) if self.inbox else b''
    def write(self,data):
        self.writes.append(data)
        if self.root:self.inbox.extend([b'\r\n',b'root@shadowdpupetalinux:~# '])


class Tests(unittest.TestCase):
    def test_only_known_clean_idle_debug_service_is_exited(self):
        p=Port(state())
        self.assertEqual(await_prompt(p,service='attended-initial-pose-v1',allow_idle_switch=True),'root')
        self.assertEqual(p.writes,[b'\x03\r'])
    def test_default_readonly_probes_do_not_switch_services(self):
        p=Port(state())
        with self.assertRaises(RuntimeError):await_prompt(p,service='attended-initial-pose-v1')
        self.assertEqual(p.writes,[])
    def test_active_fault_unknown_or_incomplete_state_never_gets_interrupt(self):
        for changes in ({'armed':True,'enabled_mask':1},{'pending':True},{'faults':1},
                        {'service':'unknown'},{'identity':'other'},{'sequence':True},
                        {'pulse_us':[1500]*9},{'pulse_us':[True]*10},{'enabled_mask':False},
                        {'output_lost':True},{'manual_diagnostics_available':False}):
            p=Port(state(**changes))
            with self.assertRaises(RuntimeError):await_prompt(p,service='attended-initial-pose-v1',allow_idle_switch=True)
            self.assertEqual(p.writes,[])
    def test_same_service_is_reused_without_interrupt(self):
        p=Port(state())
        self.assertEqual(await_prompt(p,service='attended-angle-v1',allow_idle_switch=True),'service')
        self.assertEqual(p.writes,[])
    def test_exit_must_reach_root_before_any_start_is_permitted(self):
        p=Port(state(),root=False)
        with patch('servo_center_session.time.monotonic',side_effect=[0,0,0,0,10]):
            with self.assertRaises(RuntimeError):await_prompt(p,service='attended-initial-pose-v1',allow_idle_switch=True)
        self.assertEqual(p.writes,[b'\x03\r'])
    def test_reverse_handoff_and_lost_output_are_distinct(self):
        value=state(service='attended-initial-pose-v1',output_lost=False)
        self.assertTrue(clean_idle_debug_state(value))
        p=Port(value)
        self.assertEqual(await_prompt(p,service='attended-angle-v1',allow_idle_switch=True),'root')


if __name__=='__main__':unittest.main()
