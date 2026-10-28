"""Offline contract checks; these tests never open a serial port."""
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.adapter_probe import REQUEST, main, query_version
from shadow_play.bus_servo.protocol import ProtocolError


class Port:
    def __init__(self, reply=b'', pending=0, partial=False):
        self.reply=reply;self.in_waiting=pending;self.partial=partial
        self.writes=[];self.now=0.0
    def write(self, data):
        self.writes.append(data)
        return len(data)-1 if self.partial else len(data)
    def flush(self): pass
    def read(self, size):
        self.now+=.03
        result=self.reply;self.reply=b''
        return result


class AdapterProbeTests(unittest.TestCase):
    def test_success_is_one_addressed_version_query(self):
        p=Port(b'#002PSERVO.C(7.3)!')
        self.assertEqual(query_version(p,lambda:p.now)['version'],'SERVO.C(7.3)')
        self.assertEqual(p.writes,[REQUEST])

    def test_timeout_does_not_retry(self):
        p=Port()
        with self.assertRaises(TimeoutError):query_version(p,lambda:p.now)
        self.assertEqual(p.writes,[REQUEST])

    def test_stale_data_prevents_transmission(self):
        p=Port(pending=1)
        with self.assertRaises(RuntimeError):query_version(p,lambda:p.now)
        self.assertEqual(p.writes,[])

    def test_wrong_id_and_echo_are_not_accepted(self):
        for reply in (b'#001PSERVO.C(7.3)!',REQUEST,b'#002PSERVO.C(7.3)!#002PSERVO.C(7.3)!'):
            p=Port(reply)
            with self.assertRaises(ProtocolError):query_version(p,lambda:p.now)
            self.assertEqual(p.writes,[REQUEST])

    def test_partial_write_does_not_retry(self):
        p=Port(partial=True)
        with self.assertRaises(RuntimeError):query_version(p,lambda:p.now)
        self.assertEqual(p.writes,[REQUEST])

    def test_preview_and_missing_execute_guards_do_not_import_serial(self):
        with patch('builtins.print') as output:
            main([])
            self.assertIn('"execute": false',output.call_args.args[0])
        with patch('sys.stderr'):
            with self.assertRaises(SystemExit):main(['--execute'])
            with self.assertRaises(SystemExit):
                main(['--execute','--port','COM17','--expected-hwid','known',
                      '--id2-isolated-from-fpga','--output','unused.jsonl'])


if __name__=='__main__':unittest.main()
