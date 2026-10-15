import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
import person_recovery_session as r

class ProtocolTests(unittest.TestCase):
    def deliver(self,host,line):
        with patch.object(r.select,'select',return_value=([99],[],[])),patch.object(r.os,'read',return_value=line):host.check()
    def test_opening_eight_stages(self):
        for action in ('probe_7','review_7','probe_8','review_8'):
            h=r.HostControl(99,max_stage=8)
            self.deliver(h,(': # PERSON_RECOVERY_ACTION '+action+' 42797\n').encode())
            self.assertEqual(h.action,(action,42797))
    def test_default_scope_still_six(self):
        with self.assertRaises(RuntimeError):self.deliver(r.HostControl(99),b': # PERSON_RECOVERY_ACTION probe_7 1\n')
    def test_unknown_and_concurrent_rejected(self):
        for line in (b': # PERSON_RECOVERY_ACTION probe_9 1\n',
                     b': # PERSON_RECOVERY_ACTION probe_7 1\n: # PERSON_RECOVERY_ACTION probe_8 1\n'):
            with self.assertRaises(RuntimeError):self.deliver(r.HostControl(99,max_stage=8),line)
    def test_invalid_scope(self):
        for count in (0,9,True):
            with self.assertRaises(ValueError):r.HostControl(99,max_stage=count)
if __name__=='__main__':unittest.main()
