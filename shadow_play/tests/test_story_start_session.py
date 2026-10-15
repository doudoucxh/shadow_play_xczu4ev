import io
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from story_start_session import StoryStartSession, BoardRejected, PREFIX, SERVICE


class Port:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []

    def write(self, wire):
        self.sent.append(json.loads(wire))

    def readline(self, limit):
        row = self.reply(self.sent[-1])
        if isinstance(row, bytes): return row
        return PREFIX+json.dumps(row).encode()+b'\n'


class SessionTests(unittest.TestCase):
    def session(self, reply):
        s = StoryStartSession.__new__(StoryStartSession)
        s.lock = threading.Lock(); s.closed = threading.Event()
        s.failed = False; s.log = io.StringIO(); s.port = Port(reply)
        return s

    def test_read_and_explicit_stop_only_send_requested_operation(self):
        s = self.session(lambda req: dict(transport_id=req['transport_id'], ok=True,
                                          result=dict(service=SERVICE, ready=False)))
        s.status(); s.stop()
        self.assertEqual([r['operation'] for r in s.port.sent], ['status','off'])

    def test_board_rejection_never_falls_back_to_force(self):
        s = self.session(lambda req: dict(transport_id=req['transport_id'], ok=False,
                                          error='OFF state'))
        with self.assertRaises(BoardRejected): s.start()
        self.assertEqual(len(s.port.sent), 1)
        self.assertFalse(s.failed)  # Connection remains usable for an explicit OFF.

    def test_bad_json_kills_heartbeat_and_no_retry(self):
        s = self.session(lambda req: PREFIX+b'{bad json\n')
        with self.assertRaises(ValueError): s.start()
        self.assertTrue(s.failed)
        self.assertTrue(s.closed.is_set())
        with self.assertRaises(RuntimeError): s.start()
        self.assertEqual(len(s.port.sent), 1)

    def test_unreviewed_plan_is_not_uploaded(self):
        s = self.session(lambda req: b'')
        with self.assertRaises(ValueError): s.load_plan({})
        self.assertEqual(s.port.sent, [])


if __name__ == '__main__': unittest.main()
