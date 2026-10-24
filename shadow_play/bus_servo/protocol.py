"""Servo.C ASCII protocol, per the supplied manual (pages 3–8).

ASCII positions deliberately stay in 500..2500 coordinates. Binary position
direction/scaling is different and must never be substituted for PRAD feedback.
"""
import re


class ProtocolError(RuntimeError):
    pass


def health_request(ident):
    integer(ident, 0, 253, 'Servo ID')
    fields = bytes([ident, 4, 2, 0x48, 1])
    return b'\xff\xff' + fields + bytes([(~sum(fields)) & 255])


def parse_health(data, ident):
    if (len(data) != 7 or data[:2] != b'\xff\xff' or data[2] != ident
            or data[3] != 3 or sum(data[2:]) & 255 != 255):
        raise ProtocolError('Invalid status checksum/ID/length or echoed request')
    if data[4] or data[5] not in range(9):
        raise ProtocolError(f'Servo {ident} protection/fault: flags={data[4]:02x}, state={data[5]}')
    return data[5]


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def command(ident, body):
    integer(ident, 0, 253, 'Servo ID')
    if not re.fullmatch(r'[A-Z0-9]+', body):
        raise ValueError('Unsupported command body')
    return f'#{ident:03d}P{body}!'.encode('ascii')


def move(ident, position, milliseconds):
    integer(position, 500, 2500, 'Position')
    integer(milliseconds, 20, 9999, 'Move duration')
    return command(ident, f'{position:04d}T{milliseconds:04d}')


def parse_reply(data, ident, kind):
    """Reject echoes, wrong IDs, duplicate frames and malformed feedback."""
    if not isinstance(data, bytes) or len(data) > 2048:
        raise ProtocolError('Invalid response size')
    try:
        text = data.decode('ascii').strip('\r\n')
    except UnicodeDecodeError as exc:
        raise ProtocolError('Non-ASCII reply') from exc
    prefix = f'#{ident:03d}P'
    if not text.startswith(prefix) or not text.endswith('!') or text.count('!') != 1:
        raise ProtocolError(f'Missing, duplicate or wrong-ID reply: {text!r}')
    body = text[len(prefix):-1]
    if body.startswith('ERR:'):
        raise ProtocolError(f'Servo {ident} returned {body}')
    if kind == 'position':
        if not re.fullmatch(r'\d{4}', body):
            raise ProtocolError('Expected actual PRAD position, not echo/target/ACK')
        return integer(int(body), 500, 2500, 'Feedback position')
    if kind == 'mode':
        if not re.fullmatch(r'MOD[1-4]', body):
            raise ProtocolError('Servo position mode 1–4 required')
        return int(body[3:])
    if kind == 'ok':
        if body != 'OK':
            raise ProtocolError('Expected addressed POK; RFM must be 0')
        return True
    if kind == 'version':
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\([A-Za-z0-9_.-]+\)', body):
            raise ProtocolError('Expected model/version reply')
        return body
    raise ValueError('Unknown reply type')
