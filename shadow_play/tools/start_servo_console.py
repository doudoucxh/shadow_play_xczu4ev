#!/usr/bin/env python3
"""Start the read-only-by-default service from an already authenticated root shell.

This helper never logs in, supplies passwords, loads an image, or enables PWM.
Do not use it while any other program owns the PS serial port.
"""
import argparse
import json
import re
import time


def main():
    import serial
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM13')
    parser.add_argument('--board-dir',required=True)
    parser.add_argument('--commissioning',default='servo_commissioning.template.json',
                        help='Existing JSON basename under the board project config directory')
    parser.add_argument('--known-root-shell',action='store_true',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'/run/media/mmcblk0p2/piying/[A-Za-z0-9_.-]+',args.board_dir):
        raise ValueError('Expected a dedicated project directory on the SD data partition')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.json',args.commissioning):
        raise ValueError('Commissioning filename must be a simple JSON basename')
    port=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=2)
    port.dtr=False;port.rts=False;port.port=args.port
    port.open()
    launched=False;ready=False
    try:
        port.write(b'\r')
        deadline=time.monotonic()+3
        observed=b''
        while time.monotonic()<deadline:
            observed+=port.read(4096)
            if re.search(rb'shadowdpupetalinux:[^\r\n]*#\s*$',observed): break
        else: raise RuntimeError('Expected root shell prompt; no service command sent')
        port.write(b'stty -echo\r')
        time.sleep(.2);port.read_all()
        command=('python3 -u '+args.board_dir+'/integrations/calibration/servo_console.py'
                 ' --commissioning '+args.board_dir+'/config/'+args.commissioning
                 +'; stty echo\r')
        port.write(command.encode('ascii'));launched=True
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            line=port.readline(8193)
            prefix=line.find(b'@@SP10@@')
            if prefix<0: continue
            status=json.loads(line[prefix+8:])
            state=status.get('state',{})
            if (status.get('ready') is not True or state.get('identity')!='SP10' or
                state.get('armed') is not False or state.get('enabled_mask')!=0):
                raise RuntimeError('Console did not report all PWM outputs disabled')
            ready=True
            print(json.dumps({'result':'CONSOLE_READY_OUTPUTS_OFF','state':state}),flush=True)
            return
        raise RuntimeError('Console startup not acknowledged')
    finally:
        if launched and not ready:
            port.write(b'\x03')  # console finally block disables PWM
        port.close()


if __name__=='__main__': main()
