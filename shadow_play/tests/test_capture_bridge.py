"""Exercise the PC file/TCP bridge against a local, hardware-free board service."""

import importlib.util
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "integrations" / "calibration" / "tcp_bridge.py"
SPEC = importlib.util.spec_from_file_location("capture_tcp_bridge", BRIDGE_PATH)
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


def request(session_id="test-session", seq=1, kind="capture_sync"):
    return {
        "version": 2,
        "type": kind,
        "session_id": session_id,
        "seq": seq,
        "axes": [{"axis_id": "neck_x", "value": 0.1, "unit": "demo"}],
        "slides": [
            {"id": "wusong_slide", "value": 0.1, "unit": "demo", "state_kind": "commanded", "controllable": True},
            {"id": "tiger_slide", "value": -0.1, "unit": "demo", "state_kind": "commanded", "controllable": True},
        ],
    }


def ack_for(command):
    return {
        "version": command["version"],
        "type": "capture_ack",
        "session_id": command["session_id"],
        "seq": command["seq"],
        "accepted": True,
        "adopted": command["axes"],
        "feedback": None,
        "slides": command.get("slides", []),
        "fault": None,
    }


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n"


class MockBoard:
    """Single-connection JSON-line service with an explicit release event."""

    def __init__(self, handler=None):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.listener.settimeout(0.05)
        self.host, self.port = self.listener.getsockname()
        self.release = threading.Event()
        self.stopping = threading.Event()
        self.received = queue.Queue()
        self.errors = queue.Queue()
        self.commands = []
        self.lock = threading.Lock()
        self.handler = handler or (lambda command, connection, board: connection.sendall(encoded(ack_for(command))))
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        while not self.stopping.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self.stopping.is_set():
                    self.errors.put("mock listener unexpectedly closed")
                return
            with connection:
                try:
                    connection.settimeout(1)
                    wire = bytearray()
                    while b"\n" not in wire:
                        chunk = connection.recv(4096)
                        if not chunk:
                            raise RuntimeError("bridge sent an incomplete request")
                        wire.extend(chunk)
                    command = json.loads(bytes(wire).split(b"\n", 1)[0])
                    with self.lock:
                        self.commands.append(command)
                    self.received.put(command)
                    self.handler(command, connection, self)
                except Exception as error:
                    if not self.stopping.is_set():
                        self.errors.put(error)

    def sequence_numbers(self):
        with self.lock:
            return [command["seq"] for command in self.commands]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stopping.set()
        self.release.set()
        self.listener.close()
        self.thread.join(2)
        if self.thread.is_alive():
            raise AssertionError("mock board did not stop")
        if not self.errors.empty():
            raise AssertionError("mock board error: " + str(self.errors.get_nowait()))


