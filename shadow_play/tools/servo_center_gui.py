#!/usr/bin/env python3
"""Local Windows interface; opening the window never connects or moves a servo."""
import argparse
from datetime import datetime
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from servo_center_session import CenterSession, all_off

PROJECT = Path(__file__).resolve().parents[1]
PINS = ('D14', 'D15', 'F13', 'G13', 'G14', 'G15', 'J14', 'E13', 'E14', 'E15')
RODS = ('人物左手', '人物头部', '人物右手', '老虎头部', '老虎脚部')


class Worker(threading.Thread):
    session_class = CenterSession
    log_folder = 'servo_center'
    allow_active_updates = False

    def __init__(self, commands, events):
        super().__init__(daemon=True)
        self.commands = commands
        self.events = events
        self.session = None
        self.active = None
        self.next_poll = 0

    def release(self):
        try:
            if self.session is not None:
                self.session.close()
        finally:
            self.session = None
            self.active = None

    def run(self):
        while True:
            try:
                try:
                    command, value = self.commands.get(timeout=.10)
                except queue.Empty:
                    command, value = None, None
                if command == 'shutdown':
                    try:
                        self.release()
                    finally:
                        self.events.put(('closed', None))
                    return
                if command == 'connect':
                    if self.session is not None:
                        raise RuntimeError('请先断开当前连接。')
                    folder = PROJECT / 'logs' / self.log_folder
                    folder.mkdir(parents=True, exist_ok=True)
                    log = folder / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
                    self.session = self.session_class(value, log)
                    self.events.put(('connected', str(log)))
                elif command == 'disconnect':
                    self.release()
                    self.events.put(('disconnected', None))
                elif command in ('center', 'move'):
                    channel = value if command == 'center' else value[0]
                    if self.session is None or (self.active is not None and
                            (not self.allow_active_updates or self.active != channel)):
                        raise RuntimeError('连接未就绪；换编号前请先停止输出。')
                    if command == 'center':
                        channel = value
                        state = self.session.center(channel, True)
                    else:
                        channel, pulse = value
                        state = self.session.move(channel, pulse, True)
                    self.active = channel
                    self.events.put(('active', (channel, state)))
                elif command == 'stop' and self.session is not None:
                    self.session.stop()
                    self.active = None
                    self.events.put(('stopped', None))
                if self.session is not None and time.monotonic() >= self.next_poll:
                    state = self.session.status()
                    self.events.put(('snapshot', state))
                    self.next_poll = time.monotonic() + (.2 if self.active else 1)
                    if self.active is not None:
                        if all_off(state):
                            channel, self.active = self.active, None
                            if state.get('faults'):
                                raise RuntimeError('板端已停输出，但报告故障；请检查电源/串口后重新连接。')
                            self.events.put(('completed', channel))
                        elif state['enabled_mask'] != 1 << (self.active-1) or state.get('faults'):
                            self.session.stop()
                            raise RuntimeError('输出状态异常，已请求停止。')
                        else:
                            self.events.put(('remaining', state.get('center_remaining_seconds', 0)))
            except Exception as error:
                message = str(error)
                try:
                    self.release()
                except Exception:
                    pass
                self.events.put(('error', message))


