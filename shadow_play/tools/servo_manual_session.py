"""Nominal angle conversion and explicit arbitrary-pulse bench commands."""
import math

from servo_center_session import CenterSession, all_off


def angle_to_pulse(angle):
    if isinstance(angle, bool):
        raise ValueError('角度必须是 0–270 之间的有限数值。')
    angle = float(angle)
    if not math.isfinite(angle) or not 0 <= angle <= 270:
        raise ValueError('角度必须在 0–270° 范围内。')
    return int(math.floor(500 + angle * 2000 / 270 + .5))


def validate_pulse(pulse):
    if type(pulse) is not int or not 500 <= pulse <= 2500:
        raise ValueError('脉宽必须是 500–2500 μs 之间的整数。')
    return pulse


def pulse_to_angle(pulse):
    return (validate_pulse(pulse) - 500) * 270 / 2000


def jog_pulse(pulse, delta_degrees):
    # Based on the adopted pulse for this channel, never an unsent entry value.
    return angle_to_pulse(pulse_to_angle(pulse) + delta_degrees)


def person_command_report(state):
    """Export commands with output validity, never masquerading as feedback."""
    pulses = state['pulse_us']
    if len(pulses) != 10:
        raise ValueError('需要十路完整指令快照')
    lines = ['人物六路指令快照（不是实际轴角反馈）',
             '序号：' + str(state['sequence'])]
    for i, pulse in enumerate(pulses[:6]):
        active = (state.get('armed') is True and
                  bool(state.get('enabled_mask', 0) & (1 << i)) and
                  not state.get('pending') and not state.get('faults'))
        label = '正在输出' if active else '未确认输出；仅历史指令，不能作起点'
        lines.append(f'{i+1}号：{validate_pulse(pulse)} μs / {pulse_to_angle(pulse):.3f}°；{label}')
    return '\n'.join(lines)


class ManualSession(CenterSession):
    service = 'unloaded-manual-v2'
    board_script = 'manual_servo_console.py'
    expected_hold_seconds = None

    def valid_service(self, state):
        return (super().valid_service(state) and state.get('hold_mode') == 'until_stopped'
                and state.get('same_channel_updates') is True)

    def move(self, channel, pulse, unloaded_confirmed):
        if type(channel) is not int or not 1 <= channel <= 10 or unloaded_confirmed is not True:
            raise ValueError('选择 1–10 号并确认该舵机已解除约束。')
        validate_pulse(pulse)
        before = self.status()
        if before.get('pending') or before.get('faults'):
            raise RuntimeError('输出状态异常，请先停止并检查。')
        if not all_off(before) and not (before.get('armed') is True and before.get('enabled_mask') == 1 << (channel-1)):
            raise RuntimeError('其他通道仍有输出，请先停止再换编号。')
        state = self._request('move', {'channel': channel, 'pulse_us': pulse, 'unloaded_confirmed': True})
        if (state.get('enabled_mask') != 1 << (channel-1) or state.get('armed') is not True
                or state.get('pending') or state.get('faults') or state['pulse_us'][channel-1] != pulse):
            self.stop()
            raise RuntimeError('板端采用的通道/脉宽不符合请求，已请求停止。')
        return state

    def center(self, channel, unloaded_confirmed):
        return self.move(channel, 1500, unloaded_confirmed)
