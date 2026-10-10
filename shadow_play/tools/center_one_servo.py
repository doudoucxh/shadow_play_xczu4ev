#!/usr/bin/env python3
"""One explicit unloaded 1500 us reference action; OFF after a bounded hold.

Requires an already running servo_console with this channel commissioned for
unloaded centering. Never retries initialize, sweeps, or starts a camera.
The heartbeat lives only in this process; losing it stops PWM via the watchdog.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from serial_gateway import SerialLink


def main():
    import serial
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM13')
    parser.add_argument('--channel',required=True,type=int,choices=range(1,11))
    parser.add_argument('--hold-seconds',type=float,default=5)
    parser.add_argument('--unloaded-and-observer-ready',action='store_true',required=True)
    parser.add_argument('--log',type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.hold_seconds<=10: raise ValueError('Hold must be 1..10 seconds')
    port=serial.Serial(port=None,baudrate=115200,timeout=.15,write_timeout=.5)
    port.dtr=False;port.rts=False;port.port=args.port
    link=None
    with args.log.open('x',encoding='utf-8') as log:
        try:
            port.open()
            link=SerialLink(port,log)  # Verifies all outputs OFF, then starts heartbeat.
            result=link.exchange('initialize',{'channel':args.channel})
            if result.get('ok') is not True: raise RuntimeError(result.get('error','Initialize rejected'))
            state=result['result']
            if (state['enabled_mask'] != 1<<(args.channel-1) or
                state['pulse_us'][args.channel-1]!=1500 or not state['armed'] or state['faults']):
                raise RuntimeError('Unexpected adopted state; stopping outputs')
            print(json.dumps({'event':'CENTER_COMMAND_ADOPTED','channel':args.channel,
                              'pulse_us':1500,'state':state}),flush=True)
            deadline=time.monotonic()+args.hold_seconds
            while time.monotonic()<deadline:
                if link.failed: raise RuntimeError('Link failed; hardware watchdog will stop PWM')
                time.sleep(min(.05,max(0,deadline-time.monotonic())))
            stopped=link.exchange('off',{})
            if (stopped.get('ok') is not True or stopped['result']['enabled_mask']!=0 or
                stopped['result']['armed'] or stopped['result']['pending']):
                raise RuntimeError('OFF state not confirmed; use physical power switch')
            print(json.dumps({'event':'CENTER_OUTPUT_OFF','state':stopped['result'],
                              'physical_position_confirmed':False}),flush=True)
        finally:
            if link is not None: link.close()
            elif port.is_open: port.close()


if __name__=='__main__': main()
