"""One read-only ID2 version query through the official USB servo adapter."""
import argparse
import json
from pathlib import Path
import time

from .protocol import parse_reply

REQUEST = b'#002PVER!'


def query_version(port, clock=time.monotonic):
    """Never discard pending data, retry a request, or send a control command."""
    if port.in_waiting:
        raise RuntimeError('Adapter has pending data; inspect it before querying')
    if port.write(REQUEST) != len(REQUEST):
        raise RuntimeError('Partial write; no retry')
    port.flush()
    deadline = clock() + .6
    reply = bytearray()
    last_byte = None
    while clock() < deadline:
        data = port.read(256)
        if data:
            reply.extend(data)
            last_byte = clock()
            if len(reply) > 2048:
                raise RuntimeError('Oversized adapter reply')
        if b'!' in reply and last_byte is not None and clock() - last_byte >= .02:
            return {'version': parse_reply(bytes(reply), 2, 'version'), 'rx_hex': reply.hex()}
    raise TimeoutError('ID2 version query timed out; no retry; received=' + reply.hex())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--port')
    parser.add_argument('--expected-hwid')
    parser.add_argument('--id2-isolated-from-fpga', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'execute': False, 'id': 2, 'tx_ascii': REQUEST.decode(),
                          'baud': 115200, 'queries': 1, 'motion_commands': 0}))
        return
    if (not args.port or args.port.upper() == 'COM17' or not args.expected_hwid
            or not args.id2_isolated_from_fpga or args.output is None):
        parser.error('Require the separate adapter port/HWID, isolated ID2, and a new output file; COM17 is the PS console')
    import serial
    from serial.tools import list_ports
    matches = [p for p in list_ports.comports() if p.device.upper() == args.port.upper()]
    if len(matches) != 1 or matches[0].hwid != args.expected_hwid or matches[0].vid is None:
        raise RuntimeError('USB adapter identity changed; no port opened')
    record = {'port': args.port, 'hwid': args.expected_hwid, 'id': 2,
              'tx_hex': REQUEST.hex(), 'motion_commands': 0, 'retries': 0}
    # Exclusive creation makes the invocation single-use even if interrupted.
    with args.output.open('x', encoding='utf-8') as log:
        def save(row):
            log.write(json.dumps(row, ensure_ascii=False) + '\n'); log.flush()
        save({'starting': record})
        port = serial.Serial(port=None, baudrate=115200, timeout=.02, write_timeout=.3)
        port.dtr = port.rts = False
        port.port = args.port
        try:
            port.open()
            result = query_version(port)
            record.update(result)
        except Exception as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            port.close()
            record['port_released'] = not port.is_open
            save({'final': record})
            print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
