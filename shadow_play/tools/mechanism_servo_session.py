"""Host transport for explicit per-servo targets with other outputs retained."""
from servo_center_session import CenterSession, all_off
from servo_manual_session import validate_pulse


class MechanismServoSession(CenterSession):
    service = 'attended-mechanism-v1'
    board_script = 'mechanism_manual_console.py'
    expected_hold_seconds = None

    def valid_service(self, state):
        return (super().valid_service(state) and state.get('hold_mode') == 'until_stopped'
                and state.get('retaining_other_outputs') is True)

    def move(self, channel, pulse, observer_confirmed):
        if type(channel) is not int or not 1 <= channel <= 10 or observer_confirmed is not True:
            raise ValueError('请选择一路，并确认现场监护、本次目标和联动空间。')
        validate_pulse(pulse)
        before = self.status()
        mask = before.get('enabled_mask')
        if (type(mask) is not int or not 0 <= mask < 1024 or before.get('pending')
                or before.get('faults') or before.get('output_lost')):
            raise RuntimeError('输出状态异常，请停止并检查。')
        if not all_off(before) and not (before.get('armed') is True and mask > 0):
            raise RuntimeError('输出状态不一致，请停止并检查。')
        if len(before.get('pulse_us', [])) != 10 or type(before.get('sequence')) is not int:
            raise RuntimeError('缺少完整的板端指令快照。')
        expected = list(before['pulse_us'])
        expected[channel-1] = pulse
        state = self._request('move', dict(channel=channel, pulse_us=pulse, observer_confirmed=True,
                    initial_jump_acknowledged=True, sequence=before['sequence'], expected_mask=mask))
        if (not isinstance(state, dict) or
                type(state.get('enabled_mask')) is not int or
                state.get('enabled_mask') != mask | (1 << (channel-1)) or state.get('armed') is not True
                or state.get('pending') is not False or state.get('faults') != 0
                or state.get('pulse_us') != expected or type(state.get('sequence')) is not int
                or state.get('sequence') != (before['sequence']+1) & 0xffffffff):
            self.stop()
            raise RuntimeError('板端采用指令与本次请求不符，已请求停止全部输出。')
        return state

    def center(self, channel, observer_confirmed):
        return self.move(channel, 1500, observer_confirmed)
