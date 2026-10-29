"""第二部分：按画画动作名称逐项录入反馈舵机位置。"""
import argparse
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .model import Profile
from .pose_library import ROOT, PoseLibrary, file_sha, save_library
from .pose_worker import PoseWorker

DEFAULT_PATH = ROOT / 'logs/bus_servo/pose_library/画画动作位置库.json'
VERSION = '2026.10.30-pose-r1'


class PoseApp:
    def __init__(self, root, profile_path, library_path=DEFAULT_PATH):
        self.root = root
        self.profile = Profile.load(profile_path)
        self.library = PoseLibrary(self.profile)
        self.path = Path(library_path)
        self.disk_sha = None
        self.connected = self.busy = self.moving = self.closing = False
        self.motion_allowed = self.release_allowed = False
        self.ready = set()
        self.rows = {}
        self.pending_capture = None
        self.serial = 0
        self.dirty = False
        self.commands, self.events = queue.Queue(), queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = PoseWorker(self.commands, self.events, self.stop_flag)
        self.worker.start()
        root.title('皮影 · 画画动作位置库 · ' + VERSION)
        root.geometry('1200x850')
        root.minsize(1060, 780)
        root.configure(bg='#eef2f5')
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#eef2f5')
        style.configure('TLabel', background='#eef2f5', foreground='#203246')
        style.configure('TButton', padding=(8, 5))
        style.configure('Accent.TButton', background='#216c79', foreground='white')
        body = ttk.Frame(root, padding=16)
        body.pack(fill='both', expand=True)
        header = ttk.Frame(body)
        header.pack(fill='x')
        ttk.Label(header, text='画画 · 动作位置库', font=('Microsoft YaHei UI', 22, 'bold')).pack(side='left')
        ttk.Button(header, text='操作说明', command=self.help).pack(side='right')
        ttk.Label(body, text='选动作 → 手摆或设角 → 读取实际位置保存 → 单独调用检查',
                  foreground='#526b7c').pack(anchor='w', pady=(4, 12))
        connection = ttk.Frame(body)
        connection.pack(fill='x')
        self.mode = tk.StringVar(value='离线模拟')
        self.mode_box = ttk.Combobox(connection, textvariable=self.mode, values=['离线模拟', '实物 / PS串口'],
                                     width=17, state='readonly')
        self.mode_box.pack(side='left')
        self.port = tk.StringVar(value='COM17')
        ttk.Label(connection, text='PS串口').pack(side='left', padx=(12, 5))
        self.port_box = ttk.Entry(connection, textvariable=self.port, width=9)
        self.port_box.pack(side='left')
        self.connect_button = ttk.Button(connection, text='连接', command=lambda:self.action(self.connect))
        self.connect_button.pack(side='left', padx=7)
        self.probe_button = ttk.Button(connection, text='检测当前角色', command=lambda:self.send('probe', self.axes()))
        self.probe_button.pack(side='left')
        self.link_text = tk.StringVar(value='未连接')
        ttk.Label(connection, textvariable=self.link_text).pack(side='left', padx=14)
        self.attended = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text='实物操作：我在现场可断电，已扶稳需卸力的机构，并检查运动空间。',
                        variable=self.attended).pack(anchor='w', pady=9)
        content = ttk.Frame(body)
        content.pack(fill='both', expand=True)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        left = ttk.Frame(content, padding=(0, 0, 15, 0))
        left.grid(row=0, column=0, sticky='ns')
        self.progress = tk.StringVar()
        ttk.Label(left, textvariable=self.progress, font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(0, 8))
        tree_area = ttk.Frame(left)
        tree_area.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(tree_area, columns=('state',), show='tree headings', selectmode='browse', height=16)
        self.tree.heading('#0', text='动作名称')
        self.tree.heading('state', text='位置')
        self.tree.column('#0', width=155, stretch=False)
        self.tree.column('state', width=85, stretch=False)
        scroll = ttk.Scrollbar(tree_area, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        for key, row in self.library.catalog.items():
            self.tree.insert('', 'end', iid=key, text=row['actor'] + ' · ' + row['name'])
        self.tree.bind('<<TreeviewSelect>>', self.select_action)
        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky='nsew')
        self.title = tk.StringVar()
        ttk.Label(right, textvariable=self.title, font=('Microsoft YaHei UI', 18, 'bold')).pack(anchor='w')
        guide = ttk.Frame(left)
        guide.pack(side='bottom', fill='x', pady=4, before=tree_area)
        self.canvas = tk.Canvas(guide, width=185, height=155, bg='#faf5e8', highlightthickness=0)
        self.canvas.pack()
        self.instructions = tk.StringVar()
        ttk.Label(right, textvariable=self.instructions, wraplength=680, justify='left').pack(fill='x', pady=8)
        self.table = ttk.Frame(right)
        self.table.pack(fill='x', pady=6)
        self.targets, self.feedback, self.selected = {}, {}, {}
        self.axis_widgets = []
        self.target_entries = []
        for col, label in enumerate(['调节', '编号 / 部位', '实际位置', '目标角度 / °', '已保存 / °']):
            ttk.Label(self.table, text=label, font=('Microsoft YaHei UI', 10, 'bold')).grid(row=0, column=col, padx=7, pady=6)
        self.saved_values = {}
        for n, axis in self.profile.axes.items():
            self.targets[n] = tk.StringVar(value='')
            self.feedback[n] = tk.StringVar(value='未检测')
            self.saved_values[n] = tk.StringVar(value='—')
            self.selected[n] = tk.BooleanVar(value=True)
            widgets = [ttk.Checkbutton(self.table, variable=self.selected[n]),
                       ttk.Label(self.table, text=f'{n:02d} · {axis.label}'),
                       ttk.Label(self.table, textvariable=self.feedback[n], foreground='#216c79'),
                       ttk.Spinbox(self.table, textvariable=self.targets[n], from_=axis.minimum,
                                   to=axis.maximum, increment=.5, width=10),
                       ttk.Label(self.table, textvariable=self.saved_values[n])]
            self.axis_widgets.append((n, widgets))
            self.target_entries.append(widgets[3])
        adjust = ttk.Frame(right)
        adjust.pack(fill='x', pady=8)
        self.copy_button = ttk.Button(adjust, text='实际位置填入目标', command=self.copy_feedback)
        self.copy_button.pack(side='left')
        self.duration = tk.StringVar(value='2')
        ttk.Label(adjust, text='最短到达 / 秒').pack(side='left', padx=(12, 4))
        ttk.Spinbox(adjust, from_=.02, to=9.999, increment=.5, textvariable=self.duration, width=6).pack(side='left')
        self.move_button = ttk.Button(adjust, text='设置勾选角度', command=lambda:self.action(self.move))
        self.move_button.pack(side='left', padx=8)
        hand = ttk.Frame(right)
        hand.pack(fill='x', pady=3)
        self.release_button = ttk.Button(hand, text='当前角色卸力 / 手摆', command=lambda:self.action(self.release))
        self.release_button.pack(side='left')
        self.drag_button = ttk.Button(hand, text='模拟手摆到目标', command=lambda:self.action(lambda:self.send('drag', self.target_positions())))
        self.drag_button.pack(side='left', padx=8)
        note_row = ttk.Frame(right)
        note_row.pack(fill='x', pady=8)
        ttk.Label(note_row, text='备注').pack(side='left')
        self.note = tk.StringVar()
        ttk.Entry(note_row, textvariable=self.note).pack(side='left', fill='x', expand=True, padx=8)
        save_row = ttk.Frame(right)
        save_row.pack(fill='x', pady=7)
        self.capture_button = ttk.Button(save_row, text='① 读取实际位置并保存此动作', style='Accent.TButton',
                                         command=lambda:self.action(self.capture))
        self.capture_button.pack(side='left')
        self.recall_button = ttk.Button(save_row, text='② 调用已保存姿势', command=lambda:self.action(self.recall))
        self.recall_button.pack(side='left', padx=8)
        ttk.Label(right, text='保存会新读当前角色全部舵机；勾选仅用于设角。\n'
                  '切换动作和填写目标不发送运动；图示为画画参考。',
                  foreground='#526b7c', wraplength=690).pack(anchor='w', pady=5)
        bottom = ttk.Frame(body)
        bottom.pack(fill='x', pady=(12, 6))
        self.open_button = ttk.Button(bottom, text='打开动作库…', command=lambda:self.action(self.open_library))
        self.open_button.pack(side='left')
        self.save_as_button = ttk.Button(bottom, text='动作库另存为…', command=lambda:self.action(self.save_as))
        self.save_as_button.pack(side='left', padx=8)
        self.retry_button = ttk.Button(bottom, text='保存当前库', command=lambda:self.action(self.persist))
        self.retry_button.pack(side='left')
        tk.Button(bottom, text='停止当前动作 / Esc', bg='#b84443', fg='white', relief='flat',
                  padx=16, pady=8, command=self.stop).pack(side='right')
        self.path_text = tk.StringVar(value=str(self.path))
        ttk.Label(body, textvariable=self.path_text, foreground='#526b7c', wraplength=1100).pack(anchor='w')
        self.status = tk.StringVar(value='默认离线。连接前请先在第一部分上位机断开串口。')
        ttk.Label(body, textvariable=self.status, wraplength=1100).pack(anchor='w', pady=(5, 0))
        # Reserve the file/stop/status rows before assigning remaining height to content.
        body.columnconfigure(0, weight=1)
        for child in body.winfo_children():
            child.pack_forget()
        for index, child in enumerate(body.winfo_children()):
            child.grid(row=index, column=0, sticky='nsew', pady=3)
        body.rowconfigure(4, weight=1)
        if self.path.exists():
            try:
                self.read_library(self.path)
            except Exception as exc:
                self.status.set('原动作库未加载，请检查后打开或另存：' + str(exc))
                # Keep expected_sha=None so an unreadable original cannot be overwritten.
        self.current_key = 'wusong/neutral'
        self.tree.selection_set(self.current_key)
        self.render_action()
        self.refresh_library()
        root.bind('<Escape>', lambda event:self.stop())
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(50, self.receive)

    def axes(self):
        return self.library.catalog[self.current_key]['axes'][:]

    def select_action(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        if self.busy or self.moving or self.pending_capture:
            if selection[0] != self.current_key:
                self.tree.selection_set(self.current_key)
            return
        self.current_key = selection[0]
        self.render_action()
        self.commands.put(('select', self.axes()))

    def render_action(self):
        row = self.library.catalog[self.current_key]
        entry = self.library.data['poses'].get(self.current_key)
        source = ('实物反馈' if entry['pose']['source'] == 'servo_feedback' else '模拟反馈') if entry else '尚未录入'
        self.title.set(row['actor'] + ' · ' + row['name'] + '  [' + source + ']')
        self.instructions.set(row['instruction'] + ' ' + row.get('distinguishing_instruction', ''))
        self.note.set(entry.get('note', '') if entry else '')
        for n, widgets in self.axis_widgets:
            for col, widget in enumerate(widgets):
                widget.grid_forget()
                if n in self.axes():
                    widget.grid(row=self.axes().index(n) + 1, column=col, sticky='w', padx=7, pady=2)
            angle = f'{self.profile.axes[n].degrees(entry["pose"]["positions"][str(n)]):.3f}' if entry and n in self.axes() else ''
            self.targets[n].set(angle)
            self.saved_values[n].set(angle or '—')
        self.draw_reference(row['pose'])
        self.update_controls()

    def draw_reference(self, pose):
        c = self.canvas
        c.delete('all')
        if pose is None:
            c.create_text(92, 85, text='老虎站立\n手动录入四轴位置', justify='center', fill='#526b7c')
            return
        def point(name):
            x, y = pose[name]
            return (15 + 155*x, 4 + 145*y)
        for names in [('neck', 'hip'), ('leftShoulder', 'neck', 'rightShoulder'),
                      ('leftShoulder', 'leftElbow', 'leftWrist'), ('rightShoulder', 'rightElbow', 'rightWrist'),
                      ('hip', 'leftKnee', 'leftFoot'), ('hip', 'rightKnee', 'rightFoot')]:
            c.create_line(*[v for name in names for v in point(name)], width=4, fill='#216c79', capstyle='round')
        x, y = point('head')
        c.create_oval(x-9, y-11, x+9, y+11, width=3, outline='#216c79')

    def refresh_library(self):
        actual = simulated = 0
        for key in self.library.catalog:
            entry = self.library.data['poses'].get(key)
            state = '未录入'
            if entry:
                is_real = entry['pose']['source'] == 'servo_feedback'
                actual += is_real
                simulated += not is_real
                state = '实物已录入' if is_real else '模拟已录入'
            self.tree.set(key, 'state', state)
        self.progress.set(f'实物 {actual}/21 · 模拟 {simulated}')

    def update_controls(self):
        idle = not (self.busy or self.moving or self.closing)
        ready = self.connected and set(self.axes()) <= self.ready
        simulation = self.mode.get() == '离线模拟'
        for button, enabled in [(self.connect_button, idle), (self.probe_button, idle and self.connected),
                (self.copy_button, idle and ready), (self.move_button, idle and ready and self.motion_allowed),
                (self.release_button, idle and ready and self.release_allowed),
                (self.drag_button, idle and ready and simulation), (self.capture_button, idle and ready),
                (self.recall_button, idle and ready and self.motion_allowed and self.current_key in self.library.data['poses']),
                (self.open_button, idle), (self.save_as_button, idle), (self.retry_button, idle)]:
            button.configure(state='normal' if enabled else 'disabled')
        self.connect_button.configure(text='断开' if self.connected else '连接')
        self.mode_box.configure(state='readonly' if idle and not self.connected else 'disabled')
        self.port_box.configure(state='normal' if idle and not self.connected else 'disabled')

    def action(self, callback):
        try:
            callback()
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror('操作未完成', str(exc), parent=self.root)

    def send(self, op, value=None):
        if self.busy or self.moving or self.closing:
            return
        self.busy = True
        self.commands.put((op, value))
        self.update_controls()

    def connect(self):
        self.send('disconnect' if self.connected else 'connect',
                  None if self.connected else (self.profile, self.mode.get() == '离线模拟', self.port.get().strip()))

    def target_positions(self):
        numbers = [n for n in self.axes() if self.selected[n].get()]
        self.profile.select(numbers)
        return {str(n):self.profile.axes[n].position(float(self.targets[n].get())) for n in numbers}

    def check_operator(self):
        if self.mode.get() != '离线模拟' and not self.attended.get():
            raise ValueError('请先确认现场条件。')

    def move(self):
        self.check_operator()
        self.send('move', (self.target_positions(), float(self.duration.get()), self.attended.get()))

    def release(self):
        self.check_operator()
        self.send('release', (self.axes(), self.attended.get()))

    def recall(self):
        self.check_operator()
        pose = self.library.get_pose(self.current_key, live=self.mode.get() != '离线模拟')
        self.send('recall', ((self.current_key, pose), float(self.duration.get()), self.attended.get()))

    def copy_feedback(self):
        for n in self.axes():
            if n in self.rows:
                self.targets[n].set(f'{self.profile.axes[n].degrees(self.rows[n]["p"]):.3f}')

    def capture(self):
        if len(self.note.get()) > 2000:
            raise ValueError('动作备注最多2000字。')
        if self.current_key in self.library.data['poses'] and not messagebox.askyesno(
                '更新动作位置', '替换这个动作的已保存位置？旧版本会保留在动作库旁的 history 文件夹。', parent=self.root):
            return
        self.serial += 1
        self.pending_capture = (self.serial, self.current_key, self.note.get())
        self.send('capture', (self.serial, self.current_key))

    def accept_capture(self, value):
        token, key, pose = value
        if not self.pending_capture or (token, key) != self.pending_capture[:2]:
            return
        note = self.pending_capture[2]
        self.pending_capture = None
        self.library.set_pose(key, pose, note)
        self.dirty = True
        self.refresh_library()
        self.render_action()
        self.persist()
        self.status.set('已读取并保存：' + self.library.catalog[key]['name'] + '。可继续选择下一个动作。')

    def persist(self):
        self.disk_sha = save_library(self.path, self.library, self.disk_sha)
        self.dirty = False
        self.path_text.set(str(self.path))

    def read_library(self, path):
        # Read content and its signature from the same bytes.
        raw = Path(path).read_bytes()
        library = PoseLibrary(self.profile, json.loads(raw.decode('utf-8-sig')))
        import hashlib
        self.library, self.path = library, Path(path)
        self.disk_sha = hashlib.sha256(raw).hexdigest()
        self.dirty = False
        self.path_text.set(str(self.path))

    def open_library(self):
        if self.dirty:
            raise ValueError('当前新记录尚未落盘，请先保存或另存后再打开。')
        path = filedialog.askopenfilename(parent=self.root, title='打开画画动作位置库', filetypes=[('动作位置库', '*.json')])
        if path:
            self.read_library(path)
            self.refresh_library()
            self.render_action()
            self.status.set('已打开动作库。选择或载入姿势不会发送运动。')

    def save_as(self):
        path = filedialog.asksaveasfilename(parent=self.root, title='另存画画动作位置库',
            initialfile='画画动作位置库.json', defaultextension='.json', filetypes=[('动作位置库', '*.json')])
        if path:
            signature = save_library(path, self.library, file_sha(path))
            self.path, self.disk_sha = Path(path), signature
            self.dirty = False
            self.path_text.set(str(self.path))
            self.status.set('动作库已另存，后续录入自动保存到这个文件。')

    def stop(self):
        self.pending_capture = None
        self.stop_flag.set()
        self.busy = True
        self.status.set('正在停止；取消尚未完成的读取保存。')
        self.update_controls()

    def receive(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'closed':
                    self.root.destroy()
                    return
                if kind == 'connected':
                    self.connected = True
                    self.motion_allowed = value['motion_allowed']
                    self.release_allowed = value['release_allowed']
                    self.ready = set(self.profile.axes) if value['simulation'] else set()
                    self.link_text.set('模拟已连接' if value['simulation'] else '板子已连接 · 请检测当前角色')
                    self.status.set('连接完成；实物模式需先检测当前角色。')
                elif kind in ('disconnected', 'error'):
                    self.connected = self.moving = self.busy = False
                    self.ready.clear()
                    self.rows.clear()
                    self.pending_capture = None
                    self.motion_allowed = self.release_allowed = False
                    self.link_text.set('未连接')
                    for var in self.feedback.values():
                        var.set('未连接')
                    self.status.set('已断开。' if kind == 'disconnected' else '已中止并断开：' + value)
                elif kind == 'ready':
                    self.ready = set(value)
                    self.rows.clear()
                    self.link_text.set('当前角色反馈已检测')
                elif kind == 'unavailable':
                    self.ready.clear()
                    self.rows.clear()
                    self.busy = False
                    self.pending_capture = None
                    for var in self.feedback.values():
                        var.set('反馈无效')
                    self.status.set('反馈不可用，请重新检测：' + value)
                elif kind == 'feedback':
                    self.rows = value
                    for n, var in self.feedback.items():
                        var.set(f'{self.profile.axes[n].degrees(value[n]["p"]):.2f}°' if n in value else '未采样')
                elif kind == 'captured':
                    self.action(lambda:self.accept_capture(value))
                elif kind == 'moving':
                    self.moving = True
                    self.status.set(f'目标已发送，约 {value:.2f} 秒后核对到位；Esc停止。')
                elif kind == 'arrived':
                    self.moving = False
                    self.status.set('本次动作到位反馈通过（误差≤2°），保持姿势。')
                elif kind == 'stopped':
                    self.busy = self.moving = False
                    self.pending_capture = None
                    self.status.set('停止请求已处理；运动中停止会卸力，请扶稳机构。')
                elif kind == 'rejected':
                    self.pending_capture = None
                    self.status.set('操作未完成：' + value)
                elif kind == 'done':
                    self.busy = False
                elif kind == 'message':
                    self.status.set(value)
                self.update_controls()
        except queue.Empty:
            pass
        self.root.after(50, self.receive)

    def help(self):
        messagebox.showinfo('画画动作库使用顺序',
            '1. 先在第一部分上位机断开串口，再选择实物 / PS串口、连接和检测当前角色。\n'
            '2. 左侧选择动作。图示和名称与画画识别库对应。\n'
            '3. 卸力后扶稳手摆；或把实际位置填入目标，勾选要调的轴、改角度并设置。\n'
            '4. 稳定后点“读取实际位置并保存此动作”，自动新读当前角色全部轴。\n'
            '5. 点“调用已保存姿势”检查。完成一个后选下一个，未录入项保持为空。\n'
            '文件在底部所示路径；每次录入自动保存，旧版本在同名 .history 文件夹。\n'
            '模拟姿势会明确标记，不能调用到实物。此窗口保存位置，不录连续轨迹。\n'
            '此次工具在电脑端使用；动作库尚未部署到板端画画识别流程。', parent=self.root)

    def close(self):
        if self.closing:
            return
        # Stop is immediate even when saving subsequently needs user attention.
        self.stop_flag.set()
        if self.dirty:
            try:
                self.persist()
            except Exception as exc:
                self.status.set('新记录尚未保存，请另存后关闭：' + str(exc))
                messagebox.showerror('新记录尚未保存', self.status.get(), parent=self.root)
                return
        self.closing = True
        self.pending_capture = None
        self.commands.put(('shutdown', None))
        self.update_controls()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=ROOT / 'config/bus_servo.json')
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    root = tk.Tk()
    app = PoseApp(root, args.profile)
    if args.smoke_test:
        root.after(300, app.close)
    root.mainloop()


if __name__ == '__main__':
    main()
