"""Explicit attended ten-axis initial targets; never an automatic story unlock.

The initial physical travel is unknown and cannot be rate-limited from reset
registers. Only the local operator's confirmed target vector may ARM from OFF.
The incident locks remain intact and still block every ordinary driver.
"""
import copy
import json
import re
import sys

from attended_center_console import AttendedCenterDevice
from board_server import require
from center_console import CenterController, PREFIX, serve
from initial_pose_model import validate_pulses, DEGREE_LIMITS
from servo_pwm_device import PwmDevice, Registers

SERVICE='attended-initial-pose-v1'


class InitialPoseDevice(AttendedCenterDevice):
    def commit(self,pulses,mask,allow_arm=False):
        permit,self.permit=self.permit,None
        require(permit is not None,'Explicit attended ten-target request required')
        targets,sequence=permit
        validate_pulses(pulses)
        before=self.status()
        require(before['sequence']==sequence and not before['armed'] and before['enabled_mask']==0
                and not before['pending'] and not before['faults'],'Current clean OFF state required')
        require(pulses==targets and mask==1023 and allow_arm is True,'Only the reviewed ten-target vector is allowed')
        self.inside=True
        try:return PwmDevice.commit(self,pulses,mask,allow_arm=True)
        finally:self.inside=False


class InitialPoseController(CenterController):
    service_name=SERVICE
    hold_seconds=None

    def __init__(self,device,**kwargs):
        super().__init__(device,**kwargs)
        self.owned=None
        self.output_lost=False

    def tick(self):
        state=self.device.status()
        changed=self.device.lock_state()!=self.device.lock_snapshot
        if self.owned and (changed or not state['armed'] or state['enabled_mask']!=1023
                or state['pending'] or state['faults'] or state['pulse_us']!=self.owned[0]
                or state['sequence']!=self.owned[1]):
            self.device.off()
            self.owned=None
            self.output_lost=True
        if changed:self.output_lost=True

    def status(self):
        state=super().status()
        state.update(group_initialization=True,hold_mode='until_stopped',position_feedback=None,
                     initial_pose_limits_deg=DEGREE_LIMITS,output_lost=self.output_lost)
        return state

    def handle(self,request):
        self.tick()
        require(isinstance(request,dict),'Request object required')
        ident=request.get('transport_id')
        require(isinstance(ident,str) and re.fullmatch('[a-f0-9]{32}',ident),'Invalid transport ID')
        encoded=json.dumps(request,sort_keys=True,allow_nan=False)
        if ident in self.cache:
            previous,ack=self.cache[ident]
            require(previous==encoded,'Transport ID reused with different request')
            return copy.deepcopy(ack)
        ack=dict(transport_id=ident,ok=False)
        try:
            require(set(request)=={'transport_id','operation','payload'},'Invalid envelope')
            operation,payload=request['operation'],request['payload']
            require(isinstance(payload,dict),'Payload object required')
            if operation in ('hello','status','heartbeat','off'):
                require(not payload,'Unexpected payload')
                if operation=='off':
                    self.device.off();self.owned=None;self.output_lost=False
                elif operation=='heartbeat':self.device.kick()
            elif operation=='initialize':
                require(len(self.cache)<20000,'Session exhausted; stop and reconnect')
                require(set(payload)=={'pulse_us','sequence','observer_confirmed','initial_jump_acknowledged'},
                        'Ten targets, current sequence and onsite acknowledgement required')
                pulses=validate_pulses(payload['pulse_us'])
                require(type(payload['sequence']) is int and 0<=payload['sequence']<=0xffffffff,'Invalid sequence')
                require(payload['observer_confirmed'] is True and payload['initial_jump_acknowledged'] is True,
                        'Onsite review of all ten targets and initial travel required')
                require(not self.output_lost,'Output was lost; explicitly stop and inspect before retrying')
                state=self.device.status()
                require(not state['armed'] and state['enabled_mask']==0 and not state['pending'] and not state['faults'],
                        'Stop all outputs before another initial target')
                require(state['sequence']==payload['sequence'],'State changed after operator request')
                self.device.permit=(pulses[:],payload['sequence'])
                try:
                    after=self.device.commit(pulses,1023,allow_arm=True)
                    self.owned=(pulses[:],after['sequence'])
                except BaseException:
                    self.device.off();self.output_lost=True
                    raise
                finally:self.device.permit=None
            else:raise ValueError('Only initialize, status, heartbeat and off are available')
            ack.update(ok=True,result=self.status())
        except Exception as error:ack['error']=str(error)
        if request.get('operation') not in ('hello','status','heartbeat') and len(self.cache)<20000:
            self.cache[ident]=(encoded,copy.deepcopy(ack))
        return ack


def main():
    registers=Registers();controller=None
    try:
        device=InitialPoseDevice(registers)
        controller=InitialPoseController(device)
        emit=lambda value:print(PREFIX+json.dumps(value,allow_nan=False),flush=True)
        emit(dict(ready=True,state=controller.status()))
        serve(controller,sys.stdin.fileno(),emit)
    except KeyboardInterrupt:pass
    finally:
        if controller is not None:device.off()
        registers.close()


if __name__=='__main__':main()
