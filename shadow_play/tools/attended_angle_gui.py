"""Manual boundary commands; opening or connecting does not send motion."""
import argparse
import tkinter as tk
from tkinter import ttk
from servo_manual_gui import ManualApp, ManualWorker
from servo_manual_session import ManualSession, validate_pulse
from servo_center_session import all_off
from servo_center_gui import PINS


class AttendedAngleSession(ManualSession):
    service = 'attended-angle-v1'
    board_script = 'attended_angle_console.py'
    board_dir = '/run/media/mmcblk0p2/piying/attended-angle-20261019'

    def valid_service(self, state):
        return (super().valid_service(state)
                and state.get('manual_command_policy') == 'attended-single-axis'
                and state.get('manual_diagnostics_available') is True
                and state.get('manual_channel_range') == [1,10])

    def move(self, channel, pulse, observer_confirmed):
        if type(channel) is not int or not 1 <= channel <= 10 or observer_confirmed is not True:
            raise ValueError('请选择一路，并确认现场监护和活动空间。')
        validate_pulse(pulse)
        before = self.status()
        if before.get('pending') or before.get('faults'):
            raise RuntimeError('输出异常，请停止并检查。')
        if not all_off(before) and not (before.get('armed') is True and before.get('enabled_mask') == 1 << (channel-1)):
            raise RuntimeError('换编号前请先停止 PWM。')
        state = self._request('move',dict(channel=channel,pulse_us=pulse,observer_confirmed=True,
                    initial_jump_acknowledged=True,sequence=before['sequence']))
        if (state.get('enabled_mask') != 1 << (channel-1) or state.get('armed') is not True
                or state.get('pending') or state.get('faults') or state['pulse_us'][channel-1] != pulse):
            self.stop(); raise RuntimeError('板端指令核对失败，已请求停止。')
        return state


class AttendedAngleWorker(ManualWorker):
    session_class = AttendedAngleSession
    log_folder = 'attended_angle'


class AttendedAngleApp(ManualApp):
    window_title = '人工监护 · 舵机角度与边界调试'
    heading = '单路角度与边界调试'
    worker_class = AttendedAngleWorker
    footer = ('0–270° 是电气指令范围，不代表装配后的可动范围。首次启用可能立即大幅转动。\n'
              '其余九路关闭；联动机构仍可能被牵动。停止PWM不是断电；异常时立即切断舵机电源。')

    def __init__(self,root):
        super().__init__(root)
        self.port.set('COM17')
        for button in self.control_mode_buttons:button.pack_forget()
        self.confirm_box.configure(text='我在设备旁可立即断电，已检查本次目标及联动空间，并知晓初次转动可能较快。')
        self.center_button.configure(text='回中 135° / 1500 μs')

    def selection_changed(self):
        super().selection_changed()
        channel = self.number.get()
        self.selected.set(f'当前：{channel} 号 · 引脚 {PINS[channel-1]} · 实物杆件对应待现场核对')

    def build_extra_controls(self,body):
        super().build_extra_controls(body)
        row=ttk.Frame(body);row.pack(fill='x',pady=(0,8))
        ttk.Label(row,text='人工确认本次位置后记录：').pack(side='left')
        for label,result in (('记录下限','人工观察下限'),('记录上限','人工观察上限')):
            button=ttk.Button(row,text=label,command=lambda value=result:self.record_observation(value))
            button.pack(side='left',padx=5);self.observation_buttons.append(button)

    def show_button_limits(self):
        self.limit_text.set('人工边界测试：允许输入0–270°；建议从已知位置逐步点动，不能把全范围当作可安全扫动的行程。')

    def submit(self,pulse):
        # This window exposes explicit numerical requests only, never press-and-hold scanning.
        self.control_mode.set('target')
        super().submit(pulse)

    def on_event(self,event,value):
        super().on_event(event,value)
        if event=='connected' and self.observation_path is not None:
            self.observation_path=self.observation_path.parents[1]/'attended_angle'/self.observation_path.name


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke-test',action='store_true');args=parser.parse_args()
    root=tk.Tk();app=AttendedAngleApp(root)
    if args.smoke_test:
        assert not app.connected and app.commands.empty()
        assert app.port.get() == 'COM17'
        assert '实物杆件对应待现场核对' in app.selected.get()
        app.confirmed.set(True)
        for target in ('0','135','270','nan','271'):
            app.angle.set(target);app.send_target();assert app.commands.empty()
        app.number.set(4);app.selection_changed();assert not app.confirmed.get()
        assert str(app.send_button['state'])=='disabled'
        root.after(100,app.close)
    root.mainloop()

if __name__=='__main__':main()
