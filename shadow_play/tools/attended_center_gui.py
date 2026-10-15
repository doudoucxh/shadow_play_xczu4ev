"""Explicit local operator midpoint window; opening/connecting never moves."""
import argparse
import tkinter as tk
from tkinter import messagebox
from servo_center_gui import App, Worker
from servo_center_session import CenterSession, all_off


class AttendedSession(CenterSession):
    service = 'attended-midpoint-v1'
    board_script = 'attended_center_console.py'

    def center(self, channel, observer_confirmed):
        if type(channel) is not int or not 1 <= channel <= 10 or observer_confirmed is not True:
            raise ValueError('请选择一个编号并确认现场监护')
        before = self.status()
        if not all_off(before) or before.get('faults'):
            raise RuntimeError('必须先停止全部输出并检查故障')
        state = self._request('center', dict(channel=channel, observer_confirmed=True,
                    initial_jump_acknowledged=True, sequence=before['sequence']))
        if (state.get('enabled_mask') != 1 << (channel-1) or not state.get('armed') or
                state.get('pending') or state.get('faults') or state['pulse_us'][channel-1] != 1500):
            self.stop()
            raise RuntimeError('回中指令核对失败；已请求停止')
        return state


class AttendedWorker(Worker):
    session_class = AttendedSession
    log_folder = 'attended_center'


class AttendedApp(App):
    window_title = '人工监护 · 单路回中'
    heading = '人工监护 · 单路回中'
    subtitle = '仅所选一路 1500 μs / 标称135° · 最长5秒 · 其余九路关闭'
    worker_class = AttendedWorker
    footer = ('初次回中可能立即大幅转动，软件不能限制这段速度；请现场确认整段摆动空间。\n'
              '停止PWM不等于断电或锁住姿态。此工具不解除剧本锁，不证明联动标定完成。')

    def __init__(self, root):
        super().__init__(root)
        self.port.set('COM3')
        self.confirm_box.configure(text='我在机构旁能立即断电，已检查所选轴及联动杆的回中空间，并接受首次回中可能较快。')
        self.center_button.configure(text='所选一路回中 135° / 1500 μs')
        root.bind('<Escape>', lambda event: self.stop())

    def center(self):
        if not self.connected or self.busy or not self.confirmed.get():
            return
        if not messagebox.askokcancel('只回中所选一路',
                f'即将给 {self.number.get()} 号发送1500 μs，最多5秒。\n'
                '当前位置没有反馈，首次转动速度不受软件限制。\n'
                '其他九路不保持；联动杆可能跟随移动。\n'
                '确认编号、活动空间，手离开机构并守着断电开关。', parent=self.root):
            return
        super().center()

    def completed_message(self, channel):
        return f'{channel}号回中指令输出结束；已关闭PWM。是否实际回中需现场观察，关闭后位置可能偏转。'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    root = tk.Tk()
    app = AttendedApp(root)
    if args.smoke_test:
        app.confirmed.set(True)
        app.center()
        assert not app.connected and app.commands.empty()
        root.after(100, app.close)
    root.mainloop()


if __name__ == '__main__':
    main()
