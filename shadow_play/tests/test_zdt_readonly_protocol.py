from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from zdt_readonly_protocol import ProtocolError,query,decode


class Tests(unittest.TestCase):
    def q(self,address=1,kind='version',**kw):return query(address,kind,checksum_mode=kw.get('checksum_mode','fixed_6b'))
    def d(self,kind,reply,firmware_kind=None):return decode(1,kind,bytes.fromhex(reply),checksum_mode='fixed_6b',firmware_kind=firmware_kind)

    def test_only_three_read_commands_and_no_broadcast_or_guessing(self):
        self.assertEqual(self.q(),bytes.fromhex('01 1f 6b'))
        self.assertEqual(self.q(2,'status'),bytes.fromhex('02 3a 6b'))
        self.assertEqual(self.q(255,'position'),bytes.fromhex('ff 36 6b'))
        for address in [0,256,-1,True,1.0,None]:
            with self.assertRaises(ProtocolError):self.q(address)
        for kind in ['enable','move','home','reset','stop','scan']:
            with self.assertRaises(ProtocolError):self.q(kind=kind)
        with self.assertRaises(ProtocolError):self.q(checksum_mode='unknown')

    def test_version_never_infers_firmware_kind(self):
        r=self.d('version','01 1f 00 c8 03 0e 6b')
        self.assertEqual(r['firmware_version_raw'],200)
        self.assertEqual(r['hardware_type'],3)
        self.assertIsNone(r['firmware_kind']);self.assertFalse(r['freshness_verified'])

    def test_position_units_differ_and_never_become_rail_zero_or_mm(self):
        emm=self.d('position','01 36 00 00 01 00 00 6b','Emm')
        x=self.d('position','01 36 00 00 01 00 00 6b','X')
        self.assertEqual(emm['position_degrees'],360)
        self.assertEqual(x['position_degrees'],6553.6)
        self.assertIsNone(emm['position_mm']);self.assertFalse(emm['rail_zero_verified'])
        with self.assertRaises(ProtocolError):self.d('position','01 36 00 00 01 00 00 6b')

    def test_sign_and_internal_6b_are_data_not_frame_terminators(self):
        r=self.d('position','01 36 01 00 00 6b 00 6b','Emm')
        self.assertEqual(r['position_raw_signed'],-27392)
        with self.assertRaises(ProtocolError):self.d('position','01 36 02 00 00 00 00 6b','Emm')

    def test_status_limit_levels_are_not_assumed_trigger_polarities(self):
        r=self.d('status','01 3a 83 6b')
        self.assertTrue(r['enabled']);self.assertTrue(r['target_reached']);self.assertTrue(r['power_cycle_flag'])
        self.assertFalse(r['stall_protection']);self.assertIsNone(r['limit_trigger_polarity'])
        with self.assertRaises(ProtocolError):self.d('status','01 3a e2 6b')

    def test_identity_length_checksum_and_old_version_frames_reject(self):
        for raw in ['02 3a 83 6b','01 36 83 6b','01 3a 83 00','01 3a 83 6b 00']:
            with self.assertRaises(ProtocolError):self.d('status',raw)
        with self.assertRaises(ProtocolError):self.d('version','01 1f 32 05 6b')


if __name__=='__main__':unittest.main()
