"""Check the bounded single-reference runner without serial or MMIO hardware."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import center_one_servo as runner


class Port:
    is_open=False
    def __init__(self,**kwargs): pass
    def open(self): self.is_open=True
    def close(self): self.is_open=False


class Link:
    failed=False
    reject=False
    wrong_mask=False
    calls=[]
    def __init__(self,port,log): self.port=port
    def exchange(self,operation,payload):
        self.calls.append((operation,payload))
        if operation=='initialize' and self.reject: return {'ok':False,'error':'unverified reference'}
        active=operation=='initialize'
        state={'enabled_mask':(3 if self.wrong_mask else 1) if active else 0,
               'pulse_us':[1500]*10,'armed':active,'faults':0,'pending':False}
        return {'ok':True,'result':state}
    def close(self):
        self.calls.append(('close_off',{})); self.port.close()


class CenterTests(unittest.TestCase):
    def setUp(self):
        Link.calls=[];Link.reject=False;Link.wrong_mask=False;Link.failed=False

    def run_action(self,interrupt=False):
        with tempfile.TemporaryDirectory() as temp:
            argv=['center_one_servo.py','--channel','1','--hold-seconds','1',
                  '--unloaded-and-observer-ready','--log',str(Path(temp)/'action.jsonl')]
            with patch.object(sys,'argv',argv),patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=Port)}),\
                 patch.object(runner,'SerialLink',Link),contextlib.redirect_stdout(io.StringIO()):
                if interrupt:
                    with patch.object(runner.time,'sleep',side_effect=KeyboardInterrupt): runner.main()
                else: runner.main()

    def test_one_reference_then_off(self):
        self.run_action()
        self.assertEqual(Link.calls,[('initialize',{'channel':1}),('off',{}),('close_off',{})])

    def test_rejection_never_retries(self):
        Link.reject=True
        with self.assertRaisesRegex(RuntimeError,'unverified reference'): self.run_action()
        self.assertEqual(Link.calls,[('initialize',{'channel':1}),('close_off',{})])

    def test_unexpected_mask_stops_immediately(self):
        Link.wrong_mask=True
        with self.assertRaisesRegex(RuntimeError,'Unexpected adopted state'): self.run_action()
        self.assertEqual(Link.calls,[('initialize',{'channel':1}),('close_off',{})])

    def test_keyboard_interrupt_still_closes_outputs(self):
        with self.assertRaises(KeyboardInterrupt): self.run_action(interrupt=True)
        self.assertEqual(Link.calls,[('initialize',{'channel':1}),('close_off',{})])


if __name__=='__main__': unittest.main()
