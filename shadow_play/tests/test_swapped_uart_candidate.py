import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_rail_query_candidate import candidate
from load_swapped_uart_candidate import STANDARD_SHA, verify_swapped
from load_rail_query_candidate import verify_candidate
from zdt_uartlite_telemetry import PORTS, SWAPPED_PORTS, TelemetryError, main, validate_pin_map


def swapped():
    m = candidate()
    m['previous_sha256'] = STANDARD_SHA
    m['rail_uart'].update(ports=copy.deepcopy(SWAPPED_PORTS),pin_map='swapped',tx_drive_ma=4,
                         swapped_design_checks='RAIL_UART_SWAPPED_DESIGN_CHECKS_PASS')
    return m


class Tests(unittest.TestCase):
    def test_standard_and_swapped_maps_cannot_be_confused(self):
        self.assertEqual(validate_pin_map(candidate()['rail_uart'],'standard'),PORTS)
        self.assertEqual(validate_pin_map(swapped()['rail_uart'],'swapped'),SWAPPED_PORTS)
        with self.assertRaises(TelemetryError):
            validate_pin_map(candidate()['rail_uart'],'swapped')
        with self.assertRaises(TelemetryError):
            validate_pin_map(swapped()['rail_uart'],'standard')
        with self.assertRaises(ValueError):
            verify_candidate(swapped(),'1'*64)

    def test_swapped_candidate_requires_separate_checks_and_lowest_strength(self):
        verify_swapped(swapped(),'1'*64)
        for field, value in [('tx_drive_ma',8),('pin_map','standard'),('swapped_design_checks','pending')]:
            m=swapped();m['rail_uart'][field]=value
            with self.assertRaises((ValueError,TelemetryError)):
                verify_swapped(m,'1'*64)
        m=swapped();m['previous_sha256']='2'*64
        with self.assertRaises(ValueError):
            verify_swapped(m,'1'*64)

    def test_swapped_query_scope_rejected_before_hardware_import(self):
        for kind,address in [('status',1),('position',1),('version',2)]:
            args=['query','--rail','person','--pin-map','swapped','--address',str(address),
                  '--query',kind,'--checksum-mode','fixed_6b','--firmware-kind','Emm',
                  '--boot-id','offline','--image-sha','1'*64,'--expected-sequence','0','--execute-query']
            with patch.object(sys,'argv',args),self.assertRaisesRegex(TelemetryError,'limited to one address-1'):
                main()


if __name__ == '__main__':
    unittest.main()
