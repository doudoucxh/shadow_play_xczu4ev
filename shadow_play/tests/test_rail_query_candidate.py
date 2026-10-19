import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from load_rail_query_candidate import BASE_SHA, PINS, PORTS, verify_candidate


def candidate():
    return dict(sha256='1'*64, image_kind='servo10_vision',
        design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS', bus_skew_check='SERVO_BUS_SKEW_CHECK_PASS',
        register_base=0xA0030000, pins=PINS[:], clock_hz=100000000, period_us=20000,
        channels=10, reset_outputs='disabled', part='xczu4ev-sfvc784-2-i',
        wns_ns=.2, whs_ns=.01, wpws_ns=.1,
        rail_uart=dict(design_checks='RAIL_UART_DESIGN_CHECKS_PASS', ports=copy.deepcopy(PORTS),
                       baud=115200, format='8N1'))


class Tests(unittest.TestCase):
    def test_reviewed_distinct_candidate(self):
        verify_candidate(candidate(), '1'*64)
        with self.assertRaises(ValueError):
            verify_candidate(candidate(), '2'*64)
        m = candidate()
        m['sha256'] = BASE_SHA
        with self.assertRaises(ValueError):
            verify_candidate(m, BASE_SHA)

    def test_preserve_servo_pins_clock_part_and_disabled_reset(self):
        for field, value in [('pins', ['H13']*10), ('part', 'other'), ('reset_outputs', 'enabled'),
                             ('clock_hz', 50000000), ('period_us', 10000), ('register_base', 0)]:
            m = candidate()
            m[field] = value
            with self.assertRaises(ValueError):
                verify_candidate(m, '1'*64)

    def test_failed_timing_or_design_checks_reject(self):
        for field in ('wns_ns', 'whs_ns', 'wpws_ns'):
            m = candidate()
            m[field] = -.001
            with self.assertRaises(ValueError):
                verify_candidate(m, '1'*64)
        m = candidate()
        m['design_checks'] = 'pending'
        with self.assertRaises(ValueError):
            verify_candidate(m, '1'*64)

    def test_uart_wiring_or_serial_settings_mismatch_reject(self):
        for field, value in [('baud', 9600), ('format', '8E1'), ('design_checks', 'pending')]:
            m = candidate()
            m['rail_uart'][field] = value
            with self.assertRaises(ValueError):
                verify_candidate(m, '1'*64)
        m = candidate()
        m['rail_uart']['ports']['person']['tx_pin'] = 'H13'
        with self.assertRaises(ValueError):
            verify_candidate(m, '1'*64)


if __name__ == '__main__':
    unittest.main()
