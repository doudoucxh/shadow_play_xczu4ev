"""X42S manual V1.0.4 free-protocol/6B telemetry codec, with no transport.

No enable, motion, homing, parameter writes, reset, address scans or broadcast.
Reply decoding alone cannot establish freshness, physical rail zero or travel.
"""
READ_CODES={'version':0x1f,'position':0x36,'status':0x3a}
REPLY_LENGTHS={'version':7,'position':8,'status':4}


class ProtocolError(ValueError):pass


def checked_address(address):
    if type(address) is not int or not 1<=address<=255:
        raise ProtocolError('A confirmed unicast address in 1..255 is required')
    return address


def query(address,kind,*,checksum_mode):
    checked_address(address)
    if checksum_mode!='fixed_6b' or kind not in READ_CODES:
        raise ProtocolError('Only explicitly selected fixed-6B telemetry queries are supported')
    return bytes((address,READ_CODES[kind],0x6b))


def decode(address,kind,reply,*,checksum_mode,firmware_kind=None):
    expected=query(address,kind,checksum_mode=checksum_mode)
    if type(reply) is not bytes or len(reply)<3 or reply[:2]!=expected[:2] or reply[-1]!=0x6b:
        raise ProtocolError('Reply identity or checksum mismatch')
    if len(reply)!=REPLY_LENGTHS[kind]:
        raise ProtocolError('Unexpected reply length; never infer a different firmware from a short frame')
    result=dict(address=address,query=kind,freshness_verified=False,
                position_mm=None,rail_zero_verified=False)
    if kind=='version':
        fw=int.from_bytes(reply[2:4],'big');hw=int.from_bytes(reply[4:6],'big')
        result.update(firmware_version_raw=fw,hardware_version_raw=hw,
                      hardware_series=(hw>>12)&15,hardware_type=(hw>>8)&15,
                      hardware_revision=hw&255,firmware_kind=None)
    elif kind=='status':
        flags=reply[2]
        if flags&0x40:
            raise ProtocolError('Reserved status bit or device error response; inspect raw frame')
        result.update(flags_raw=flags,enabled=bool(flags&1),target_reached=bool(flags&2),
            stall_detected=bool(flags&4),stall_protection=bool(flags&8),
            left_limit_input_high=bool(flags&16),right_limit_input_high=bool(flags&32),
            power_cycle_flag=bool(flags&128),limit_trigger_polarity=None)
    else:
        if firmware_kind not in ('Emm','X') or reply[2] not in (0,1):
            raise ProtocolError('Confirmed Emm/X firmware and valid position sign are required')
        magnitude=int.from_bytes(reply[3:7],'big');signed=magnitude*(-1 if reply[2] else 1)
        degrees=signed*360/65536 if firmware_kind=='Emm' else signed/10
        result.update(firmware_kind=firmware_kind,position_raw_signed=signed,position_degrees=degrees)
    return result
