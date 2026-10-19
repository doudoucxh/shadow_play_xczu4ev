from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_zdt_uartlite_telemetry import Fake
from uart_person_loopback_check import LoopbackPort,main
from zdt_readonly_protocol import ProtocolError
from zdt_uartlite_telemetry import QueryPort,TelemetryError


class Tests(unittest.TestCase):
    def test_exact_echo_is_only_a_local_loop_not_a_motor_handshake(self):
        f=Fake(reply=bytes.fromhex('011f6b'))
        p=LoopbackPort(f,clock=f.clock,sleep=f.sleep)
        r=p.request(1,'version',checksum_mode='fixed_6b',firmware_kind='Emm')
        self.assertTrue(r['local_loopback_echo_verified'])
        self.assertTrue(r['freshness_verified'])
        self.assertFalse(r['motor_handshake_verified'])
        self.assertEqual(f.writes,[(4,1),(4,0x1f),(4,0x6b)])

    def test_real_version_reply_and_corrupt_echo_do_not_pass_as_loopback(self):
        for raw in ('011f006410016b','021f6b','011f6b00'):
            f=Fake(reply=bytes.fromhex(raw));p=LoopbackPort(f,clock=f.clock,sleep=f.sleep)
            with self.assertRaises(TelemetryError):
                p.request(1,'version',checksum_mode='fixed_6b',firmware_kind='Emm')
        f=Fake(reply=bytes.fromhex('011f6b'));p=QueryPort(f,clock=f.clock,sleep=f.sleep)
        with self.assertRaises(ProtocolError):
            p.request(1,'version',checksum_mode='fixed_6b',firmware_kind='Emm')

    def test_missing_operator_setup_rejects_before_device_import(self):
        for flags in ([],['--actuators-off-confirmed'],
                      ['--actuators-off-confirmed','--f15-h13-linked-confirmed']):
            args=['loopback','--boot-id','offline','--expected-sequence','0','--execute-check']+flags
            with patch.object(sys,'argv',args),self.assertRaisesRegex(TelemetryError,'confirmations required'):
                main()


if __name__=='__main__':unittest.main()
