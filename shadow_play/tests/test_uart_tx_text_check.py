from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'integrations/calibration'),str(Path(__file__).resolve().parents[1]/'tools')]
from uart_tx_text_check import TextPort,TEXT,COUNT,PORTS,validate_image,IMAGE_SHA,main,run_continuous
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

    def test_repeat_exceeds_five_with_bounded_diagnostics_and_no_retry(self):
        f=Fake();p=TextPort(f,'person',repeat=True,clock=f.clock,sleep=f.sleep)
        for _ in range(40):p.send_line()
        self.assertEqual(p.lines,40);self.assertEqual(len(p.diagnostics),32)
        self.assertEqual(bytes(v for a,v in f.writes),TEXT['person']*40)
        f.drain=False
        with self.assertRaises(RuntimeError):p.send_line()
        count=len(f.writes)
        with self.assertRaises(RuntimeError):p.send_line()
        self.assertEqual(len(f.writes),count)

    def test_continuous_stop_cadence_and_state_change(self):
        from unittest.mock import Mock
        f=Fake()
        class Stop:
            stopped=False
            def is_set(self):return self.stopped
            def wait(self,t):f.sleep(t)
        stop=Stop();starts=[];ports={'person':Mock(),'tiger':Mock()}
        def report(active):
            starts.append(f.clock())
            if len(starts)==7:stop.stopped=True
        run_continuous(ports,lambda:None,stop,report,clock=f.clock)
        self.assertEqual(ports['person'].send_line.call_count,7)
        self.assertTrue(all(b-a>=1-1e-8 for a,b in zip(starts,starts[1:])))
        stop=Stop();ports={'person':Mock(),'tiger':Mock()}
        def changed():raise RuntimeError('PWM changed')
        with self.assertRaises(RuntimeError):run_continuous(ports,changed,stop,report,clock=f.clock)
        ports['person'].send_line.assert_not_called()

    def test_stop_between_ports_does_not_send_second_port(self):
        from unittest.mock import Mock
        stop=Mock();stop.is_set.side_effect=[False,False,True]
        ports={'person':Mock(),'tiger':Mock()}
        run_continuous(ports,lambda:None,stop,Mock())
        ports['person'].send_line.assert_called_once();ports['tiger'].send_line.assert_not_called()


if __name__=='__main__':unittest.main()
