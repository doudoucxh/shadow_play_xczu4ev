#!/usr/bin/env python3
"""JSON roundtrip check in an already verified board root shell. No motor APIs.

Uses a temporary Python echo process, with identity UART_ECHO_ONLY. It cannot be
mistaken for a real SP10 service by serial_gateway.py's readiness check.
"""
import argparse
import json
import shlex
import statistics
import time
import uuid
import serial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM13')
    parser.add_argument('--known-root-shell',required=True,action='store_true')
    args=parser.parse_args()
    code="""import sys,json
print('UART_ECHO_READY',flush=True)
for line in sys.stdin:
 request=json.loads(line)
 print('@@SP10@@'+json.dumps({'transport_id':request['transport_id'],'identity':'UART_ECHO_ONLY','echo':request},separators=(',',':')),flush=True)
 if request.get('operation')=='probe_exit': break
"""
    port=serial.Serial(port=None,baudrate=115200,timeout=.3,write_timeout=2)
    port.dtr=False;port.rts=False;port.port=args.port;port.open()
    complete=False
    try:
        port.write(b'stty -echo\r');time.sleep(.2);port.reset_input_buffer()
        # The script source is one canonical shell line, containing no physical newlines.
        import base64
        encoded=base64.b64encode(code.encode()).decode()
        command="python3 -u -c "+shlex.quote("import base64;exec(base64.b64decode('"+encoded+"'))")+"; stty echo\r"
        port.write(command.encode())
        deadline=time.monotonic()+5;ready=False
        while time.monotonic()<deadline:
            if b'UART_ECHO_READY' in port.readline(): ready=True;break
        if not ready: raise RuntimeError('Echo process readiness missing; no JSON sent')
        timings=[]
        for index in range(10):
            request={'transport_id':uuid.uuid4().hex,'operation':'probe_exit' if index==9 else 'echo',
                     'axes':[{'axis_id':'servo_{:02d}'.format(i+1),'unit':'us','value':1500} for i in range(10)],
                     'note':'传输测试，不操作电机。'*4}
            started=time.monotonic();port.write((json.dumps(request,ensure_ascii=False,separators=(',',':'))+'\n').encode())
            line=port.readline(8193)
            if not line.startswith(b'@@SP10@@'): raise RuntimeError('Unexpected UART echo')
            response=json.loads(line[8:])
            if response.get('echo')!=request or response.get('identity')!='UART_ECHO_ONLY':
                raise RuntimeError('UART roundtrip content mismatch')
            timings.append((time.monotonic()-started)*1000)
        complete=True
        print(json.dumps({'result':'UART_ECHO_ONLY_PASS','requests':10,
            'maximum_roundtrip_ms':round(max(timings),1),'median_roundtrip_ms':round(statistics.median(timings),1),
            'motor_registers_accessed':False},indent=2))
    finally:
        if not complete: port.write(b'\x03')
        time.sleep(.3);port.close()


if __name__=='__main__': main()
