"""Explicit one-isolated-servo ID assignment; never broadcasts or moves."""
import argparse
import json
from pathlib import Path
import threading

from .device import Mmio, WireBus
from .protocol import command, parse_reply, integer


def assign_id(bus, old, new):
    integer(old,0,253,'Current ID');integer(new,0,253,'New ID')
    if old==new:raise ValueError('Old and new IDs are the same')
    version=parse_reply(bus.exchange(command(old,'VER')),old,'version')
    # A success response uses the NEW ID, per Servo.C manual page 4.
    parse_reply(bus.exchange(command(old,f'ID{new}')),new,'ok')
    verified=parse_reply(bus.exchange(command(new,'VER')),new,'version')
    if verified!=version:raise RuntimeError('Version changed after ID assignment')
    return {'old_id':old,'new_id':new,'version':version,'motion_commands_sent':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--bus',choices=['person','tiger'],required=True)
    parser.add_argument('--old',type=int,default=0)
    parser.add_argument('--new',type=int,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--only-one-servo-connected',action='store_true')
    parser.add_argument('--electrical-3v3-verified',action='store_true')
    args=parser.parse_args()
    integer(args.old,0,253,'Old ID');integer(args.new,0,253,'New ID')
    if not args.execute:
        print('Offline ID plan: '+json.dumps({'bus':args.bus,'old':args.old,'new':args.new}))
        return
    if not args.only_one_servo_connected or not args.electrical_3v3_verified:
        parser.error('Physical isolation and 3.3V compatibility must be confirmed')
    reg=Mmio(args.manifest)
    try:
        bus=WireBus(reg,0x100 if args.bus=='person' else 0x200,threading.Lock())
        print(json.dumps(assign_id(bus,args.old,args.new)))
    finally:reg.close()


if __name__=='__main__':main()