class BridgeProcess:
    def __init__(self, session, board, timeout=0.2):
        self.lines = queue.Queue()
        self.history = []
        self.process = subprocess.Popen(
            [sys.executable, "-u", str(BRIDGE_PATH), "--session-dir", str(session),
             "--host", board.host, "--port", str(board.port), "--timeout", str(timeout)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        self.readers = []
        for channel, stream in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            thread = threading.Thread(target=self._read, args=(channel, stream), daemon=True)
            thread.start()
            self.readers.append(thread)
        self.wait_line(lambda channel, line: channel == "stdout" and "Bridge ready" in line)

    def _read(self, channel, stream):
        for line in stream:
            self.lines.put((channel, line.rstrip()))
        self.lines.put((channel, None))

    def wait_line(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("bridge event timeout; output=" + repr(self.history))
            try:
                channel, line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise AssertionError("bridge event timeout; output=" + repr(self.history)) from error
            if line is None:
                if self.process.poll() is not None:
                    raise AssertionError("bridge exited unexpectedly; output=" + repr(self.history))
                continue
            self.history.append((channel, line))
            if predicate(channel, line):
                return line

    def success(self, seq):
        return self.wait_line(lambda channel, line: channel == "stdout" and line == "seq {}: ACK accepted=True".format(seq))

    def failure(self, seq):
        return self.wait_line(lambda channel, line: channel == "stderr" and
                              "Request request_{:06d}.json failed:".format(seq) in line)

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for thread in self.readers:
            thread.join(1)
        self.process.stdout.close()
        self.process.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()


def session_directory(root):
    session = Path(root) / "test-session"
    (session / "requests").mkdir(parents=True)
    (session / "acks").mkdir()
    return session


def write_request(session, seq, kind, replace=False):
    final = session / "requests" / "request_{:06d}.json".format(seq)
    temporary = final.with_suffix(".test-tmp")
    if not replace and final.exists():
        raise FileExistsError(str(final))
    temporary.write_bytes(encoded(request(session.name, seq, kind)))
    os.replace(temporary, final)


def read_ack(session, seq):
    data = (session / "acks" / "ack_{:06d}.json".format(seq)).read_bytes()
    if not data.endswith(b"\n"):
        raise AssertionError("ACK became visible without its final newline")
    return json.loads(data)


class ForwardTests(unittest.TestCase):
    def test_identity_and_complete_group_survive_short_tcp_reads(self):
        def fragment(command, connection, _):
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            for byte in encoded(ack_for(command)):
                connection.sendall(bytes([byte]))

        command = request()
        with MockBoard(fragment) as board:
            actual = BRIDGE.forward(command, board.host, board.port, 1)
            self.assertEqual(actual, ack_for(command))
            self.assertEqual(board.received.get(timeout=1), command)
            self.assertEqual(board.sequence_numbers(), [1])

    def test_rejects_mismatched_identity_sequence_version_and_types(self):
        mutations = {
            "session": lambda ack: ack.update(session_id="different-session"),
            "sequence": lambda ack: ack.update(seq=2),
            "boolean sequence": lambda ack: ack.update(seq=True),
            "version": lambda ack: ack.update(version=1),
            "ACK type": lambda ack: ack.update(type="capture_target"),
            "accepted type": lambda ack: ack.update(accepted="true"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                def reply(command, connection, _, mutation=mutate):
                    ack = ack_for(command)
                    mutation(ack)
                    connection.sendall(encoded(ack))
                with MockBoard(reply) as board:
                    with self.assertRaises(ValueError):
                        BRIDGE.forward(request(), board.host, board.port, 1)
                    self.assertEqual(board.sequence_numbers(), [1])

    def test_rejects_duplicate_json_nonobject_and_extra_ack(self):
        replies = {
            "duplicate key": lambda command: b'{"seq":1,' + encoded(ack_for(command))[1:],
            "nonobject": lambda command: b"[]\n",
            "multiple ACKs": lambda command: encoded(ack_for(command)) * 2,
        }
        for label, build in replies.items():
            with self.subTest(label=label):
                with MockBoard(lambda command, connection, _, factory=build:
                               connection.sendall(factory(command))) as board:
                    with self.assertRaises(ValueError):
                        BRIDGE.forward(request(), board.host, board.port, 1)

    def test_ack_without_newline_is_rejected(self):
        with MockBoard(lambda command, connection, _: connection.sendall(encoded(ack_for(command))[:-1])) as board:
            with self.assertRaises(ConnectionError):
                BRIDGE.forward(request(), board.host, board.port, 1)
            self.assertEqual(board.sequence_numbers(), [1])

    def test_timeout_is_bounded_and_does_not_reconnect(self):
        with MockBoard(lambda command, connection, board: board.release.wait(2)) as board:
            started = time.monotonic()
            with self.assertRaises((TimeoutError, socket.timeout)):
                BRIDGE.forward(request(), board.host, board.port, 0.1)
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(board.sequence_numbers(), [1])

    def test_atomic_ack_refuses_existing_file_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as root:
            final = Path(root) / "ack_000001.json"
            ack = ack_for(request())
            BRIDGE.write_ack(final, ack)
            data = final.read_bytes()
            self.assertTrue(data.endswith(b"\n"))
            self.assertEqual(json.loads(data), ack)
            with self.assertRaises(FileExistsError):
                BRIDGE.write_ack(final, dict(ack, accepted=False))
            self.assertEqual(final.read_bytes(), data)
            self.assertEqual(list(Path(root).glob("*.tmp.*")), [])
            invalid = Path(root) / "ack_000002.json"
            with self.assertRaises(ValueError):
                BRIDGE.write_ack(invalid, dict(ack, value=float("nan")))
            self.assertFalse(invalid.exists())


class ProcessTests(unittest.TestCase):
    def test_old_requests_ignored_and_targets_need_fresh_sync(self):
        with tempfile.TemporaryDirectory() as root, MockBoard() as board:
            session = session_directory(root)
            write_request(session, 1, "capture_sync")
            write_request(session, 2, "capture_target")
            with BridgeProcess(session, board) as process:
                write_request(session, 3, "capture_target")
                self.assertIn("fresh read-only capture_sync", process.failure(3))
                write_request(session, 4, "capture_sync")
                process.success(4)
                self.assertFalse(read_ack(session, 3)["accepted"])
                self.assertEqual(board.sequence_numbers(), [4])
                self.assertFalse((session / "acks" / "ack_000001.json").exists())
                self.assertFalse((session / "acks" / "ack_000002.json").exists())
                write_request(session, 5, "capture_target")
                process.success(5)
                self.assertEqual(read_ack(session, 5), ack_for(request(session.name, 5, "capture_target")))
                # Replacing a consumed filename must not repeat a possibly executed command.
                write_request(session, 5, "capture_target", replace=True)
                write_request(session, 6, "capture_sync")
                process.success(6)
                self.assertEqual(board.sequence_numbers(), [4, 5, 6])
                self.assertEqual(list((session / "acks").glob("*.tmp.*")), [])

    def test_timeout_writes_fault_never_retries_and_requires_resync(self):
        def reply(command, connection, board):
            if command["seq"] == 2:
                board.release.wait(2)
            else:
                connection.sendall(encoded(ack_for(command)))

        with tempfile.TemporaryDirectory() as root, MockBoard(reply) as board:
            session = session_directory(root)
            with BridgeProcess(session, board, timeout=0.1) as process:
                write_request(session, 1, "capture_sync")
                process.success(1)
                write_request(session, 2, "capture_target")
                self.assertIn("No automatic retry", process.failure(2))
                write_request(session, 2, "capture_target", replace=True)
                write_request(session, 3, "capture_target")
                self.assertIn("fresh read-only capture_sync", process.failure(3))
                board.release.set()
                write_request(session, 4, "capture_sync")
                process.success(4)
                self.assertEqual(board.sequence_numbers(), [1, 2, 4])
                failure = read_ack(session, 2)
                self.assertFalse(failure["accepted"])
                self.assertIn("PC bridge:", failure["fault"])
                self.assertEqual(failure["adopted"], [])
                self.assertIsNone(failure["feedback"])

    def test_restart_does_not_replay_target_sent_without_ack(self):
        def reply(command, connection, board):
            if command["seq"] == 2:
                board.release.wait(3)
            else:
                connection.sendall(encoded(ack_for(command)))

        with tempfile.TemporaryDirectory() as root, MockBoard(reply) as board:
            session = session_directory(root)
            process = BridgeProcess(session, board, timeout=1)
            try:
                write_request(session, 1, "capture_sync")
                process.success(1)
                self.assertEqual(board.received.get(timeout=1)["seq"], 1)
                write_request(session, 2, "capture_target")
                self.assertEqual(board.received.get(timeout=1)["seq"], 2)
            finally:
                process.stop()
            self.assertFalse((session / "acks" / "ack_000002.json").exists())
            with BridgeProcess(session, board, timeout=0.2) as restarted:
                write_request(session, 3, "capture_target")
                self.assertIn("fresh read-only capture_sync", restarted.failure(3))
                board.release.set()
                write_request(session, 4, "capture_sync")
                restarted.success(4)
                self.assertEqual(board.sequence_numbers(), [1, 2, 4])
                self.assertFalse((session / "acks" / "ack_000002.json").exists())


if __name__ == "__main__":
    unittest.main()
