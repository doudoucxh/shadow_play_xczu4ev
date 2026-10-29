"""Windows teaching studio: selectable axes, feedback recording and replay."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .device import SimulationDevice
from .editing import PoseCaptureError
from .model import MOTION_SCHEMA, Profile, playback_plan, save_recording, validate_recording
from .session import PlaybackRejected, TeachingSession
from .transport import RemoteDevice
from .protocol import ServoUnavailable
from .timeline import PlaybackTimeline, format_time

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#26a69a', '#5477d4', '#db9239', '#d85c74', '#8a69d2', '#639d49', '#d16635', '#4d9aba', '#b477b0', '#a19a35']


class Worker(threading.Thread):
    def __init__(self, commands, events, stop_flag):
        super().__init__(daemon=True)
        self.commands, self.events, self.stop_flag = commands, events, stop_flag
        self.session = None
        self.shutting_down = False
        self.numbers = []
        self.playback_timeline = None
        self.next_progress = 0
        self.audio_player = None
        self.audio_index = 0

    def emit(self, kind, value=None):
        self.events.put((kind, value))

    def release(self):
        self.stop_audio()
        if self.session:
            try:
                self.session.close()
            finally:
                self.session = None

    def stop_audio(self):
        if self.audio_player:
            # Never delay the actuator stop while an audio driver is closing.
            self.audio_player.close(wait=False); self.audio_player = None

    def sync_audio(self):
        if not self.audio_player:return
        if self.audio_player.error:raise RuntimeError('电脑音频播放失败：'+str(self.audio_player.error))
        s=self.session
        if s.index and s.index!=self.audio_index:
            self.audio_index=s.index
            self.audio_player.segment(s.plan.source_times[s.index-1],s.plan.source_times[s.index],
                                      s.segment_started,s.segment_duration_ms/1000)

    def run(self):
        while True:
            try:
                if self.stop_flag.is_set():
                    self.stop_audio()
                    self.stop_flag.clear()
                    # Throw away queued targets before processing an emergency
                    # request. Shutdown is retained so closing still completes.
                    shutdown = False
                    while True:
                        try:
                            op, _ = self.commands.get_nowait()
                            shutdown |= op == 'shutdown'
                        except queue.Empty:
                            break
                    if self.session:
                        self.shutting_down = shutdown
                        was_recording = self.session.recording
                        stopped = self.session.stop()
                        if was_recording and self.session.record:
                            self.emit('record', (self.session.record, self.session.last_path))
                        self.emit('stopped', stopped)
                    if shutdown:
                        self.release(); self.emit('closed'); return
                    self.emit('idle')
                try:
                    op, value = self.commands.get(timeout=.01)
                except queue.Empty:
                    op, value = None, None
                if op in ('disconnect', 'shutdown'):
                    self.shutting_down = op == 'shutdown'
                    self.release(); self.emit('disconnected' if op == 'disconnect' else 'closed')
                    if op == 'shutdown':
                        return
                elif op == 'connect':
                    if self.session:
                        raise RuntimeError('请先断开现有连接。')
                    profile, simulation, port = value
                    self.numbers = [n for n in self.numbers if n in profile.axes] or profile.layout.numbers
                    device = SimulationDevice(profile) if simulation else RemoteDevice(profile, port)
                    try:
                        self.session = TeachingSession(profile, device, ROOT/'logs/bus_servo/takes')
                        self.session.cancel_requested = self.stop_flag.is_set
                    except BaseException:
                        device.close(); raise
                    self.emit('connected', {'simulation': simulation,
                                           'motion_allowed': simulation or device.motion_allowed,
                                           'release_allowed': simulation or getattr(device, 'release_allowed', False)})
                elif op == 'select':
                    if self.session:
                        self.numbers = value or self.session.profile.layout.numbers
                        self.session.profile.select(self.numbers)
                    else:
                        self.numbers = value
                elif op and self.session:
                    s = self.session
                    if op == 'probe':
                        rows = s.probe(value)
                        self.emit('servos_ready', sorted(s.ready_axes))
                        self.emit('feedback', rows)
                    elif op == 'angles':
                        s.set_angles(*value); self.emit('message', '角度指令已发送，实际位置以反馈为准。')
                    elif op == 'release':
                        s.require_feedback(value)
                        s.device.release(value); self.emit('message', '所选轴已回复卸力命令；请扶稳机构，确认松力后手动操作。')
                    elif op == 'record_start':
                        s.start_recording(*value); self.emit('recording', value[2])
                    elif op == 'record_end':
                        path = s.finish_recording(); self.emit('record', (s.record, path)); self.emit('idle')
                    elif op == 'capture_pose':
                        try:
                            self.emit('pose', s.capture_pose(value))
                        except PoseCaptureError as exc:
                            # A pose outside the configured envelope is rejected
                            # without releasing unrelated, currently held axes.
                            self.emit('capture_error', str(exc))
                    elif op == 'prepare':
                        seconds = s.prepare_first(*value)
                        self.emit('prepared')
                        self.emit('message', f'已发送到首帧指令，预计至少 {seconds:.1f} 秒；回放时会重新读位置。')
                    elif op == 'play':
                        try:
                            self.stop_audio();self.audio_index=0
                            if len(value)>3 and value[3] is not None:
                                from .audio import AudioPlayer
                                try:self.audio_player=AudioPlayer(value[3])
                                except Exception as exc:raise PlaybackRejected('电脑音频尚未就绪：'+str(exc)) from exc
                            s.start_playback(*value[:3])
                        except PlaybackRejected as exc:
                            self.stop_audio()
                            self.emit('playback_rejected', str(exc))
                        else:
                            self.playback_timeline = PlaybackTimeline(value[0], value[2], s.play_end, s.plan)
                            self.next_progress = s.play_start
                            self.emit('playing', self.playback_timeline.snapshot(state='playing'))
                    elif op == 'drag':
                        if not s.device.simulation:
                            raise RuntimeError('模拟拖动仅用于离线模式。')
                        s.device.drag(value)
                    self.emit('command_done')
                if self.session:
                    if self.audio_player and self.audio_player.error:
                        raise RuntimeError('电脑音频播放失败：'+str(self.audio_player.error))
                    rows, finished = self.session.tick(self.numbers)
                    self.sync_audio()
                    # Publish only after a successful scheduler/feedback tick.
                    # A blocked or failed request must not animate to completion.
                    if self.playback_timeline and (self.session.playing or finished):
                        now = self.session.clock()
                        if finished or now >= self.next_progress:
                            self.emit('playback_progress', self.playback_timeline.snapshot(
                                self.session.playback_elapsed(), 'completed' if finished else 'playing',
                                wall_elapsed=now-self.session.play_start))
                            self.next_progress = now + .05
                    if rows:
                        self.emit('feedback', rows)
                        if self.session.recording:
                            self.emit('sample', self.session.record['samples'][-1])
                    if finished:
                        self.stop_audio()
                        self.emit('idle'); self.emit('message', '回放已结束，末帧位置反馈通过；保持状态，点停止可卸力。')
            except ServoUnavailable as exc:
                # A failed idle query keeps the PS link alive but invalidates all
                # feedback and stops polling. Only an explicit probe can restart it.
                if self.session:
                    if self.session.recording:
                        try:
                            self.session.finish_recording(complete=False, reason=str(exc))
                            self.emit('record', (self.session.record, self.session.last_path))
                        except Exception as storage_error:
                            self.emit('message', '中断记录保存失败：'+str(storage_error))
                    self.session.ready_axes.clear()
                    self.session.last_feedback.clear()
                self.emit('servos_unavailable', str(exc))
            except Exception as exc:
                self.stop_audio()
                recovery = None
                try:
                    if self.session:
                        was_recording = self.session.recording
                        self.session.stop(reason=str(exc))
                        if was_recording and self.session.record:
                            recovery = (self.session.record, self.session.last_path)
                except Exception:
                    pass
                try:
                    self.release()
                except Exception:
                    pass
                if recovery:
                    self.emit('record', recovery)
                self.emit('error', str(exc))
                if self.shutting_down:
                    self.emit('closed'); return


class App:
    def __init__(self, root, profile_path):
        self.root, self.profile_path = root, Path(profile_path)
        self.profile = Profile.load(profile_path)
        self.commands, self.events = queue.Queue(), queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = Worker(self.commands, self.events, self.stop_flag)
        self.worker.start()
        self.connected = self.busy = self.recording = self.playing = self.closing = False
        self.ready_axes = set()
        self.motion_allowed = False
        self.release_allowed = False
        self.record = None
        self.editor = None
        self.av_editor = None
        self.live_samples = []
        self.playback_progress = None
        self.plot_bounds = None
        suffix={'dual':' · 人物 / 老虎双总线','tiger-four-port':' · 老虎临时四口','ten-port':' · 十舵机独立十口'}[self.profile.layout.name]
        root.title('皮影 · 总线舵机示教工作台（分步/剪辑）' + suffix)
        root.geometry('1180x850'); root.minsize(1030, 790)
        root.configure(bg='#eef2f5')
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#eef2f5')
        style.configure('TLabel', background='#eef2f5', foreground='#203246',font=('Microsoft YaHei UI',9))
        style.configure('TButton', padding=(10,4))
        style.configure('Accent.TButton', background='#216c79', foreground='white')
        style.configure('Playback.Horizontal.TProgressbar',background='#216c79',troughcolor='#dce6eb',
                        bordercolor='#dce6eb',lightcolor='#216c79',darkcolor='#216c79')
        body = ttk.Frame(root, padding=18); body.pack(fill='both', expand=True)
        header = ttk.Frame(body); header.pack(fill='x')
        ttk.Label(header, text='皮影示教工作台', font=('Microsoft YaHei UI',22,'bold')).pack(side='left')
        ttk.Button(header, text='使用说明', command=lambda:self.action(self.open_guide)).pack(side='right', padx=(14,0))
        self.av_button=ttk.Button(header,text='音频 / 轨迹剪辑',command=lambda:self.action(self.open_av_editor))
        self.av_button.pack(side='right',padx=(10,0))
        ttk.Label(header, text=self.profile.layout.title, foreground='#59728a').pack(side='right', pady=10)
        ttk.Label(body, text='先用手演一遍，记录舵机实际位置，再按时间重现动作。', foreground='#526b7c').pack(anchor='w', pady=(2,12))
        row = ttk.Frame(body); row.pack(fill='x', pady=(0,10))
        self.mode = tk.StringVar(value='离线模拟')
        self.mode_box = ttk.Combobox(row, textvariable=self.mode, values=['离线模拟','实物 / PS串口'], state='readonly', width=18)
        self.mode_box.pack(side='left')
        ttk.Label(row,text='PS串口').pack(side='left',padx=(16,5))
        self.port = tk.StringVar(value='COM17' if self.profile.layout.name in ('dual','ten-port') else 'COM19')
        self.port_box = ttk.Combobox(row, textvariable=self.port, width=12)
        self.port_box.pack(side='left')
        self.refresh_ports()
        ttk.Button(row,text='刷新',command=self.refresh_ports).pack(side='left',padx=5)
        self.connect_button = ttk.Button(row,text='连接',command=self.connect,style='Accent.TButton')
        self.connect_button.pack(side='left',padx=7)
        self.probe_button = ttk.Button(row,text='检测所选舵机',command=lambda:self.action(lambda:self.send('probe',self.numbers())))
        self.probe_button.pack(side='left',padx=3)
        self.configure_button = ttk.Button(row,text='ID / 角度与限位配置',command=self.configure)
        self.configure_button.pack(side='right')
        self.attended = tk.BooleanVar(value=False)
        self.attend_box = ttk.Checkbutton(body,text='实物操作：我在现场可断电，已扶稳需卸力的机构，并检查运动空间。',variable=self.attended)
        self.attend_box.pack(anchor='w',pady=(0,8))
        row = ttk.Frame(body); row.pack(fill='x',pady=(0,4))
        self.selection_buttons=[]
        groups=[('全选',self.profile.layout.numbers)]
        if any(n<=6 for n in self.profile.axes):groups.append(('人物',[n for n in self.profile.axes if n<=6]))
        groups += [('老虎',[n for n in self.profile.axes if n>=7]),('清空',[])]
        for label,nums in groups:
            b=ttk.Button(row,text=label,command=lambda nums=list(nums):self.select(nums));b.pack(side='left',padx=(0,5));self.selection_buttons.append(b)
        self.selection_text=tk.StringVar(value=f'已选 {len(self.profile.axes)} 轴')
        ttk.Label(row,textvariable=self.selection_text).pack(side='right')
        axis_area=ttk.Frame(body);axis_area.pack(fill='x',pady=4)
        self.axes_canvas=tk.Canvas(axis_area,height=250,bg='#eef2f5',highlightthickness=0)
        axis_scroll=ttk.Scrollbar(axis_area,orient='vertical',command=self.axes_canvas.yview)
        axis_scroll.pack(side='right',fill='y')
        self.axes_canvas.pack(side='left',fill='x',expand=True)
        self.axes_canvas.configure(yscrollcommand=axis_scroll.set)
        table=ttk.Frame(self.axes_canvas);self.axes_table=table
        table_window=self.axes_canvas.create_window(0,0,window=table,anchor='nw')
        table.bind('<Configure>',lambda event:self.axes_canvas.configure(scrollregion=self.axes_canvas.bbox('all')))
        self.axes_canvas.bind('<Configure>',lambda event:self.axes_canvas.itemconfigure(table_window,width=event.width))
        for col,title in enumerate(['选择','编号 / 总线ID','控制部位','总线口','实际角度','目标角度','目标调整 / °','软件范围']):
            ttk.Label(table,text=title,font=('Microsoft YaHei UI',10,'bold')).grid(row=0,column=col,sticky='w',padx=6,pady=6)
        table.columnconfigure(6,weight=1)
        self.selected={};self.targets={};self.feedback={};self.checks=[]
        for table_row,(n,a) in enumerate(self.profile.axes.items(),1):
            self.selected[n]=tk.BooleanVar(value=True)
            self.targets[n]=tk.DoubleVar(value=a.span/2)
            self.feedback[n]=tk.StringVar(value='—')
            box=ttk.Checkbutton(table,variable=self.selected[n],command=self.selection_changed);box.grid(row=table_row,column=0);self.checks.append(box)
            for col,text in [(1,f'{n:02d} / {a.ident:03d}'),(2,a.label),(3,self.profile.layout.connector_label(a.bus)),(7,f'{a.minimum:g}–{a.maximum:g}°')]:
                ttk.Label(table,text=text).grid(row=table_row,column=col,sticky='w',padx=6,pady=1)
            ttk.Label(table,textvariable=self.feedback[n],foreground=COLORS[n-1],width=11).grid(row=table_row,column=4,sticky='w',padx=6)
            ttk.Spinbox(table,from_=a.minimum,to=a.maximum,increment=.5,textvariable=self.targets[n],width=8,font=('Segoe UI',9)).grid(row=table_row,column=5,padx=6)
            ttk.Scale(table,from_=a.minimum,to=a.maximum,variable=self.targets[n]).grid(row=table_row,column=6,sticky='ew',padx=10)
        row=ttk.Frame(body);row.pack(fill='x',pady=9)
        ttk.Label(row,text='到达时间 / ms').pack(side='left')
        self.duration=tk.StringVar(value='2000')
        ttk.Spinbox(row,from_=20,to=9999,increment=100,textvariable=self.duration,width=8).pack(side='left',padx=7)
        self.move_button=ttk.Button(row,text='设置所选角度',command=self.set_angles);self.move_button.pack(side='left',padx=4)
        self.release_button=ttk.Button(row,text='所选轴卸力',command=self.release);self.release_button.pack(side='left',padx=4)
        self.drag_button=ttk.Button(row,text='模拟手动拖到目标',command=self.drag);self.drag_button.pack(side='left',padx=4)
        self.stop_button=tk.Button(row,text='停止当前动作 / Esc',bg='#b84443',fg='white',relief='flat',command=self.stop,padx=16,pady=8)
        self.stop_button.pack(side='right')
        ttk.Separator(body).pack(fill='x',pady=5)
        row=ttk.Frame(body);row.pack(fill='x',pady=7)
        self.record_mode=tk.StringVar(value='手动示教（卸力）')
        self.record_mode_box=ttk.Combobox(row,textvariable=self.record_mode,values=['手动示教（卸力）','控制动作录制'],state='readonly',width=19)
        self.record_mode_box.pack(side='left')
        self.record_mode_box.bind('<<ComboboxSelected>>',lambda event:self.update_controls())
        ttk.Label(row,text='采样 Hz').pack(side='left',padx=(10,4))
        self.rate=tk.StringVar(value='10')
        self.rate_box=ttk.Combobox(row,textvariable=self.rate,values=['5','10','20'],width=4,state='readonly');self.rate_box.pack(side='left')
        self.record_button=ttk.Button(row,text='① 开始录制',command=self.start_record,style='Accent.TButton');self.record_button.pack(side='left',padx=7)
        self.end_button=ttk.Button(row,text='② 结束录制',command=lambda:self.send('record_end'));self.end_button.pack(side='left',padx=3)
        self.load_button=ttk.Button(row,text='打开轨迹…',command=self.load);self.load_button.pack(side='right')
        self.save_button=ttk.Button(row,text='另存轨迹…',command=self.save);self.save_button.pack(side='right',padx=5)
        self.editor_button=ttk.Button(row,text='分步录入 / 剪辑',command=lambda:self.action(self.open_editor));self.editor_button.pack(side='right',padx=5)
        row=ttk.Frame(body);row.pack(fill='x',pady=(0,8))
        self.prepare_button=ttk.Button(row,text='③ 缓慢到首帧',command=self.prepare);self.prepare_button.pack(side='left')
        ttk.Label(row,text='回放倍率').pack(side='left',padx=(12,5))
        self.speed=tk.StringVar(value='0.5')
        self.speed_box=ttk.Combobox(row,textvariable=self.speed,values=['0.25','0.5','0.75','1.0','1.5','2.0'],width=5,state='readonly')
        self.speed_box.pack(side='left')
        self.speed_box.bind('<<ComboboxSelected>>',lambda event:self.reset_timeline())
        self.play_button=ttk.Button(row,text='④ 回放所选轴',command=self.play,style='Accent.TButton');self.play_button.pack(side='left',padx=8)
        self.take_info=tk.StringVar(value='尚无轨迹 · 录制会自动保存在 shadow_play/logs/bus_servo/takes')
        ttk.Label(row,textvariable=self.take_info,foreground='#536d7d').pack(side='right')
        timeline=ttk.Frame(body);timeline.pack(fill='x',pady=(0,5))
        timeline.columnconfigure(0,weight=1)
        self.timeline_text=tk.StringVar(value='回放进度 · 尚无轨迹')
        self.timeline_source=tk.StringVar(value='')
        self.timeline_segment=tk.StringVar(value='')
        ttk.Label(timeline,textvariable=self.timeline_text,font=('Microsoft YaHei UI',10,'bold')).grid(row=0,column=0,sticky='w')
        ttk.Label(timeline,textvariable=self.timeline_source,foreground='#526b7c').grid(row=0,column=1,sticky='e',padx=(10,0))
        self.progress_bar=ttk.Progressbar(timeline,mode='determinate',maximum=100,style='Playback.Horizontal.TProgressbar')
        self.progress_bar.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(5,3))
        self.segment_label=ttk.Label(timeline,textvariable=self.timeline_segment,foreground='#526b7c')
        self.canvas=tk.Canvas(body,height=160,bg='#ffffff',highlightthickness=1,highlightbackground='#dce4eb')
        self.canvas.bind('<Configure>',lambda e:(self.plot(),self.root.after_idle(self.resize_axis_table)))
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x')
        self.status=tk.StringVar(value='未连接 · 默认离线模拟。实物请核对对应镜像、接线与就绪状态；操作流程见右上角“使用说明”。')
        ttk.Label(footer,textvariable=self.status,wraplength=1100,foreground='#25566a').pack(anchor='w')
        ttk.Label(footer,text=f'记录的是电机轴反馈；连杆间隙和皮影弹性仍会影响复刻。{len(self.profile.layout.buses)}条总线并行，同一总线各轴依次发送，非硬件同时触发。',foreground='#627987',wraplength=1100).pack(anchor='w',pady=(5,0))
        self.canvas.pack(fill='both',expand=True,pady=(3,8))
        root.bind('<Escape>',lambda e:self.stop());root.protocol('WM_DELETE_WINDOW',self.close)
        root.bind('<Configure>',lambda event:root.after_idle(self.resize_axis_table) if event.widget is root else None)
        root.after(50,self.receive);self.update_controls()

    def resize_axis_table(self):
        # Preserve a readable chart on shorter screens; all axes remain accessible.
        available=self.axes_canvas.winfo_height()+self.canvas.winfo_height()-150
        height=max(100,min(self.axes_table.winfo_reqheight(),available))
        if abs(self.axes_canvas.winfo_height()-height)>2:
            self.axes_canvas.configure(height=height)

    def open_guide(self, section=None):
        import webbrowser
        path = ROOT/'docs/bus_servo_user_guide.html'
        if not path.is_file():
            raise FileNotFoundError('使用说明文件缺失：'+str(path))
        url=path.resolve().as_uri()+('#'+section if section else '')
        if not webbrowser.open(url):
            raise RuntimeError('未能打开浏览器，请手动打开说明文件：'+str(path))

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            self.port_box['values']=[p.device for p in list_ports.comports()]
        except ImportError:
            self.port_box['values']=[]

    def numbers(self):
        nums=[n for n,v in self.selected.items() if v.get()]
        if not nums:
            raise ValueError('至少选择一个舵机。')
        return nums

    def select(self, numbers):
        for n,v in self.selected.items():v.set(n in numbers)
        self.selection_changed()

    def selection_changed(self):
        nums=[n for n,v in self.selected.items() if v.get()]
        self.selection_text.set(f'已选 {len(nums)} 轴')
        self.commands.put(('select',nums));self.plot()
        if not self.playing:self.reset_timeline()
        self.update_controls()

    def feedback_ready(self, numbers):
        return bool(numbers) and self.connected and set(numbers) <= self.ready_axes

    def check_operator(self):
        if self.mode.get()!='离线模拟' and not self.attended.get():
            raise ValueError('请先确认现场条件。')

    def send(self, op, value=None):
        if self.busy or self.closing:return
        self.busy=True;self.update_controls();self.commands.put((op,value))

    def action(self, callback):
        try:callback()
        except Exception as exc:messagebox.showerror('操作未发送',str(exc),parent=self.root)

    def connect(self):
        if self.connected:
            self.send('disconnect');return
        self.send('connect',(self.profile,self.mode.get()=='离线模拟',self.port.get().strip()))

    def set_angles(self):
        def run():
            self.check_operator();nums=self.numbers()
            self.send('angles',(nums,{str(n):self.targets[n].get() for n in nums},int(self.duration.get())))
        self.action(run)

    def release(self):
        self.action(lambda:(self.check_operator(),self.send('release',self.numbers())))

    def drag(self):
        self.action(lambda:self.send('drag',{str(n):self.profile.axes[n].position(self.targets[n].get()) for n in self.numbers()}))

    def start_record(self):
        def run():
            self.check_operator();nums=self.numbers()
            self.live_samples=[];self.record=None;self.reset_timeline();self.plot()
            self.send('record_start',(nums,int(self.rate.get()),self.record_mode.get().startswith('手动')))
        self.action(run)

    def prepare(self):
        self.action(lambda:(self.check_operator(),self.send('prepare',(self.record,self.numbers()))))

    def play(self):
        def start():
            self.check_operator()
            if self.av_editor:self.av_editor.stop_preview()
            track=None
            if self.record and 'av_project' in self.record:
                from .audio import AudioTrack
                candidate=AudioTrack(self.record['av_project'])
                track=candidate if candidate.clips else None
            self.send('play',(self.record,self.numbers(),float(self.speed.get()),track))
        self.action(start)

    def stop(self):
        if self.av_editor:self.av_editor.stop_preview()
        if self.connected:
            self.stop_flag.set();self.status.set('正在停止当前动作或录制…')

    def load(self):
        path=filedialog.askopenfilename(parent=self.root,title='打开示教轨迹',filetypes=[('示教轨迹','*.json')])
        if not path:return
        def run():
            if Path(path).stat().st_size>64*1024*1024:raise ValueError('轨迹文件超过64MB。')
            record=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if record.get('schema')=='shadow.bus-av-project.v1':
                raise ValueError('这是联合编辑工程，请在“音频 / 轨迹剪辑”中打开。')
            if 'av_project' in record:
                from .av_editing import load_file
                record=load_file(path,self.profile)
            if record.get('schema')=='shadow.bus-edit.v1':
                raise ValueError('这是编辑工程，请在“分步录入 / 剪辑”窗口中选择“打开工程”。')
            validate_recording(record,self.profile)
            self.record=record;self.live_samples=[];self.select(record['selected']);self.describe_record(path);self.plot();self.update_controls()
        self.action(run)

    def save(self):
        if not self.record:return
        path=filedialog.asksaveasfilename(parent=self.root,title='另存轨迹（保留每次原始录制）',defaultextension='.json',initialfile='第一部分_'+datetime.now().strftime('%H%M%S')+'.json',filetypes=[('示教轨迹','*.json')])
        if path:
            if 'av_project' in self.record:
                from .av_editing import save_bundle
                self.action(lambda:save_bundle(path,self.record))
            else:self.action(lambda:save_recording(path,self.record))

    def describe_record(self,path):
        r=self.record; samples=r['samples'];seconds=samples[-1]['t']-samples[0]['t'] if len(samples)>1 else 0
        prefix='模拟' if r['source']=='simulation' else '实测'
        if r.get('schema')==MOTION_SCHEMA:
            prefix='编辑动作（'+('模拟素材' if r['source']=='simulation' else '实测素材')+'）'
        rate='' if r.get('schema')==MOTION_SCHEMA else f' / {r.get("measured_hz",0):.1f}Hz'
        self.take_info.set(f'{prefix} · {len(samples)} 帧 / {seconds:.1f}s'+rate+(' · 不完整' if not r['complete'] else ''))
        if 'av_project' in r:self.take_info.set(self.take_info.get()+' · 电脑音频联动')
        self.reset_timeline()
        if path:self.status.set('轨迹已保存：'+str(path))

    def open_editor(self):
        if self.editor:
            self.editor.window.lift(); return
        from .editor_gui import EditorWindow
        self.editor = EditorWindow(self, ROOT/'logs/bus_servo/edits')

    def open_av_editor(self):
        if self.av_editor:self.av_editor.window.lift();return
        from .av_gui import AVWindow
        self.av_editor=AVWindow(self,ROOT/'logs/bus_servo/av_edits')

    def configure(self):
        if self.connected:return
        win=tk.Toplevel(self.root);win.title('总线ID与角度配置');win.geometry('880x590')
        ttk.Label(win,text='实物每条总线内ID必须唯一；此窗口保存电脑配置，不向舵机写ID。',wraplength=820).pack(pady=12)
        table=ttk.Frame(win,padding=8);table.pack(fill='x')
        fields=('id','span_deg','min_deg','max_deg','max_speed_deg_s');titles=('轴','总线ID','规格 / °','最小 / °','最大 / °','最大速度 / °/s')
        for c,title in enumerate(titles):ttk.Label(table,text=title).grid(row=0,column=c,padx=8,pady=5)
        values=[]
        for i,row in enumerate(self.profile.data['axes'],1):
            ttk.Label(table,text=f'{row["number"]}号').grid(row=i,column=0);v={}
            for c,key in enumerate(fields,1):
                v[key]=tk.StringVar(value=str(row[key]));ttk.Entry(table,textvariable=v[key],width=12).grid(row=i,column=c,padx=8,pady=5)
            values.append(v)
        ttk.Label(win,text='修改后另存配置，重新打开程序使用；板端需安装同一份配置。实机就绪标记由换装和联调结果确认。',wraplength=820).pack(pady=12)
        def save_profile():
            def run():
                data=json.loads(json.dumps(self.profile.data))
                for row,v in zip(data['axes'],values):
                    for key in fields:row[key]=(int if key in ('id','span_deg') else float)(v[key].get())
                for key in ('hardware_verified','electrical_3v3_verified','mechanical_limits_verified'):data[key]=False
                Profile(data)
                path=filedialog.asksaveasfilename(parent=win,defaultextension='.json',initialfile='bus_servo_custom.json')
                if path:
                    with Path(path).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
                    messagebox.showinfo('已保存','配置已保存。下次启动可用 --profile 指定该文件。',parent=win)
            self.action(run)
        ttk.Button(win,text='另存配置…',command=save_profile).pack(pady=5)

    def reset_timeline(self):
        if self.playing:return
        if not self.record:
            self.show_progress(None);return
        plan=None
        try:
            plan=playback_plan(self.record,self.profile,self.numbers(),float(self.speed.get()))
        except ValueError:
            # Invalid/incomplete material remains visible for inspection.
            # Only an explicit play request reports a validation error.
            pass
        self.show_progress(PlaybackTimeline(self.record,float(self.speed.get()),plan=plan).snapshot())

    def show_progress(self, progress):
        self.playback_progress = progress
        if progress is None:
            self.timeline_text.set('回放进度 · 尚无轨迹')
            self.timeline_source.set('')
            self.timeline_segment.set('')
            self.segment_label.grid_remove()
            self.progress_bar['value']=0
        else:
            labels={'ready':'待回放','playing':'回放中','checking':'核对末帧',
                    'completed':'已完成','stopped':'已停止','failed':'已中止','disconnected':'已断开'}
            p=progress
            estimate='' if p['state']=='completed' else '预计 '
            self.timeline_text.set(f'{labels[p["state"]]}  {format_time(p["elapsed_s"])} / {estimate}{format_time(p["duration_s"])}'
                                   f'  ·  {p["fraction"]*100:.0f}%  ·  预计剩余 {format_time(p["duration_s"]-p["elapsed_s"])}')
            adjusted='（快段已放慢）' if p.get('retimed_intervals') else ''
            self.timeline_source.set(f'{p["speed"]:g}×{adjusted}  ·  轨迹 {format_time(p["source_s"])} / {format_time(p["source_duration_s"])}')
            segment=p['segment']
            delay=p.get('communication_delay_s',0)
            if delay>=.05:segment+=(('  ·  ' if segment else '')+f'通信 / 到达顺延 {delay:.1f} 秒')
            if len(segment)>70:segment=segment[:67]+'…'
            self.timeline_segment.set(segment)
            if segment:self.segment_label.grid(row=2,column=0,columnspan=2,sticky='w')
            else:self.segment_label.grid_remove()
            self.progress_bar['value']=p['fraction']*100
        self.draw_playhead()

    def finish_timeline(self, state):
        if self.playback_progress and self.playback_progress['state'] in ('playing','checking'):
            self.show_progress(dict(self.playback_progress,state=state))

    def draw_playhead(self):
        c=self.canvas;c.delete('playhead')
        if not self.plot_bounds or not self.playback_progress or self.recording:return
        left,right,top,bottom,duration=self.plot_bounds
        seconds=min(duration,self.playback_progress['source_s'])
        x=left+(right-left)*seconds/duration
        c.create_line(x,top,x,bottom,fill='#c44343',width=2,tags='playhead')
        c.create_polygon(x-5,top,x+5,top,x,top+7,fill='#c44343',outline='',tags='playhead')
        label=c.create_text(min(right-30,max(left+30,x)),top+17,text=format_time(seconds),
                            fill='#a52c2c',font=('Segoe UI',9,'bold'),tags='playhead')
        bounds=c.bbox(label)
        if bounds:
            box=c.create_rectangle(bounds[0]-3,bounds[1]-1,bounds[2]+3,bounds[3]+1,
                                   fill='white',outline='',tags='playhead')
            c.tag_lower(box,label)

    def plot(self):
        c=self.canvas;c.delete('all');w=max(c.winfo_width(),300);h=max(c.winfo_height(),60)
        self.plot_bounds=None
        left,right,top,bottom=50,w-22,16,h-28
        span=max(a.span for a in self.profile.axes.values())
        for deg in range(0,span+1,90):
            y=bottom-(bottom-top)*deg/span;c.create_line(left,y,right,y,fill='#edf1f5');c.create_text(left-9,y,text=str(deg),anchor='e',fill='#7c8b9b',font=('Segoe UI',9))
        samples=self.live_samples if self.recording else (self.record['samples'] if self.record else [])
        if not samples:
            c.create_text(w/2,h/2,text='运动轨迹将在这里显示  ·  横轴时间 / 纵轴角度',fill='#8b99a8',font=('Microsoft YaHei UI',11));return
        origin=samples[0]['t'];end=max(samples[-1]['t']-origin,.001)
        self.plot_bounds=(left,right,top,bottom,end)
        for step in range(5):
            seconds=end*step/4;x=left+(right-left)*step/4
            c.create_line(x,top,x,bottom,fill='#edf1f5')
            c.create_text(x,bottom+16,text=format_time(seconds),fill='#76899a',
                          anchor='w' if step==0 else ('e' if step==4 else 'center'))
        for n,v in self.selected.items():
            if not v.get():continue
            key=str(n);points=[]
            drawn=samples[::max(1,len(samples)//1200)]
            if drawn[-1] is not samples[-1]:drawn=drawn+[samples[-1]]
            for sample in drawn:
                if key in sample['positions']:
                    points.extend([left+(right-left)*(sample['t']-origin)/end,bottom-(bottom-top)*self.profile.axes[n].degrees(sample['positions'][key])/span])
            if len(points)>=4:c.create_line(*points,fill=COLORS[n-1],width=2)
        self.draw_playhead()

    def update_controls(self):
        idle=self.connected and not self.busy and not self.recording and not self.playing
        ready=self.feedback_ready([n for n,v in self.selected.items() if v.get()])
        motion=ready and self.motion_allowed
        def state(widget,enabled):widget.configure(state='normal' if enabled else 'disabled')
        state(self.connect_button,not self.busy and not self.recording and not self.playing)
        self.connect_button.configure(text='断开' if self.connected else '连接板子 / 模拟')
        state(self.probe_button,idle and self.mode.get()!='离线模拟')
        self.mode_box.configure(state='disabled' if self.connected or self.busy else 'readonly')
        for box in (self.record_mode_box,self.rate_box):box.configure(state='disabled' if self.recording or self.playing or self.busy else 'readonly')
        self.speed_box.configure(state='disabled' if self.playing or self.busy else 'readonly')
        state(self.port_box,not self.connected and not self.busy);state(self.configure_button,not self.connected and not self.busy)
        state(self.move_button,motion and not self.busy and not self.playing and (not self.recording or self.record_mode.get()=='控制动作录制'))
        state(self.release_button,idle and ready and self.release_allowed)
        state(self.record_button,idle and ready and (self.record_mode.get()=='控制动作录制' or self.release_allowed))
        state(self.end_button,self.recording and not self.busy)
        state(self.drag_button,self.connected and not self.busy and not self.playing and self.mode.get()=='离线模拟')
        for b in [self.prepare_button,self.play_button]:state(b,idle and motion and self.record is not None and self.record.get('complete') is True)
        state(self.save_button,self.record is not None and not self.recording)
        state(self.load_button,not self.recording and not self.playing and not self.busy)
        state(self.editor_button,not self.recording and not self.playing and not self.busy)
        state(self.av_button,not self.recording and not self.playing and not self.busy)
        # Controlled recording keeps its initial acquisition set. The operator
        # may independently select a smaller/different group to send targets to.
        can_select=not self.playing and not self.busy and (not self.recording or self.record_mode.get()=='控制动作录制')
        for b in self.checks+self.selection_buttons:state(b,can_select)
        if self.editor: self.editor.sync_controls()

    def receive(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='closed':self.root.destroy();return
                if kind=='connected':
                    self.connected=True;self.busy=False
                    self.motion_allowed=value['motion_allowed']
                    self.release_allowed=value['release_allowed']
                    self.ready_axes=set(self.profile.axes) if value['simulation'] else set()
                    self.status.set('离线模拟已连接；模拟数据不能用于实机回放。' if value['simulation'] else
                                    '板子已连接 · 舵机尚未检测（可保持断电）。供电后点“检测所选舵机”；连接不发送舵机指令。')
                    for text in self.feedback.values():text.set('未检测')
                elif kind=='servos_ready':
                    self.ready_axes=set(value)
                    access = '。' if self.motion_allowed else ('。可卸力、手动录制；设角与回放尚未开放。' if self.release_allowed else '。当前为只读调试。')
                    self.status.set('板子已连接 · 舵机反馈通过：'+', '.join(map(str,value))+access)
                elif kind=='servos_unavailable':
                    self.finish_timeline('failed')
                    self.ready_axes.clear();self.busy=self.recording=self.playing=False
                    for text in self.feedback.values():text.set('无有效反馈')
                    if self.editor:self.editor.cancel_capture()
                    self.status.set(value)
                elif kind=='disconnected':
                    self.finish_timeline('disconnected')
                    self.ready_axes.clear();self.motion_allowed=self.release_allowed=False
                    self.connected=False;self.busy=False;self.status.set('已断开。')
                    for value in self.feedback.values():value.set('未连接')
                elif kind=='feedback':
                    for n,text in self.feedback.items():
                        text.set(f'{self.profile.axes[n].degrees(value[n]["p"]):.2f}°' if n in value else ('未采样' if n in self.ready_axes else '未检测'))
                elif kind=='pose':
                    if self.editor: self.editor.accept_pose(value)
                elif kind=='capture_error':
                    if self.editor:
                        self.editor.cancel_capture(); self.editor.status.set('姿势未录入：'+value)
                    self.status.set('姿势未录入：'+value)
                elif kind=='recording':
                    self.recording=True
                    prefix='正在录制模拟反馈。' if self.mode.get()=='离线模拟' else '正在录制实际反馈。'
                    self.status.set(prefix+('所选轴已回复卸力命令，扶稳机构后手动表演。' if value else '录制轴已固定；可重新勾选控制轴并设置角度。'))
                elif kind=='sample':
                    self.live_samples.append(value);self.take_info.set(f'录制中 · {len(self.live_samples)} 帧 / {value["t"]:.1f}s');self.plot()
                elif kind=='record':self.record,path=value;self.describe_record(path);self.plot()
                elif kind=='prepared':self.reset_timeline()
                elif kind=='playing':
                    self.playing=True;self.show_progress(value)
                    adjusted=f'其中 {value["retimed_intervals"]} 段已自动放慢；' if value.get('retimed_intervals') else ''
                    self.status.set('正在回放所选轴，小于等于0.5°的微小抖动已忽略；'+adjusted+'播放时间随通信耗时顺延，Esc停止。')
                elif kind=='playback_rejected':
                    self.status.set('回放未开始：'+value+' 板子连接保留。')
                elif kind=='playback_progress':self.show_progress(value)
                elif kind=='idle':
                    self.busy=self.recording=self.playing=False;self.plot()
                    if self.editor: self.editor.cancel_capture()
                elif kind=='command_done':self.busy=False
                elif kind=='message':self.status.set(value)
                elif kind=='stopped':
                    self.finish_timeline('stopped')
                    self.status.set('当前动作/录制已停止；需要松开舵机时，请点击“所选轴卸力”。本次停止没有发送卸力命令。' if isinstance(value,dict) and value.get('state')=='no_motion_lease' else
                                    '已发出卸力请求；实物总线广播没有逐轴确认，不代表已切断电源。')
                elif kind=='error':
                    self.finish_timeline('failed')
                    was_connected = self.connected
                    self.connected=self.busy=self.recording=self.playing=False
                    self.ready_axes.clear();self.motion_allowed=self.release_allowed=False
                    if self.editor: self.editor.cancel_capture()
                    for text in self.feedback.values():text.set('反馈失效')
                    if was_connected:
                        self.status.set('已中止并断开：'+value+' 实物停止状态未获独立确认，请检查。')
                    else:
                        self.status.set('连接失败：'+value)
                        if not self.closing:
                            messagebox.showerror('连接未完成', value, parent=self.root)
                    self.plot()
                self.update_controls()
        except queue.Empty:pass
        self.root.after(50,self.receive)

    def close(self):
        if self.closing:return
        if self.av_editor:
            if self.av_editor.busy:
                self.stop_flag.set();self.status.set('音频文件正在处理，完成后请再关闭。');return
            self.av_editor.stop_preview()
            try:self.av_editor.autosave()
            except Exception as exc:
                self.stop_flag.set();messagebox.showerror('联合编辑草稿尚未保存',str(exc),parent=self.root);return
        if self.editor:
            try:
                self.editor.autosave()
            except Exception as exc:
                self.stop_flag.set()
                messagebox.showerror('编辑草稿尚未保存', str(exc), parent=self.root)
                return
        self.closing=True;self.status.set('正在停止并保存未完成记录…')
        self.commands.put(('shutdown',None));self.stop_flag.set()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=ROOT/'config/bus_servo.json')
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--av-editor',action='store_true')
    args=parser.parse_args();root=tk.Tk();app=App(root,args.profile)
    if args.av_editor:app.open_av_editor()
    if args.smoke_test:
        app.open_editor()
        root.after(300,app.close)
    root.mainloop()


if __name__=='__main__':main()
