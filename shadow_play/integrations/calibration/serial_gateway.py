#!/usr/bin/env python3
"""Windows COM-to-TCP bridge; requires an already running servo_console.py.

Does not type shell commands/passwords or initialize outputs. One lock serializes
capture, commissioning and watchdog heartbeat. A timeout permanently closes the
link; there is no automatic reconnect, retry, or automatic rearm.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socketserver
import threading
import time
import uuid
from tcp_bridge import parse_json

PREFIX = b'@@SP10@@'


class SerialLink:
    def __init__(self, port, log):
        self.port = port
        self.log = log
        self.lock = threading.Lock()
        self.failed = False
        self.closed = threading.Event()
        hello = self.exchange('hello', {})
        state = hello.get('result', {})
        if (hello.get('ok') is not True or state.get('identity') != 'SP10' or
                state.get('clock_hz') != 100000000 or state.get('period_us') != 20000 or
                state.get('armed') is not False or state.get('enabled_mask') != 0):
            self.failed = True
            raise RuntimeError('Expected SP10 hardware with all outputs off; inspect board before starting bridge')
        self.worker = threading.Thread(target=self._heartbeat, daemon=True)
        self.worker.start()

    def exchange(self, operation, payload):
        with self.lock:
            if self.failed:
                raise RuntimeError('Serial link failed; restart service and inspect board state before motion')
            request = {'transport_id': uuid.uuid4().hex, 'operation': operation, 'payload': payload}
            wire = json.dumps(request, allow_nan=False, separators=(',', ':')).encode('utf-8') + b'\n'
            if len(wire) > 4096:
                raise ValueError('Console frame too large')
            self.log.write(json.dumps({'logged_at': datetime.now(timezone.utc).isoformat(),
                                       'sent': request})+'\n'); self.log.flush()
            try:
                self.port.write(wire)
                deadline = time.monotonic()+1.5
                while time.monotonic() < deadline:
                    line = self.port.readline(8193)
                    if len(line) > 8192:
                        raise ValueError('Oversized console response')
                    start = line.find(PREFIX)
                    if start < 0:
                        continue  # boot/kernel messages cannot act as acknowledgements
                    reply = parse_json(line[start+len(PREFIX):].decode('utf-8'))
                    if reply.get('transport_id') != request['transport_id']:
                        continue
                    self.log.write(json.dumps({'logged_at': datetime.now(timezone.utc).isoformat(),
                                               'received': reply})+'\n'); self.log.flush()
                    if type(reply.get('ok')) is not bool:
                        raise ValueError('Invalid console response')
                    if not reply['ok']:
                        return reply
                    return reply
                raise TimeoutError('Serial ACK unknown; no retry, heartbeat stopped')
            except Exception:
                self.failed = True
                raise

    def _heartbeat(self):
        while not self.closed.wait(.35):
            try:
                ack = self.exchange('heartbeat', {})
                if not ack['ok']:
                    self.failed = True
                    return
            except Exception:
                return

    def close(self):
        self.closed.set()
        self.worker.join(timeout=2)
        if not self.failed:
            try:
                self.exchange('off', {})
            except Exception:
                pass
        self.port.close()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(3)
        try:
            line = self.rfile.readline(4097)
            if len(line) > 4096 or not line.endswith(b'\n'):
                raise ValueError('Invalid client frame')
            request = parse_json(line.decode('utf-8'))
            if isinstance(request, dict) and request.get('type') in ('capture_sync', 'capture_target'):
                ack = self.server.link.exchange('capture', request)
                if not ack['ok']:
                    raise RuntimeError(ack.get('error', 'Console rejected request'))
                result = ack['result']
            else:
                if not isinstance(request, dict) or set(request) != {'operation', 'payload'}:
                    raise ValueError('Invalid maintenance request')
                if request['operation'] not in ('status', 'off', 'initialize', 'jog'):
                    raise ValueError('Unknown maintenance operation')
                result = self.server.link.exchange(request['operation'], request['payload'])
            self.wfile.write((json.dumps(result, allow_nan=False)+'\n').encode('utf-8'))
        except Exception as error:
            self.wfile.write((json.dumps({'error': str(error)})+'\n').encode('utf-8'))


def main():
    import serial
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM13')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--tcp-port', type=int, default=7000)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    port = serial.Serial(port=None, baudrate=115200, timeout=.15, write_timeout=.5)
    port.dtr = False; port.rts = False; port.port = args.port
    port.open()
    with args.log.open('x', encoding='utf-8') as log:
        link = SerialLink(port, log)
        try:
            with socketserver.TCPServer((args.bind, args.tcp_port), Handler) as server:
                server.link = link
                print('SERIAL GATEWAY READY; outputs are not automatically enabled', flush=True)
                server.serve_forever()
        finally:
            link.close()


if __name__ == '__main__':
    main()
