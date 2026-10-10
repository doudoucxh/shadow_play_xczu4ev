#!/usr/bin/env python3
"""Single-servo nominal-angle/pulse control, without opening a camera."""
import argparse
from datetime import datetime
import json
import tkinter as tk
from tkinter import ttk

from servo_center_gui import App, Worker, PROJECT, PINS
from servo_manual_session import ManualSession, angle_to_pulse, pulse_to_angle, jog_pulse, validate_pulse
from servo_button_jog import load_button_limits, checked_target, next_button_pulse, INTERVAL_MS, STEP_US


class ManualWorker(Worker):
    session_class = ManualSession
    log_folder = 'servo_manual'
    allow_active_updates = True


class ManualApp(App):
    window_title = '皮影舵机 · 单路角度调试'
    heading = '单路角度调试'
    subtitle = '0–270° 标称角度 / 500–2500 μs  ·  50 Hz  ·  持续保持，手动停止'
    window_size = '900x900'
    window_minimum = (870, 870)
    body_padding = 16
    history_rows = 3
    worker_class = ManualWorker
    footer = ('按钮模式限未接木杆云台；数值模式限已解除机构约束的舵机；接杆范围尚未验证。\n'
              '“停止 PWM”不等于断电。重新安装支架前请先关闭舵机独立电源。')

    def __init__(self, root):
        self.latest = None
        self.last_action = None
        self.observation_path = None
        self.holding_channel = None
        self.stopping = False
        self.press_direction = 0
        self.press_channel = None
        self.press_job = None
        self.button_limits = load_button_limits()
        super().__init__(root)
        root.geometry(f'{self.window_size}+{max(0, (root.winfo_screenwidth()-900)//2)}+10')
        self.center_button.configure(text='回中 135° / 1500 μs')
        root.bind_all('<ButtonRelease-1>', lambda event: self.release_press(), add='+')
        root.bind('<FocusOut>', lambda event: root.after_idle(self.check_press_focus), add='+')
        root.bind('<Unmap>', lambda event: self.release_press() if event.widget == root else None, add='+')
        root.bind('<Escape>', lambda event: self.stop(), add='+')

    def build_extra_controls(self, body):
        self.mode = tk.StringVar(value='angle')
        self.angle = tk.StringVar(value='135')
        self.pulse = tk.StringVar(value='1500')
        self.preview = tk.StringVar()
        self.adopted = tk.StringVar(value='上次采用的指令：未读取（实际角度没有反馈）')
        self.control_mode = tk.StringVar(value='target')
        self.limit_text = tk.StringVar()
        box = ttk.LabelFrame(body, text='输入目标；点击发送后才会动作', padding=10)
        box.pack(fill='x', pady=(0, 8))
        self.mode_angle = ttk.Radiobutton(box, text='标称角度 °', variable=self.mode, value='angle', command=self.preview_target)
        self.mode_angle.grid(row=0, column=0, sticky='w')
        self.angle_entry = ttk.Entry(box, textvariable=self.angle, width=10)
        self.angle_entry.grid(row=0, column=1, padx=8)
        self.mode_pulse = ttk.Radiobutton(box, text='脉宽 μs', variable=self.mode, value='pulse', command=self.preview_target)
        self.mode_pulse.grid(row=0, column=2, padx=(20, 0))
        self.pulse_entry = ttk.Entry(box, textvariable=self.pulse, width=10)
        self.pulse_entry.grid(row=0, column=3, padx=8)
        self.send_button = ttk.Button(box, text='发送目标', command=self.send_target)
        self.send_button.grid(row=0, column=4, padx=12)
        ttk.Label(box, textvariable=self.preview).grid(row=1, column=0, columnspan=5, sticky='w', pady=(8, 5))
        ttk.Label(box, text='回中 = 135°；0° 是标称端点。角度由脉宽换算，不是云台对幕布的角度。').grid(row=2, column=0, columnspan=5, sticky='w')
        mode_row = ttk.Frame(box)
        mode_row.grid(row=3, column=0, columnspan=5, sticky='w', pady=(8, 3))
        self.control_mode_buttons = []
        for value, label in (('target', '数值 / 单次点动'), ('button', '按住按钮调节（未接木杆）')):
            button = ttk.Radiobutton(mode_row, text=label, variable=self.control_mode,
                                     value=value, command=self.control_mode_changed)
            button.pack(side='left', padx=(0, 20))
            self.control_mode_buttons.append(button)
        row = self.single_jog_row = ttk.Frame(box)
        row.grid(row=4, column=0, columnspan=5, sticky='w', pady=(5, 5))
        ttk.Label(row, text='相对上次指令点动：').pack(side='left')
        self.jog_buttons = []
        for delta in (-5, -1, 1, 5):
            button = ttk.Button(row, text=f'{delta:+}°', width=7, command=lambda d=delta: self.jog(d))
            button.pack(side='left', padx=5)
            self.jog_buttons.append(button)
        self.press_row = ttk.Frame(box)
        self.press_row.grid(row=4, column=0, columnspan=5, sticky='w', pady=(5, 5))
        self.press_buttons = {}
        for direction, label in ((-1, '按住：减小角度 −'), (1, '按住：增大角度 +')):
            button = ttk.Button(self.press_row, text=label, width=22)
            button.pack(side='left', padx=(0, 15))
            button.bind('<ButtonPress-1>', lambda event, d=direction: self.start_press(d))
            button.bind('<ButtonRelease-1>', lambda event: self.release_press())
            button.bind('<Leave>', lambda event: self.release_press())
            self.press_buttons[direction] = button
        ttk.Label(self.press_row, text='松开后保持最后指令').pack(side='left')
        self.press_row.grid_remove()
        ttk.Label(box, textvariable=self.limit_text, foreground='#7a4512').grid(row=5, column=0, columnspan=5, sticky='w')
        ttk.Label(box, textvariable=self.adopted, foreground='#145577').grid(row=6, column=0, columnspan=5, sticky='w', pady=4)
        self.angle.trace_add('write', lambda *_: self.preview_target())
        self.pulse.trace_add('write', lambda *_: self.preview_target())
        self.preview_target()
        observations = ttk.Frame(body)
        observations.pack(fill='x', pady=(0, 8))
        ttk.Label(observations, text='本次现场观察：').pack(side='left')
        self.observation_buttons = []
        for label in ('有转动', '没有转动', '不确定'):
            button = ttk.Button(observations, text=label, command=lambda result=label: self.record_observation(result))
            button.pack(side='left', padx=5)
            self.observation_buttons.append(button)

    def desired_pulse(self):
        if self.mode.get() == 'angle':
            return angle_to_pulse(self.angle.get())
        text = self.pulse.get().strip()
        if not text.isascii() or not text.isdigit():
            raise ValueError('脉宽请填写 500–2500 之间的整数。')
        return validate_pulse(int(text))

    def preview_target(self):
        try:
            pulse = self.desired_pulse()
            self.preview.set(f'将发送：{pulse} μs ≈ {pulse_to_angle(pulse):.3f}°；持续保持，可继续点动或点击停止。')
        except (ValueError, OverflowError):
            self.preview.set('输入范围：角度 0–270°，或整数脉宽 500–2500 μs。')

    def show_adopted(self):
        if self.latest is None:
            self.adopted.set('上次采用的指令：未读取（实际角度没有反馈）')
            return
        pulse = self.latest['pulse_us'][self.number.get()-1]
        self.adopted.set(f'该通道上次采用：{pulse} μs ≈ {pulse_to_angle(pulse):.3f}°；实际位置仍需现场观察。')

    def selection_changed(self):
        self.release_press()
        super().selection_changed()
        self.last_action = None
        pulse = self.latest['pulse_us'][self.number.get()-1] if self.latest else 1500
        self.angle.set(f'{pulse_to_angle(pulse):.3f}')
        self.pulse.set(str(pulse))
        self.show_adopted()
        self.show_button_limits()
        self.update_controls()

    def show_button_limits(self):
        low, high = self.button_limits[self.number.get()]
        if self.control_mode.get() == 'button':
            self.limit_text.set(f'本路按钮范围约 {pulse_to_angle(low):.1f}–{pulse_to_angle(high):.1f}°（边界内缩 10°）；每步约 {STEP_US*270/2000:.2f}°。先发送起始角度建立保持。')
        else:
            self.limit_text.set('数值模式保留原电气范围；装配后的机械行程不能按 0–270°使用。')

    def control_mode_changed(self):
        self.release_press()
        self.confirmed.set(False)
        button_mode = self.control_mode.get() == 'button'
        if button_mode:
            self.single_jog_row.grid_remove()
            self.press_row.grid()
            self.confirm_box.configure(text='我确认木杆未连接，当前姿态与计划运动路径无干涉，并在现场观察、可随时断电。')
        else:
            self.press_row.grid_remove()
            self.single_jog_row.grid()
            self.confirm_box.configure(text='我已解除所选舵机的杆件和支架约束，输出轴可自由转动，并在现场观察。')
        self.show_button_limits()
        self.update_controls()

    def check_press_focus(self):
        if self.press_direction and self.root.focus_displayof() is None:
            self.release_press()

    def release_press(self):
        self.press_direction = 0
        self.press_channel = None
        if self.press_job is not None:
            self.root.after_cancel(self.press_job)
            self.press_job = None
        if hasattr(self, 'confirm_box'):
            self.update_controls()

    def start_press(self, direction):
        if (self.control_mode.get() != 'button' or self.press_direction or self.busy or
                not self.connected or self.closing or not self.confirmed.get() or
                self.holding_channel != self.number.get()):
            return 'break'
        self.press_buttons[direction].focus_set()
        self.press_direction, self.press_channel = direction, self.number.get()
        self.press_step()
        return 'break'

    def press_step(self):
        self.press_job = None
        if not self.press_direction:
            return
        if (not self.connected or self.closing or self.stopping or not self.confirmed.get() or
                self.control_mode.get() != 'button' or self.press_channel != self.number.get() or
                self.holding_channel != self.press_channel or self.latest is None):
            self.release_press()
            return
        if self.busy:
            return  # Only an ACK may schedule the next increment.
        try:
            prior = self.latest['pulse_us'][self.press_channel-1]
            pulse = next_button_pulse(self.button_limits, self.press_channel, prior, self.press_direction)
            if pulse == prior:
                self.release_press()
                self.state.set('已到按钮模式的内缩边界，停止递增并保持；请松开按钮。')
                return
            self.angle.set(f'{pulse_to_angle(pulse):.3f}')
            self.pulse.set(str(pulse))
            self.submit(pulse)
        except ValueError as error:
            self.release_press()
            self.state.set('按钮调节未发送：' + str(error))

    def update_controls(self):
        super().update_controls()
        if self.holding_channel is not None:
            for button in self.radios:
                button.configure(state='disabled')
            self.confirm_box.configure(state='disabled' if self.busy or self.closing or self.press_direction else 'normal')
        ready = self.connected and not self.busy and not self.closing and self.confirmed.get()
        self.send_button.configure(state='normal' if ready and not self.press_direction else 'disabled')
        if self.press_direction:
            self.center_button.configure(state='disabled')
        for button in self.jog_buttons:
            button.configure(state='normal' if ready and self.latest is not None and not self.press_direction else 'disabled')
        for widget in (self.angle_entry, self.pulse_entry, self.mode_angle, self.mode_pulse):
            widget.configure(state='disabled' if self.busy or self.closing or self.press_direction else 'normal')
        for widget in self.control_mode_buttons:
            widget.configure(state='disabled' if self.busy or self.closing or self.press_direction else 'normal')
        for direction, button in self.press_buttons.items():
            enabled = (self.control_mode.get() == 'button' and self.connected and not self.closing and
                       not self.stopping and self.confirmed.get() and self.holding_channel == self.number.get() and
                       (self.press_direction == direction or (not self.press_direction and not self.busy)))
            button.configure(state='normal' if enabled else 'disabled')
        can_record = not self.busy and not self.closing and self.last_action is not None
        for button in self.observation_buttons:
            button.configure(state='normal' if can_record else 'disabled')

    def submit(self, pulse):
        if not self.connected or self.busy or self.closing or not self.confirmed.get():
            return
        validate_pulse(pulse)
        if self.control_mode.get() == 'button':
            checked_target(self.button_limits, self.number.get(), pulse)
        self.last_action = None
        self.busy = True
        self.state.set(f'请求 {self.number.get()} 号：{pulse} μs ≈ {pulse_to_angle(pulse):.3f}°；请现场观察。')
        self.commands.put(('move', (self.number.get(), pulse)))
        self.update_controls()

    def center(self):
        try:
            self.submit(1500)
        except ValueError as error:
            self.state.set('回中未发送：' + str(error))

    def completed_message(self, channel):
        return f'{channel} 号 PWM 已停止。实际位置需要现场确认；拆装前须断电。'

    def remaining_message(self, value):
        if self.press_direction:
            return f'{self.number.get()} 号按住调节中 · {self.active_pulse} μs · 松开/移开鼠标停止递增'
        return f'{self.number.get()} 号持续输出 {self.active_pulse} μs · 可继续调本路；换编号请先停止 PWM'

    def stop(self):
        self.release_press()
        if not self.connected or self.closing:
            return
        self.stopping = True
        self.busy = True
        super().stop()
        self.update_controls()

    def toggle_connection(self):
        self.release_press()
        super().toggle_connection()

    def close(self):
        self.release_press()
        super().close()

    def send_target(self):
        try:
            self.submit(self.desired_pulse())
        except (ValueError, OverflowError) as error:
            self.state.set('输入未发送：' + str(error))

    def jog(self, delta):
        if self.latest is None:
            return
        try:
            pulse = jog_pulse(self.latest['pulse_us'][self.number.get()-1], delta)
            self.angle.set(f'{pulse_to_angle(pulse):.3f}')
            self.pulse.set(str(pulse))
            self.submit(pulse)
        except ValueError as error:
            self.state.set('点动未发送：' + str(error))

    def on_event(self, event, value):
        if event in ('stopped', 'completed', 'disconnected', 'error'):
            self.release_press()
            self.holding_channel = None
            self.stopping = False
        if event in ('disconnected', 'error'):
            self.latest = None
            self.last_action = None
            self.show_adopted()
        elif event == 'connected':
            self.observation_path = PROJECT / 'logs' / 'servo_manual' / ('observations_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
        elif event == 'snapshot':
            self.latest = value
            self.show_adopted()
        elif event == 'active':
            channel, state = value
            self.latest = state
            self.holding_channel = channel
            self.busy = self.stopping
            self.show_adopted()
            pulse = state['pulse_us'][channel-1]
            self.last_action = {'command_time': datetime.now().astimezone().isoformat(),
                                'channel': channel, 'pin': PINS[channel-1], 'pulse_us': pulse,
                                'nominal_degrees': pulse_to_angle(pulse),
                                'sequence': state['sequence'], 'actual_angle_degrees': None}
            if self.press_direction and not self.stopping and not self.closing:
                if self.press_job is not None:
                    self.root.after_cancel(self.press_job)
                self.press_job = self.root.after(INTERVAL_MS, self.press_step)

    def record_observation(self, observation):
        if self.last_action is None or self.busy or self.observation_path is None:
            return
        record = dict(self.last_action, observation=observation,
                      observation_time=datetime.now().astimezone().isoformat())
        try:
            with self.observation_path.open('a', encoding='utf-8') as file:
                file.write(json.dumps(record, ensure_ascii=False) + '\n')
            self.log(f'已记录 {record["channel"]} 号：{observation}（{record["pulse_us"]} μs）；这不是自动故障判定。')
        except OSError as error:
            self.state.set('观察记录保存失败：' + str(error))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    root = tk.Tk()
    app = ManualApp(root)
    if args.smoke_test:
        assert app.commands.empty() and not app.connected
        app.confirmed.set(True)
        app.angle.set('140')
        app.send_target()
        assert app.commands.empty()
        app.number.set(10)
        app.selection_changed()
        assert not app.confirmed.get() and str(app.send_button['state']) == 'disabled'
        app.angle.set('nan')
        app.send_target()
        assert app.commands.empty()
        root.after(500, app.close)
    root.mainloop()


if __name__ == '__main__':
    main()