class App:
    window_title = '皮影舵机 · 单路快速回中'
    heading = '单路快速回中'
    subtitle = '固定 1500 μs  ·  50 Hz  ·  保持 5 秒后自动停止 PWM'
    window_size = '830x640'
    window_minimum = (790, 600)
    worker_class = Worker
    body_padding = 24
    history_rows = 5
    footer = ('回中结束 → 关闭舵机独立电源 → 保持轴位置 → 重新安装舵盘/支架。\n'
              '“停止 PWM”不等于切断电源；遇到卡阻请立即关闭舵机电源。')

    def __init__(self, root):
        self.root = root
        root.title(self.window_title)
        root.geometry(self.window_size)
        root.minsize(*self.window_minimum)
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 20, 'bold'))
        style.configure('Action.TButton', font=('Microsoft YaHei UI', 15, 'bold'), padding=12)
        self.commands, self.events = queue.Queue(), queue.Queue()
        self.worker = self.worker_class(self.commands, self.events)
        self.worker.start()
        self.connected = False
        self.busy = False
        self.closing = False
        self.active_pulse = 1500
        self.port = tk.StringVar(value='COM13')
        self.number = tk.IntVar(value=1)
        self.confirmed = tk.BooleanVar(value=False)
        self.state = tk.StringVar(value='未连接 · 打开窗口不会发送舵机动作')
        self.selected = tk.StringVar()
        body = ttk.Frame(root, padding=self.body_padding)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=self.heading, style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text=self.subtitle).pack(anchor='w', pady=(5, 15))
        connection = ttk.Frame(body)
        connection.pack(fill='x')
        ttk.Label(connection, text='PS 调试串口').pack(side='left')
        self.port_box = ttk.Combobox(connection, textvariable=self.port, width=12)
        self.port_box.pack(side='left', padx=10)
        self.refresh_button = ttk.Button(connection, text='刷新', command=self.refresh_ports)
        self.refresh_button.pack(side='left')
        self.connect_button = ttk.Button(connection, text='连接板子', command=self.toggle_connection)
        self.connect_button.pack(side='right')
        ttk.Label(body, text='连接前：关闭其他串口工具；板端已登录 root，且已加载十路 PWM 镜像。').pack(anchor='w', pady=(8, 14))
        group = ttk.LabelFrame(body, text='选择一个舵机', padding=12)
        group.pack(fill='x')
        self.radios = []
        for i in range(10):
            button = ttk.Radiobutton(group, text=f'{i+1} 号  {PINS[i]}', value=i+1,
                                     variable=self.number, command=self.selection_changed)
            button.grid(row=i//5, column=i%5, padx=12, pady=8, sticky='w')
            self.radios.append(button)
        ttk.Label(body, textvariable=self.selected, font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w', pady=(15, 8))
        self.build_extra_controls(body)
        self.confirm_box = ttk.Checkbutton(body, variable=self.confirmed, command=self.update_controls,
            text='我已解除所选舵机的杆件和支架约束，输出轴可自由转动，并在现场观察。')
        self.confirm_box.pack(anchor='w')
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=15)
        self.center_button = ttk.Button(actions, text='所选舵机回中（5 秒）', style='Action.TButton', command=self.center)
        self.center_button.pack(side='left', fill='x', expand=True, padx=(0, 12))
        self.stop_button = ttk.Button(actions, text='停止 PWM', style='Action.TButton', command=self.stop)
        self.stop_button.pack(side='right')
        ttk.Label(body, textvariable=self.state, wraplength=765, foreground='#145577').pack(anchor='w', pady=(0, 8))
        ttk.Label(body, text=self.footer, wraplength=800).pack(anchor='w')
        self.history = tk.Text(body, height=self.history_rows, wrap='word', state='disabled', font=('Microsoft YaHei UI', 9))
        self.history.pack(fill='both', expand=True, pady=(12, 0))
        self.refresh_ports()
        self.selection_changed()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.receive)

    def build_extra_controls(self, body):
        pass

    def on_event(self, event, value):
        pass

    def completed_message(self, channel):
        return f'{channel} 号 PWM 已自动停止。请确认停稳，再断开舵机电源进行安装。'

    def remaining_message(self, value):
        return f'{self.number.get()} 号正在输出 {self.active_pulse} μs · 剩余 {value:.1f} 秒'

    def log(self, text):
        self.history.configure(state='normal')
        self.history.insert('end', datetime.now().strftime('%H:%M:%S') + '  ' + text + '\n')
        self.history.see('end')
        self.history.configure(state='disabled')

    def refresh_ports(self):
        from serial.tools import list_ports
        self.port_box['values'] = [item.device for item in list_ports.comports()]

    def selection_changed(self):
        channel = self.number.get()
        self.confirmed.set(False)
        self.selected.set(f'当前：{channel} 号 · {RODS[(channel-1)//2]} · 引脚 {PINS[channel-1]}')
        self.update_controls()

    def update_controls(self):
        locked = self.busy or self.closing
        self.center_button.configure(state='normal' if self.connected and not locked and self.confirmed.get() else 'disabled')
        self.stop_button.configure(state='normal' if self.connected and not self.closing else 'disabled')
        self.connect_button.configure(text='断开连接' if self.connected else '连接板子', state='disabled' if locked else 'normal')
        self.confirm_box.configure(state='disabled' if locked else 'normal')
        self.port_box.configure(state='disabled' if self.connected or locked else 'normal')
        self.refresh_button.configure(state='disabled' if self.connected or locked else 'normal')
        for button in self.radios:
            button.configure(state='disabled' if locked else 'normal')

    def toggle_connection(self):
        self.busy = True
        self.confirmed.set(False)
        self.state.set('正在连接并核对板端输出…' if not self.connected else '正在停止输出并释放串口…')
        self.commands.put(('disconnect', None) if self.connected else ('connect', self.port.get().strip()))
        self.update_controls()

    def center(self):
        if not self.connected or self.busy or not self.confirmed.get():
            return
        self.busy = True
        self.confirmed.set(False)
        self.state.set(f'正在请求 {self.number.get()} 号回中；请现场观察。')
        self.commands.put(('center', self.number.get()))
        self.update_controls()

    def stop(self):
        self.commands.put(('stop', None))
        self.state.set('正在请求停止 PWM；若有卡阻，请直接关闭舵机电源。')

    def receive(self):
        while True:
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == 'closed':
                self.root.destroy()
                return
            self.on_event(event, value)
            if event == 'connected':
                self.connected, self.busy = True, False
                self.state.set('已连接 · 十路 PWM 均已关闭，可以选择舵机。')
                self.log('连接完成；日志：' + value)
            elif event == 'disconnected':
                self.connected, self.busy = False, False
                self.state.set('已断开连接；串口已释放。')
            elif event == 'active':
                channel, state = value
                self.active_pulse = state['pulse_us'][channel-1]
                self.log(f'{channel} 号已接受 {self.active_pulse} μs 指令；其余九路未启用。')
            elif event == 'remaining':
                self.state.set(self.remaining_message(value))
            elif event == 'completed':
                self.busy = False
                self.state.set(self.completed_message(value))
                self.log(f'{value} 号输出结束，已确认十路关闭；实际位置需要你现场确认。')
            elif event == 'stopped':
                self.busy = False
                self.state.set('已确认十路 PWM 关闭。提前停止不代表已经回中。')
                self.log('人工停止 PWM。')
            elif event == 'error':
                self.connected, self.busy = False, False
                self.confirmed.set(False)
                self.state.set('连接/操作失败：' + value + ' 若刚才正在动作，请先断开舵机电源。')
                self.log('错误：' + value)
            self.update_controls()
        self.root.after(80, self.receive)

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.state.set('正在停止输出并关闭窗口…')
        self.commands.put(('shutdown', None))
        self.update_controls()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true', help='Create UI and close without connecting')
    args = parser.parse_args()
    root = tk.Tk()
    app = App(root)
    if args.smoke_test:
        assert not app.connected and app.commands.empty()
        assert str(app.center_button['state']) == 'disabled'
        app.confirmed.set(True)
        app.update_controls()
        assert str(app.center_button['state']) == 'disabled'
        app.number.set(10)
        app.selection_changed()
        assert not app.confirmed.get() and app.commands.empty()
        root.after(500, app.close)
    root.mainloop()


if __name__ == '__main__':
    main()
