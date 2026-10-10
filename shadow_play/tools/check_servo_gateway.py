#!/usr/bin/env python3
"""Verify an uncommissioned, outputs-OFF gateway without enabling PWM."""
import argparse
import json
import socket
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--port',type=int,default=7000)
    args=parser.parse_args()
    durations=[]
    def exchange(operation,payload=None):
        started=time.monotonic()
        with socket.create_connection((args.host,args.port),3) as connection:
            connection.settimeout(3)
            connection.sendall((json.dumps({'operation':operation,'payload':payload or {}})+'\n').encode())
            result=json.loads(connection.makefile('rb').readline(8193))
        durations.append((time.monotonic()-started)*1000)
        return result
    initial=None
    for _ in range(10):
        response=exchange('status')
        assert response.get('ok') is True,response
        state=response['result']
        assert state['identity']=='SP10' and state['period_us']==20000 and state['clock_hz']==100000000
        assert state['enabled_mask']==0 and not state['armed'] and state['faults']==0 and not state['pending']
        if initial is None: initial=state
        assert state==initial,'Read-only status changed hardware state'
    response=exchange('off')
    assert response.get('ok') is True,response
    assert response['result']==initial,'OFF should preserve this already-off state'
    print(json.dumps({'result':'VM_TO_WINDOWS_TO_ZYNQ_PASS','requests':len(durations),
                      'max_roundtrip_ms':round(max(durations),1),'final':response['result']},indent=2))


if __name__=='__main__': main()
