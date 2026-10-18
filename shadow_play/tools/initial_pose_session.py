"""Explicit host-side group initialization; no connect-time movement."""
from servo_center_session import CenterSession, all_off
from initial_pose_model import validate_pulses


class InitialPoseSession(CenterSession):
    service='attended-initial-pose-v1'
    board_script='initial_pose_console.py'
    board_dir='/run/media/mmcblk0p2/piying/servo-initial-pose-20261018'
    expected_hold_seconds=None

    def valid_service(self,state):
        return (super().valid_service(state) and state.get('group_initialization') is True
                and state.get('hold_mode')=='until_stopped')

    def initialize(self,pulses,observer_confirmed):
        pulses=validate_pulses(pulses)
        if observer_confirmed is not True:raise ValueError('请先确认现场监护、十路目标和联动空间。')
        before=self.status()
        if not all_off(before) or before.get('faults') or before.get('output_lost'):
            raise RuntimeError('需要先停止全部输出并检查状态。')
        sequence=before.get('sequence')
        if type(sequence) is not int or not 0<=sequence<=0xffffffff:raise RuntimeError('板端缺少有效序号。')
        state=self._request('initialize',dict(pulse_us=pulses,sequence=sequence,
                            observer_confirmed=True,initial_jump_acknowledged=True))
        if (state.get('armed') is not True or type(state.get('enabled_mask')) is not int
                or state['enabled_mask']!=1023 or state.get('pending') is not False
                or state.get('faults')!=0 or state.get('pulse_us')!=pulses
                or type(state.get('sequence')) is not int or state['sequence']!=(sequence+1)&0xffffffff):
            self.stop()
            raise RuntimeError('十路回执与目标不符，已请求全部停止。')
        return state
