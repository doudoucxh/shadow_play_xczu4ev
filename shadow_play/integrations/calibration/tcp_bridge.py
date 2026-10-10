#!/usr/bin/env python3
"""Forward one capture session to a board JSON-line service (no motor driver)."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

MAX_BYTES = 1024 * 1024


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def forward(request, host, port, timeout):
    payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    if len(payload) > MAX_BYTES:
        raise ValueError("request exceeds 1 MiB")
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(max(0.001, deadline - time.monotonic()))
        connection.sendall(payload)
        response = bytearray()
        while b"\n" not in response:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("board ACK timeout")
            connection.settimeout(remaining)
            chunk = connection.recv(4096)
            if not chunk:
                raise ConnectionError("board closed without a newline ACK")
            response.extend(chunk)
            if len(response) > MAX_BYTES:
                raise ValueError("board response exceeds 1 MiB")
    line, extra = bytes(response).split(b"\n", 1)
    if extra.strip():
        raise ValueError("expected exactly one ACK")
    ack = parse_json(line.decode("utf-8"))
    if not isinstance(ack, dict):
        raise ValueError("ACK must be an object")
    for key in ("version", "session_id", "seq"):
        if type(ack.get(key)) is not type(request[key]) or ack[key] != request[key]:
            raise ValueError("ACK mismatched " + key)
    if ack.get("type") != "capture_ack" or type(ack.get("accepted")) is not bool:
        raise ValueError("invalid capture ACK")
    # The C++ session validates adopted axes, slides, units, limits and faults.
    return ack


def validate_request(request, session_id, filename):
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if type(request.get("version")) is not int or request["version"] not in (1, 2):
        raise ValueError("invalid protocol version")
    if request.get("session_id") != session_id:
        raise ValueError("request session differs from directory")
    if type(request.get("seq")) is not int or request["seq"] <= 0:
        raise ValueError("invalid sequence")
    if filename != "request_{:06d}.json".format(request["seq"]):
        raise ValueError("request filename differs from sequence")
    if request.get("type") not in ("capture_sync", "capture_target"):
        raise ValueError("unknown request type")
    if not isinstance(request.get("axes"), list) or not request["axes"]:
        raise ValueError("missing axes")
    if request["version"] == 2 and not isinstance(request.get("slides"), list):
        raise ValueError("version 2 requires slides")


def write_ack(path, ack):
    # GUI sees only a fully written file; never replace a prior response.
    if path.exists():
        raise FileExistsError(str(path))
    temporary = path.with_suffix(".tmp.{}".format(os.getpid()))
    data = json.dumps(ack, ensure_ascii=False, allow_nan=False) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise FileExistsError(str(path))
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def run(session_dir, host, port, timeout):
    requests = session_dir / "requests"
    acks = session_dir / "acks"
    if not requests.is_dir() or not acks.is_dir():
        raise ValueError("start the external GUI first; use its exchange/session_id directory")
    seen = {path.name for path in requests.glob("request_*.json")}
    synchronized = False
    print("Bridge ready for {}. Existing requests ignored; click GUI sync now.".format(
        session_dir.name), flush=True)
    while True:
        for path in sorted(requests.glob("request_*.json")):
            if path.name in seen:
                continue
            seen.add(path.name)  # Never retry a command with uncertain execution.
            if path.stat().st_size > MAX_BYTES:
                print("Rejected oversized request: " + path.name, file=sys.stderr, flush=True)
                synchronized = False
                continue
            request = None
            try:
                request = parse_json(path.read_text(encoding="utf-8"))
                validate_request(request, session_dir.name, path.name)
                if request["type"] == "capture_target" and not synchronized:
                    raise ValueError("bridge requires a fresh read-only capture_sync first")
                ack_path = acks / "ack_{:06d}.json".format(request["seq"])
                if ack_path.exists():
                    raise ValueError("ACK already exists; command will not be replayed")
                ack = forward(request, host, port, timeout)
                if request["type"] == "capture_sync":
                    synchronized = ack["accepted"] and ack.get("fault") in (None, False)
                elif not ack["accepted"] or ack.get("fault") not in (None, False):
                    synchronized = False
                write_ack(ack_path, ack)
                print("seq {}: ACK accepted={}".format(request["seq"], ack["accepted"]), flush=True)
            except Exception as error:
                synchronized = False
                print("Request {} failed: {}. No automatic retry.".format(path.name, error),
                      file=sys.stderr, flush=True)
                if isinstance(request, dict):
                    try:
                        validate_request(request, session_dir.name, path.name)
                        ack = {"version": request["version"], "type": "capture_ack",
                               "session_id": request["session_id"], "seq": request["seq"],
                               "accepted": False, "adopted": [], "feedback": None,
                               "slides": [], "fault": "PC bridge: " + str(error)}
                        write_ack(acks / "ack_{:06d}.json".format(request["seq"]), ack)
                    except Exception:
                        pass  # GUI will time out and require a new sync.
        time.sleep(0.04)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", required=True, type=Path,
                        help="GUI exchange/<session_id> directory")
    parser.add_argument("--host", required=True, help="board IP or hostname")
    parser.add_argument("--port", type=int, default=7000, help="board service port, default 7000")
    parser.add_argument("--timeout", type=float, default=4.0, help="less than GUI ACK timeout")
    args = parser.parse_args()
    if not (1 <= args.port <= 65535) or not (0 < args.timeout <= 60):
        parser.error("invalid port or timeout")
    try:
        run(args.session_dir.resolve(), args.host, args.port, args.timeout)
    except KeyboardInterrupt:
        print("Bridge stopped; this is not a hardware emergency stop.", flush=True)
    except Exception as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
