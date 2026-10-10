#!/usr/bin/env python3
"""Board electrical-command test: servo supply MUST remain disconnected/off.

Verifies AXI command adoption and watchdog, not physical pulses/servo positions.
Normal startup is read-only unless --servo-power-off-confirmed is supplied.
"""
import argparse
import json
import time
from servo_pwm_device import PwmDevice, Registers


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--servo-power-off-confirmed',action='store_true')
    args=parser.parse_args()
    registers=Registers(); device=PwmDevice(registers)
    try:
        print(json.dumps({'initial':device.status()}),flush=True)
        if not args.servo_power_off_confirmed:
            return
        print(json.dumps({'step':'explicit_off_before_test'}),flush=True)
        device.off()
        for i in range(10):
            pulses=[1500]*10; pulses[i]=1505
            state=device.commit(pulses,1<<i,allow_arm=True)
            assert state['enabled_mask']==1<<i and state['pulse_us']==pulses
            print(json.dumps({'channel':i+1,'adopted':state}),flush=True)
        device.commit([1500]*10,1023)
        time.sleep(2.2)  # Intentionally no heartbeat: verify hardware shutdown.
        state=device.status()
        assert not state['armed'] and state['enabled_mask']==0 and state['faults']&2
        print(json.dumps({'watchdog_shutdown':state,'result':'PASS_COMMAND_READBACK_AND_WATCHDOG'}),flush=True)
        device.reg.write(0x1c,0x4b49434b)  # A late heartbeat must not restart PWM.
        state=device.status()
        assert not state['armed'] and state['enabled_mask']==0 and state['faults']&2
        # Explicitly recover the deliberately injected timeout, with mask zero.
        state=device.commit([1500]*10,0,allow_arm=True)
        assert state['faults']==0 and state['enabled_mask']==0
        print(json.dumps({'recovery_outputs_off':device.off()}),flush=True)
    finally:
        if args.servo_power_off_confirmed:
            device.off()
        registers.close()


if __name__=='__main__': main()
