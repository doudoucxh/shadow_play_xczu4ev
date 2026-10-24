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
from .model import Profile, save_recording, validate_recording
from .session import TeachingSession
from .transport import RemoteDevice

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#26a69a', '#5477d4', '#db9239', '#d85c74', '#8a69d2', '#639d49', '#d16635', '#4d9aba', '#b477b0', '#a19a35']


class Worker(threading.Thread):
    def __init__(self, commands, events, stop_flag):
        super().__init__(daemon=True)
        self.commands, self.events, self.stop_flag = commands, events, stop_flag
        self.session = None
        self.shutting_down = False
        self.numbers = list(range(1,11))

    def emit(self, kind, value=None):
        self.events.put((kind, value))

    def release(self):
        if self.session:
            try:
                self.session.close()
            finally:
                self.session = None

    def run(self):
        while True:
            try:
                if self.stop_flag.is_set():
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
                        stopped = self.session.stop()
                        if self.session.record:
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
                    device = SimulationDevice(profile) if simulation else RemoteDevice(profile, port)
                    try:
                        self.session = TeachingSession(profile, device, ROOT/'logs/bus_servo/takes')
                    except BaseException:
                        device.close(); raise
                    self.emit('connected', simulation)
                elif op == 'select':
                    self.numbers = value or list(range(1,11))
                elif op and self.session:
                    s = self.session
                    if op == 'angles':
                        s.set_angles(*value); self.emit('message', '角度指令已发送，实际位置以反馈为准。')
                    elif op == 'release':
                        s.device.release(value); self.emit('message', '所选轴卸力完成；请扶稳机构后手动操作。')
                    elif op == 'record_start':
                        s.start_recording(*value); self.emit('recording', value[2])
                    elif op == 'record_end':
                        path = s.finish_recording(); self.emit('record', (s.record, path)); self.emit('idle')
                    elif op == 'prepare':
                        seconds = s.prepare_first(*value)
                        self.emit('message', f'已发送到首帧指令，预计至少 {seconds:.1f} 秒；回放时会重新读位置。')
                    elif op == 'play':
                        s.start_playback(*value); self.emit('playing')
                    elif op == 'drag':
                        if not s.device.simulation:
                            raise RuntimeError('模拟拖动仅用于离线模式。')
                        s.device.drag(value)
                    self.emit('command_done')
                if self.session:
                    rows, finished = self.session.tick(self.numbers)
                    if rows:
                        self.emit('feedback', rows)
                        if self.session.recording:
                            self.emit('sample', self.session.record['samples'][-1])
                    if finished:
                        self.emit('idle'); self.emit('message', '回放已结束，末帧位置反馈通过；保持状态，点停止可卸力。')
            except Exception as exc:
                recovery = None
                try:
                    if self.session:
                        self.session.stop(reason=str(exc))
                        if self.session.record:
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
        self.record = None
        self.live_samples = []
        root.title('皮影 · 总线舵机示教工作台')
        root.geometry('1180x850'); root.minsize(1030, 790)
        root.configure(bg='#eef2f5')
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#eef2f5')
        style.configure('TLabel', background='#eef2f5', foreground='#203246',font=('Microsoft YaHei UI',9))
        style.configure('TButton', padding=(10,4))
        style.configure('Accent.TButton', background='#216c79', foreground='white')
        body = ttk.Frame(root, padding=18); body.pack(fill='both', expand=True)
        header = ttk.Frame(body); header.pack(fill='x')
        ttk.Label(header, text='皮影示教工作台', font=('Microsoft YaHei UI',22,'bold')).pack(side='left')
        ttk.Label(header, text='人物 6 轴 / E14     老虎 4 轴 / E15', foreground='#59728a').pack(side='right', pady=10)
        ttk.Label(body, text='先用手演一遍，记录舵机实际位置，再按时间重现动作。', foreground='#526b7c').pack(anchor='w', pady=(2,12))
        row = ttk.Frame(body); row.pack(fill='x', pady=(0,10))
        self.mode = tk.StringVar(value='离线模拟')
        self.mode_box = ttk.Combobox(row, textvariable=self.mode, values=['离线模拟','实物 / PS串口'], state='readonly', width=18)
        self.mode_box.pack(side='left')
        ttk.Label(row,text='PS串口').pack(side='left',padx=(16,5))
        self.port = tk.StringVar(value='COM19')
        self.port_box = ttk.Combobox(row, textvariable=self.port, width=12)
        self.port_box.pack(side='left')
        self.refresh_ports()
        ttk.Button(row,text='刷新',command=self.refresh_ports).pack(side='left',padx=5)
        self.connect_button = ttk.Button(row,text='连接',command=self.connect,style='Accent.TButton')
        self.connect_button.pack(side='left',padx=7)
        self.configure_button = ttk.Button(row,text='ID / 角度与限位配置',command=self.configure)
        self.configure_button.pack(side='right')
        self.attended = tk.BooleanVar(value=False)
        self.attend_box = ttk.Checkbutton(body,text='实物操作：我在现场可断电，已扶稳需卸力的机构，并检查运动空间。',variable=self.attended)
        self.attend_box.pack(anchor='w',pady=(0,8))
        row = ttk.Frame(body); row.pack(fill='x',pady=(0,4))
        self.selection_buttons=[]
        for label,nums in [('全选',range(1,11)),('人物',range(1,7)),('老虎',range(7,11)),('清空',[])]:
            b=ttk.Button(row,text=label,command=lambda nums=list(nums):self.select(nums));b.pack(side='left',padx=(0,5));self.selection_buttons.append(b)
        self.selection_text=tk.StringVar(value='已选 10 轴')
        ttk.Label(row,textvariable=self.selection_text).pack(side='right')
        table=ttk.Frame(body);table.pack(fill='x',pady=4)
        for col,title in enumerate(['选择','编号 / 总线ID','控制部位','总线口','实际角度','目标角度','目标调整 / °','软件范围']):
            ttk.Label(table,text=title,font=('Microsoft YaHei UI',10,'bold')).grid(row=0,column=col,sticky='w',padx=6,pady=6)
        table.columnconfigure(6,weight=1)
        self.selected={};self.targets={};self.feedback={};self.checks=[]
        for n,a in self.profile.axes.items():
            self.selected[n]=tk.BooleanVar(value=True)
            self.targets[n]=tk.DoubleVar(value=a.span/2)
            self.feedback[n]=tk.StringVar(value='—')
            box=ttk.Checkbutton(table,variable=self.selected[n],command=self.selection_changed);box.grid(row=n,column=0);self.checks.append(box)
            for col,text in [(1,f'{n:02d} / {a.ident:03d}'),(2,a.label),(3,'人物 · E14' if n<=6 else '老虎 · E15'),(7,f'{a.minimum:g}–{a.maximum:g}°')]:
                ttk.Label(table,text=text).grid(row=n,column=col,sticky='w',padx=6,pady=1)
            ttk.Label(table,textvariable=self.feedback[n],foreground=COLORS[n-1],width=11).grid(row=n,column=4,sticky='w',padx=6)
            ttk.Spinbox(table,from_=a.minimum,to=a.maximum,increment=.5,textvariable=self.targets[n],width=8,font=('Segoe UI',9)).grid(row=n,column=5,padx=6)
            ttk.Scale(table,from_=a.minimum,to=a.maximum,variable=self.targets[n]).grid(row=n,column=6,sticky='ew',padx=10)
        row=ttk.Frame(body);row.pack(fill='x',pady=9)
        ttk.Label(row,text='到达时间 / ms').pack(side='left')
        self.duration=tk.StringVar(value='2000')
        ttk.Spinbox(row,from_=20,to=9999,increment=100,textvariable=self.duration,width=8).pack(side='left',padx=7)
        self.move_button=ttk.Button(row,text='设置所选角度',command=self.set_angles);self.move_button.pack(side='left',padx=4)
        self.release_button=ttk.Button(row,text='所选轴卸力',command=self.release);self.release_button.pack(side='left',padx=4)
        self.drag_button=ttk.Button(row,text='模拟手动拖到目标',command=self.drag);self.drag_button.pack(side='left',padx=4)
        self.stop_button=tk.Button(row,text='停止并卸力 / Esc',bg='#b84443',fg='white',relief='flat',command=self.stop,padx=16,pady=8)
        self.stop_button.pack(side='right')
        ttk.Separator(body).pack(fill='x',pady=5)
        row=ttk.Frame(body);row.pack(fill='x',pady=7)
        self.record_mode=tk.StringVar(value='手动示教（卸力）')
        self.record_mode_box=ttk.Combobox(row,textvariable=self.record_mode,values=['手动示教（卸力）','控制动作录制'],state='readonly',width=19)
        self.record_mode_box.pack(side='left')
        ttk.Label(row,text='采样 Hz').pack(side='left',padx=(10,4))
        self.rate=tk.StringVar(value='10')
        self.rate_box=ttk.Combobox(row,textvariable=self.rate,values=['5','10','20'],width=4,state='readonly');self.rate_box.pack(side='left')
        self.record_button=ttk.Button(row,text='① 开始录制',command=self.start_record,style='Accent.TButton');self.record_button.pack(side='left',padx=7)
        self.end_button=ttk.Button(row,text='② 结束录制',command=lambda:self.send('record_end'));self.end_button.pack(side='left',padx=3)
        self.load_button=ttk.Button(row,text='打开轨迹…',command=self.load);self.load_button.pack(side='right')
        self.save_button=ttk.Button(row,text='另存轨迹…',command=self.save);self.save_button.pack(side='right',padx=5)
        row=ttk.Frame(body);row.pack(fill='x',pady=(0,8))
        self.prepare_button=ttk.Button(row,text='③ 缓慢到首帧',command=self.prepare);self.prepare_button.pack(side='left')
        ttk.Label(row,text='回放倍率').pack(side='left',padx=(12,5))
        self.speed=tk.StringVar(value='0.5')
        ttk.Combobox(row,textvariable=self.speed,values=['0.25','0.5','0.75','1.0','1.5','2.0'],width=5,state='readonly').pack(side='left')
        self.play_button=ttk.Button(row,text='④ 回放所选轴',command=self.play,style='Accent.TButton');self.play_button.pack(side='left',padx=8)
        self.take_info=tk.StringVar(value='尚无轨迹 · 录制会自动保存在 shadow_play/logs/bus_servo/takes')
        ttk.Label(row,textvariable=self.take_info,foreground='#536d7d').pack(side='right')
        self.canvas=tk.Canvas(body,height=160,bg='#ffffff',highlightthickness=1,highlightbackground='#dce4eb')
        self.canvas.bind('<Configure>',lambda e:self.plot())
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x')
        self.status=tk.StringVar(value='未连接 · 默认离线模拟。实物待换装、回传电平确认、逐个编号和限位标定。')
        ttk.Label(footer,textvariable=self.status,wraplength=1100,foreground='#25566a').pack(anchor='w')
        ttk.Label(footer,text='记录的是电机轴反馈；连杆间隙和皮影弹性仍会影响复刻。两总线并行，同一总线各轴依次发送，非硬件同时触发。',foreground='#627987',wraplength=1100).pack(anchor='w',pady=(5,0))
        self.canvas.pack(fill='both',expand=True,pady=(3,8))
        root.bind('<Escape>',lambda e:self.stop());root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(50,self.receive);self.update_controls()

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
            self.live_samples=[];self.record=None;self.plot()
            self.send('record_start',(nums,int(self.rate.get()),self.record_mode.get().startswith('手动')))
        self.action(run)

    def prepare(self):
        self.action(lambda:(self.check_operator(),self.send('prepare',(self.record,self.numbers()))))

    def play(self):
        self.action(lambda:(self.check_operator(),self.send('play',(self.record,self.numbers(),float(self.speed.get())))))

    def stop(self):
        if self.connected:
            self.stop_flag.set();self.status.set('正在请求卸力；实物异常时请现场断电。')

    def load(self):
        path=filedialog.askopenfilename(parent=self.root,title='打开示教轨迹',filetypes=[('示教轨迹','*.json')])
        if not path:return
        def run():
            if Path(path).stat().st_size>64*1024*1024:raise ValueError('轨迹文件超过64MB。')
            record=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            validate_recording(record,self.profile)
            self.record=record;self.live_samples=[];self.select(record['selected']);self.describe_record(path);self.plot();self.update_controls()
        self.action(run)

    def save(self):
        if not self.record:return
        path=filedialog.asksaveasfilename(parent=self.root,title='另存轨迹（保留每次原始录制）',defaultextension='.json',initialfile='第一部分_'+datetime.now().strftime('%H%M%S')+'.json',filetypes=[('示教轨迹','*.json')])
        if path:self.action(lambda:save_recording(path,self.record))

    def describe_record(self,path):
        r=self.record; samples=r['samples'];seconds=samples[-1]['t']-samples[0]['t'] if len(samples)>1 else 0
        prefix='模拟' if r['source']=='simulation' else '实测'
        self.take_info.set(f'{prefix} · {len(samples)} 帧 / {seconds:.1f}s / {r.get("measured_hz",0):.1f}Hz'+(' · 不完整' if not r['complete'] else ''))
        if path:self.status.set('轨迹已保存：'+str(path))

    def configure(self):
        if self.connected:return
        win=tk.Toplevel(self.root);win.title('总线ID与角度配置');win.geometry('880x590')
        ttk.Label(win,text='实物每条总线内ID必须唯一；此窗口保存电脑配置，不向舵机写ID。',wraplength=820).pack(pady=12)
        table=ttk.Frame(win,padding=8);table.pack(fill='x')
        fields=('id','span_deg','min_deg','max_deg','max_speed_deg_s');titles=('轴','总线ID','规格 / °','最小 / °','最大 / °','最大速度 / °/s')
        for c,title in enumerate(titles):ttk.Label(table,text=title).grid(row=0,column=c,padx=8,pady=5)
        values=[]
        for i,row in enumerate(self.profile.data['axes'],1):
            ttk.Label(table,text=f'{i}号').grid(row=i,column=0);v={}
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

    def plot(self):
        c=self.canvas;c.delete('all');w=max(c.winfo_width(),300);h=max(c.winfo_height(),60)
        left,right,top,bottom=50,w-22,16,h-28
        span=max(a.span for a in self.profile.axes.values())
        for deg in range(0,span+1,90):
            y=bottom-(bottom-top)*deg/span;c.create_line(left,y,right,y,fill='#edf1f5');c.create_text(left-9,y,text=str(deg),anchor='e',fill='#7c8b9b',font=('Segoe UI',9))
        samples=self.live_samples if self.recording else (self.record['samples'] if self.record else [])
        if not samples:
            c.create_text(w/2,h/2,text='运动轨迹将在这里显示  ·  横轴时间 / 纵轴角度',fill='#8b99a8',font=('Microsoft YaHei UI',11));return
        end=max(samples[-1]['t'],1)
        for n,v in self.selected.items():
            if not v.get():continue
            key=str(n);points=[]
            for sample in samples[::max(1,len(samples)//1200)]:
                if key in sample['positions']:
                    points.extend([left+(right-left)*sample['t']/end,bottom-(bottom-top)*self.profile.axes[n].degrees(sample['positions'][key])/span])
            if len(points)>=4:c.create_line(*points,fill=COLORS[n-1],width=2)
        c.create_text(left,bottom+16,text='0s',fill='#76899a');c.create_text(right,bottom+16,text=f'{end:.1f}s',fill='#76899a',anchor='e')

    def update_controls(self):
        idle=self.connected and not self.busy and not self.recording and not self.playing
        def state(widget,enabled):widget.configure(state='normal' if enabled else 'disabled')
        state(self.connect_button,not self.busy and not self.recording and not self.playing)
        self.connect_button.configure(text='断开' if self.connected else '连接')
        self.mode_box.configure(state='disabled' if self.connected or self.busy else 'readonly')
        for box in (self.record_mode_box,self.rate_box):box.configure(state='disabled' if self.recording or self.playing or self.busy else 'readonly')
        state(self.port_box,not self.connected and not self.busy);state(self.configure_button,not self.connected and not self.busy)
        state(self.move_button,self.connected and not self.busy and not self.playing and (not self.recording or self.record_mode.get()=='控制动作录制'))
        state(self.release_button,idle);state(self.record_button,idle)
        state(self.end_button,self.recording and not self.busy)
        state(self.drag_button,self.connected and not self.busy and self.mode.get()=='离线模拟' and self.recording)
        for b in [self.prepare_button,self.play_button]:state(b,idle and self.record is not None and self.record.get('complete') is True)
        state(self.save_button,self.record is not None and not self.recording)
        state(self.load_button,not self.recording and not self.playing and not self.busy)
        # Controlled recording keeps its initial acquisition set. The operator
        # may independently select a smaller/different group to send targets to.
        can_select=not self.playing and not self.busy and (not self.recording or self.record_mode.get()=='控制动作录制')
        for b in self.checks+self.selection_buttons:state(b,can_select)

    def receive(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='closed':self.root.destroy();return
                if kind=='connected':
                    self.connected=True;self.busy=False
                    self.status.set('离线模拟已连接；模拟数据不能用于实机回放。' if value else '实物只读连接完成，未发送角度。')
                elif kind=='disconnected':
                    self.connected=False;self.busy=False;self.status.set('已断开。')
                    for value in self.feedback.values():value.set('未连接')
                elif kind=='feedback':
                    for n,text in self.feedback.items():
                        text.set(f'{self.profile.axes[n].degrees(value[n]["p"]):.2f}°' if n in value else '未采样')
                elif kind=='recording':
                    self.recording=True
                    prefix='正在录制模拟反馈。' if self.mode.get()=='离线模拟' else '正在录制实际反馈。'
                    self.status.set(prefix+('所选轴已卸力，可手动表演。' if value else '录制轴已固定；可重新勾选控制轴并设置角度。'))
                elif kind=='sample':
                    self.live_samples.append(value);self.take_info.set(f'录制中 · {len(self.live_samples)} 帧 / {value["t"]:.1f}s');self.plot()
                elif kind=='record':self.record,path=value;self.describe_record(path);self.plot()
                elif kind=='playing':self.playing=True;self.status.set('正在回放所选轴，Esc停止。')
                elif kind=='idle':self.busy=self.recording=self.playing=False;self.plot()
                elif kind=='command_done':self.busy=False
                elif kind=='message':self.status.set(value)
                elif kind=='stopped':self.status.set('已发出卸力请求；实物总线广播没有逐轴确认，不代表已切断电源。')
                elif kind=='error':
                    self.connected=self.busy=self.recording=self.playing=False
                    for text in self.feedback.values():text.set('反馈失效')
                    self.status.set('已中止并断开：'+value+' 实物停止状态未获独立确认，请检查。')
                    self.plot()
                self.update_controls()
        except queue.Empty:pass
        self.root.after(50,self.receive)

    def close(self):
        if self.closing:return
        self.closing=True;self.status.set('正在停止并保存未完成记录…')
        self.commands.put(('shutdown',None));self.stop_flag.set()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=ROOT/'config/bus_servo.json')
    parser.add_argument('--smoke-test',action='store_true')
    args=parser.parse_args();root=tk.Tk();app=App(root,args.profile)
    if args.smoke_test:
        root.after(300,app.close)
    root.mainloop()


if __name__=='__main__':main()
