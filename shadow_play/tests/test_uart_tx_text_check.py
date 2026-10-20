from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'integrations/calibration'),str(Path(__file__).resolve().parents[1]/'tools')]
from uart_tx_text_check import TextPort,TEXT,COUNT,PORTS,validate_image,IMAGE_SHA,main
from zdt_uartlite_telemetry import PORTS as REVIEWED_PORTS


class Fake:
    def __init__(self,status=4,drain=True):self.now=0.;self.status=status;self.writes=[];self.drain=drain
    def read(self,offset):
        if offset!=8:raise AssertionError('RX or control register accessed')
        return self.status if not self.writes or self.drain else 0
    def write(self,offset,value):
        if offset!=4:raise AssertionError('Non TX write')
        self.writes.append((offset,value))
    def clock(self):return self.now
    def sleep(self,t):self.now+=t


class Tests(unittest.TestCase):
    def port(self,f,name='person'):return TextPort(f,name,clock=f.clock,sleep=f.sleep)

    def test_exact_finite_text_and_only_tx_register(self):
        self.assertEqual(PORTS,REVIEWED_PORTS)
        for name,line in TEXT.items():
            f=Fake();p=self.port(f,name)
            for _ in range(COUNT):p.send_line()
            self.assertEqual(bytes(v for a,v in f.writes),line*COUNT)
            self.assertTrue(all(a==4 for a,v in f.writes))
            with self.assertRaises(RuntimeError):p.send_line()
            self.assertFalse(p.diagnostics[-1]['wire_received_verified'])

    def test_busy_or_interrupt_client_sends_nothing(self):
        for status in (0,8,12,0x14,0x100):
            f=Fake(status);p=self.port(f)
            with self.assertRaises(RuntimeError):p.send_line()
            self.assertEqual(f.writes,[])

    def test_unconnected_rx_flags_do_not_invalidate_transmit_only(self):
        for status in (5,0x44,0xE7):
            f=Fake(status);p=self.port(f);row=p.send_line()
            self.assertTrue(row['tx_fifo_drained']);self.assertEqual(row['rx_flags_before'],status&0xE3)
            self.assertFalse(row['wire_received_verified'])

    def test_partial_or_timeout_not_retried(self):
        f=Fake(drain=False);p=self.port(f)
        with self.assertRaises(TimeoutError):p.send_line()
        self.assertEqual(len(f.writes),len(TEXT['person']))
        with self.assertRaises(RuntimeError):p.send_line()
        class Partial(Fake):
            def write(self,a,v):
                if len(self.writes)==3:raise OSError('interrupted')
                super().write(a,v)
        f=Partial();p=self.port(f)
        with self.assertRaises(OSError):p.send_line()
        with self.assertRaises(RuntimeError):p.send_line()
        self.assertEqual(len(f.writes),3)

    def test_missing_isolation_rejected_before_hardware_import(self):
        for flags in ([],['--ttl-3v3-confirmed'],['--motor-rx-disconnected-confirmed']):
            with patch.object(sys,'argv',['text','--execute-text']+flags),self.assertRaisesRegex(RuntimeError,'disconnection'):
                main()

    def test_old_or_swapped_image_is_rejected(self):
        m=dict(boot_id='boot',sha256=IMAGE_SHA,design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS',
            rail_uart=dict(design_checks='RAIL_UART_DESIGN_CHECKS_PASS',ports=PORTS,baud=115200,format='8N1'))
        validate_image(m,'boot')
        for name,value in [('sha256','old'),('boot_id','another')]:
            bad=dict(m);bad[name]=value
            with self.assertRaises(RuntimeError):validate_image(bad,'boot')


if __name__=='__main__':unittest.main()
