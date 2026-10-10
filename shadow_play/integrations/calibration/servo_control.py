#!/usr/bin/env python3
"""Explicit one-channel controls for the Windows serial gateway; never retries."""
import argparse
import json
import socket


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=7000)
    sub=parser.add_subparsers(dest='operation',required=True)
    sub.add_parser('status'); sub.add_parser('off')
    initialize=sub.add_parser('initialize')
    initialize.add_argument('channel',type=int,choices=range(1,11))
    jog=sub.add_parser('jog')
    jog.add_argument('channel',type=int,choices=range(1,11))
    jog.add_argument('delta_us',type=int,choices=[-5,-4,-3,-2,-1,1,2,3,4,5])
    args=parser.parse_args()
    payload={}
    if args.operation in ('initialize','jog'): payload['channel']=args.channel
    if args.operation=='jog': payload['delta_us']=args.delta_us
    request={'operation':args.operation,'payload':payload}
    with socket.create_connection((args.host,args.port),timeout=3) as connection:
        connection.settimeout(3)
        connection.sendall((json.dumps(request)+'\n').encode())
        line=connection.makefile('rb').readline(8193)
        if len(line)>8192 or not line.endswith(b'\n'):
            raise RuntimeError('Unknown command result; inspect status before further action. No retry.')
    response=json.loads(line)
    print(json.dumps(response,indent=2,ensure_ascii=False))
    if response.get('ok') is not True:
        raise SystemExit(1)


if __name__=='__main__': main()
