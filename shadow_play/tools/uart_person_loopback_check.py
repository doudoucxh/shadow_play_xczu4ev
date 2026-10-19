"""One address-1 read-query echo on the isolated person UART, with motors off.

Requires the motor's RX/TX disconnected from FPGA and F15 linked to H13.
An echo establishes this board-side loop only, never a motor handshake.
"""
import argparse
import json
import mmap
import os
from pathlib import Path

from zdt_readonly_protocol import query
from zdt_uartlite_telemetry import PORTS, QueryPort, TelemetryError, validate_pin_map

IMAGE_SHA='ea680d88d2d149157490ebbe27b253b3814d6d2df17aeebb477047bb4bc81e90'


class LoopbackPort(QueryPort):
    def decode_reply(self,address,kind,raw,*,checksum_mode,firmware_kind):
        expected=query(1,'version',checksum_mode='fixed_6b')
        if (address!=1 or kind!='version' or checksum_mode!='fixed_6b' or raw!=expected):
            raise TelemetryError('Not the exact three-byte local loopback echo')
        return dict(local_loopback_echo_verified=True,motor_handshake_verified=False,
                    position_feedback=None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-id',required=True)
    parser.add_argument('--expected-sequence',required=True,type=int)
    parser.add_argument('--execute-check',action='store_true')
    parser.add_argument('--actuators-off-confirmed',action='store_true')
    parser.add_argument('--person-motor-signals-disconnected-confirmed',action='store_true')
    parser.add_argument('--f15-h13-linked-confirmed',action='store_true')
    args=parser.parse_args()
    if not args.execute_check:
        print('OFFLINE_LOOPBACK_DESCRIPTION '+json.dumps(dict(
            pins=['F15','H13'],rail='person',query_hex='011f6b',motor_motion=False)))
        return
    if not all((args.actuators_off_confirmed,args.person_motor_signals_disconnected_confirmed,
                args.f15_h13_linked_confirmed)):
        raise TelemetryError('Actual power-off, isolated motor signals and loopback-link confirmations required')
    import fcntl
    from mmio32 import WordAccess
    from servo_pwm_device import Registers,PwmDevice
    marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    validate_pin_map(marker.get('rail_uart',{}),'standard')
    if (boot!=args.boot_id or marker.get('boot_id')!=boot or marker.get('sha256')!=IMAGE_SHA or
            marker.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS' or
            marker['rail_uart'].get('design_checks')!='RAIL_UART_DESIGN_CHECKS_PASS' or
            marker['rail_uart'].get('baud')!=115200 or marker['rail_uart'].get('format')!='8N1'):
        raise TelemetryError('Reviewed standard UART image/boot mismatch')
    with Path('/run/shadow-rail-uart.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        registers=Registers()
        try:
            state=PwmDevice(registers).status()
            if (any(state[k] for k in ('armed','enabled_mask','pending','faults')) or
                    state['sequence']!=args.expected_sequence):
                raise TelemetryError('Bound stopped PWM state mismatch')
            used=Path('/run/shadow-person-uart-loopback-20261019.used')
            with used.open('x') as handle:
                handle.write(json.dumps(dict(boot_id=boot,query_hex='011f6b'))+'\n')
            fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
            try:
                with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,
                               offset=PORTS['person']['base']) as memory:
                    words=WordAccess(memory);port=LoopbackPort(words)
                    try:
                        result=port.request(1,'version',checksum_mode='fixed_6b',firmware_kind='Emm')
                    except Exception as error:
                        print('UART_LOOPBACK_ERROR '+json.dumps(dict(error=str(error),
                            reply_hex=port.received.hex(),diagnostics=port.diagnostics(),
                            motor_motion_sent=False)),flush=True)
                        raise
                    finally:words.close()
            finally:os.close(fd)
            after=PwmDevice(registers).status()
            if after!=state:raise TelemetryError('PWM state changed during loopback')
            print('UART_LOOPBACK '+json.dumps(dict(result=result,diagnostics=port.diagnostics(),
                pwm_unchanged=True,motor_motion_sent=False)),flush=True)
        finally:registers.close()


if __name__=='__main__':main()
