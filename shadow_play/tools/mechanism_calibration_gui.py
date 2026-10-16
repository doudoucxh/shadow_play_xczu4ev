"""Explicit manual calibration UI. Default simulation; no motion on open/load."""
import argparse,copy,json,queue,threading,time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
import mechanism_calibration_model as model
from mechanism_rail_adapter import UnconfiguredRailDriver,simulated_relative,finite_number
from servo_manual_session import angle_to_pulse,pulse_to_angle,validate_pulse

ROOT=Path(__file__).resolve().parents[1]
PINS=('D14','D15','F13','G13','G14','G15','J14','E13','E14','E15')
AXES=['servo'+str(i) for i in range(1,11)]+['rail1','rail2']
SETUP=json.loads((ROOT/'config/manual_mechanism_setup.json').read_text(encoding='utf-8'))

class SerialWorker(threading.Thread):
    def __init__(self,commands,events):
        super().__init__(daemon=True);self.commands=commands;self.events=events;self.session=None
    def run(self):
        poll=0
        while True:
            try:
                try:operation,value=self.commands.get(timeout=.1)
                except queue.Empty:operation,value=None,None
                if operation in ('disconnect','shutdown'):
                    if self.session:self.session.close();self.session=None
                    self.events.put(('closed' if operation=='shutdown' else 'disconnected',None))
                    if operation=='shutdown':return
                elif operation=='connect':
                    from mechanism_servo_session import MechanismServoSession
                    folder=ROOT/'logs/mechanism_calibration';folder.mkdir(parents=True,exist_ok=True)
                    self.session=MechanismServoSession(value,folder/('serial_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.jsonl'))
                    self.events.put(('connected',self.session.status()))
                elif operation=='move':self.events.put(('state',self.session.move(*value,True)))
                elif operation=='stop':self.events.put(('state',self.session.stop()))
                if self.session and time.monotonic()>poll:
                    self.events.put(('snapshot',self.session.status()));poll=time.monotonic()+.5
            except Exception as error:
                try:
                    if self.session:self.session.close()
                except Exception:pass
                self.session=None;self.events.put(('error',str(error)))

class App:
    def __init__(self,root):
        self.root=root;root.title('皮影机构 · 舵机/双丝杆手动标定');root.geometry('1180x860');root.minsize(1080,780)
        root.option_add('*Font',('Microsoft YaHei UI',10))
        self.commands=queue.Queue();self.events=queue.Queue();self.worker=SerialWorker(self.commands,self.events);self.worker.start()
        self.connected=False;self.busy=False;self.closing=False;self.driver=UnconfiguredRailDriver()
        self.mode=tk.StringVar(value='模拟（不接硬件）');self.port=tk.StringVar(value='COM3')
        self.geometry=tk.StringVar(value='结构-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        self.project=model.new_project(self.geometry.get());self.snapshot=model.new_snapshot()
        self.board=None;self.path=None;self.status=tk.StringVar(value='模拟模式 · 打开、载入记录均不会连接或驱动机构')
        self.observer=tk.BooleanVar(value=False);self.notes=tk.StringVar();self.label=tk.StringVar();self.geometry_notes=tk.StringVar()
        top=ttk.Frame(root,padding=10);top.pack(fill='x')
        ttk.Label(top,text='模式').pack(side='left');self.mode_box=ttk.Combobox(top,textvariable=self.mode,values=['模拟（不接硬件）','实机（PS串口）'],state='readonly',width=20);self.mode_box.pack(side='left',padx=6);self.mode_box.bind('<<ComboboxSelected>>',self.mode_changed)
        self.port_box=ttk.Combobox(top,textvariable=self.port,width=9);self.port_box.pack(side='left')
        ttk.Button(top,text='刷新串口',command=self.refresh_ports).pack(side='left',padx=5)
        self.connect_button=ttk.Button(top,text='连接 / 开始模拟',command=self.connect);self.connect_button.pack(side='left')
        self.stop_button=ttk.Button(top,text='停止全部舵机 / Esc',command=self.stop);self.stop_button.pack(side='right')
        projectbar=ttk.Frame(root,padding=(10,0,10,6));projectbar.pack(fill='x')
        ttk.Label(projectbar,text='结构版本/杆长配置').pack(side='left');ttk.Entry(projectbar,textvariable=self.geometry,width=30,state='readonly').pack(side='left',padx=5)
        for text,cmd in [('新建结构',self.new_project),('载入',self.load),('保存JSON',self.save),('导出CSV',self.export)]:ttk.Button(projectbar,text=text,command=cmd).pack(side='left',padx=3)
        ttk.Checkbutton(root,text='我在机构旁可立即断电；已检查本次目标、杆件及联动空间。首次启用没有实际角度反馈。',variable=self.observer,command=self.update_controls).pack(anchor='w',padx=12)
        ttk.Label(root,textvariable=self.status,foreground='#175a7a',wraplength=1130).pack(anchor='w',padx=12,pady=5)
        notebook=self.notebook=ttk.Notebook(root);notebook.pack(fill='both',expand=True,padx=10,pady=5)
        servo=ttk.Frame(notebook,padding=10);rails=ttk.Frame(notebook,padding=10);zones=ttk.Frame(notebook,padding=10);records=ttk.Frame(notebook,padding=10)
        for tab,title in [(servo,'十路舵机'),(rails,'两根丝杆'),(zones,'限位与危险组合'),(records,'标定记录')]:notebook.add(tab,text=title)
        self.build_servo(servo);self.build_rails(rails);self.build_zones(zones);self.build_records(records)
        ttk.Label(root,text='真实丝杆驱动尚未配置；实机移动按钮禁用。记录可用姿态不等于已证明所有中间路径安全。停止PWM不是切断电源。',wraplength=1140).pack(anchor='w',padx=12,pady=5)
        root.bind('<Escape>',lambda e:self.stop());root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh_ports();self.render();root.after(80,self.receive)

    def build_servo(self,box):
        self.servo_table=ttk.Treeview(box,columns=('pin','angle','pulse','output'),show='headings',height=10)
        for key,label,width in [('pin','编号 / 引脚 / 部位',300),('angle','指令角度°',140),('pulse','指令脉宽μs',140),('output','保持/实际位置',350)]:self.servo_table.heading(key,text=label);self.servo_table.column(key,width=width)
        self.servo_table.pack(fill='x');self.servo_table.bind('<<TreeviewSelect>>',self.select_servo)
        self.channel=tk.IntVar(value=1);self.angle=tk.StringVar(value='135');self.step=tk.StringVar(value='1');self.target_unit=tk.StringVar(value='角度°')
        row=ttk.Frame(box);row.pack(fill='x',pady=10)
        ttk.Label(row,text='选中编号').pack(side='left');ttk.Spinbox(row,from_=1,to=10,textvariable=self.channel,width=5).pack(side='left',padx=5)
        unit=ttk.Combobox(row,textvariable=self.target_unit,values=['角度°','脉宽μs'],width=8,state='readonly');unit.pack(side='left',padx=5);unit.bind('<<ComboboxSelected>>',self.target_unit_changed)
        ttk.Entry(row,textvariable=self.angle,width=10).pack(side='left',padx=5)
        self.servo_buttons=[]
        for text,cmd in [('发送该路',self.send_servo),('回中135°',lambda:self.send_servo(1500))]:
            b=ttk.Button(row,text=text,command=cmd);b.pack(side='left',padx=4);self.servo_buttons.append(b)
        ttk.Label(row,text='点动步长°').pack(side='left',padx=(15,0));ttk.Combobox(row,textvariable=self.step,values=['0.5','1','2','5'],width=6).pack(side='left',padx=5)
        for direction in (-1,1):
            b=ttk.Button(row,text='− 点动' if direction<0 else '+ 点动',command=lambda d=direction:self.jog(d));b.pack(side='left',padx=4);self.servo_buttons.append(b)
        ttk.Label(box,text='一次只改选中一路，已经启用的其它舵机继续保持；不会自动回中未启用轴。\n首次启用可输入目标；点动必须基于当前持续输出的指令。灰色/关闭的历史值不能作当前位置。',wraplength=1050).pack(anchor='w',pady=8)

    def build_rails(self,box):
        self.rail_vars={};self.rail_buttons=[]
        for axis in ('rail1','rail2'):
            setup=SETUP['rails'][axis]
            f=ttk.LabelFrame(box,text=f"丝杆 {axis[-1]} / {setup['character']} / {setup['screw_model']} / 标称行程{setup['nominal_travel_mm']}mm",padding=12);f.pack(fill='x',pady=7)
            details=f"{setup['character']} {setup['screw_model']}，驱动固件/接线/细分/限位待确认"
            v={key:tk.StringVar(value=val) for key,val in [('position',''),('step','1'),('minimum','0'),('maximum',str(setup['nominal_travel_mm'])),('details',details),('status','未知位置；尚未建立基准')]};self.rail_vars[axis]=v
            ttk.Label(f,textvariable=v['status']).grid(row=0,column=0,columnspan=8,sticky='w',pady=4)
            for col,(key,title) in enumerate([('position','实测当前位置mm'),('step','单次移动mm'),('minimum','行程下限mm'),('maximum','行程上限mm')]):
                ttk.Label(f,text=title).grid(row=1,column=col*2,sticky='w');ttk.Entry(f,textvariable=v[key],width=9).grid(row=1,column=col*2+1,padx=5)
            ttk.Button(f,text='录入实测位置 / 模拟位置',command=lambda a=axis:self.measure_rail(a)).grid(row=2,column=0,columnspan=2,pady=10,sticky='w')
            ttk.Button(f,text='当前位置记为零（不运动）',command=lambda a=axis:self.measure_rail(a,zero=True)).grid(row=2,column=2,columnspan=2,sticky='w')
            ttk.Button(f,text='位置未知 / 基准失效',command=lambda a=axis:self.invalidate_rail(a)).grid(row=2,column=4,columnspan=2,sticky='w')
            for col,d in [(6,-1),(7,1)]:
                b=ttk.Button(f,text='− 移动' if d<0 else '+ 移动',command=lambda a=axis,s=d:self.rail_move(a,s));b.grid(row=2,column=col,padx=4);self.rail_buttons.append(b)
            ttk.Label(f,text='归属/驱动器/导程/细分/限位：').grid(row=3,column=0,columnspan=2,sticky='w')
            ttk.Entry(f,textvariable=v['details'],width=60).grid(row=3,column=2,columnspan=4,sticky='ew',padx=4)
            ttk.Button(f,text='保存行程与参数',command=lambda a=axis:self.save_rail_config(a)).grid(row=3,column=6,columnspan=2,pady=5)
        ttk.Label(box,text=self.driver.reason+'\n实机中只能录入你用尺子量到的位置；不会把输入位置当作驱动回执。模拟移动明确标记为模拟，不能用于真实标定。\n未配置自动回零或限位开关，不会向机械端点运动来猜测零点。',wraplength=1060).pack(anchor='w',pady=15)

    def build_zones(self,box):
        row=ttk.Frame(box);row.pack(fill='x');self.limit_axis=tk.StringVar(value='servo1');self.limit_min=tk.StringVar(value='');self.limit_max=tk.StringVar(value='')
        ttk.Label(row,text='单轴软限位（舵机用°，丝杆用mm）').pack(side='left');ttk.Combobox(row,textvariable=self.limit_axis,values=AXES,width=9,state='readonly').pack(side='left',padx=4)
        ttk.Entry(row,textvariable=self.limit_min,width=9).pack(side='left');ttk.Label(row,text='至').pack(side='left');ttk.Entry(row,textvariable=self.limit_max,width=9).pack(side='left')
        ttk.Button(row,text='保存并启用',command=self.set_limit).pack(side='left',padx=5)
        ttk.Button(row,text='停机后禁用此限位',command=self.disable_limit).pack(side='left',padx=5)
        ttk.Label(box,text='禁止区域：勾选参与条件，只有全部条件同时满足才属于该组合。舵机区间用角度°；丝杆用mm。检查包含从起点到终点的直线路径，不只检查终点。',wraplength=1070).pack(anchor='w',pady=10)
        self.zone_name=tk.StringVar();namebar=ttk.Frame(box);namebar.pack(fill='x');ttk.Label(namebar,text='区域名称').pack(side='left');ttk.Entry(namebar,textvariable=self.zone_name,width=42).pack(side='left',padx=5)
        grid=ttk.Frame(box);grid.pack(fill='x');self.zone_fields={}
        for i,axis in enumerate(AXES):
            selected=tk.BooleanVar(value=False);lo=tk.StringVar();hi=tk.StringVar();self.zone_fields[axis]=(selected,lo,hi)
            row,col=divmod(i,3);base=col*4
            ttk.Checkbutton(grid,text=axis,variable=selected).grid(row=row,column=base,sticky='w',pady=5,padx=3)
            ttk.Entry(grid,textvariable=lo,width=10).grid(row=row,column=base+1);ttk.Label(grid,text='—').grid(row=row,column=base+2);ttk.Entry(grid,textvariable=hi,width=10).grid(row=row,column=base+3,padx=(0,15))
        actions=ttk.Frame(box);actions.pack(fill='x',pady=10)
        ttk.Button(actions,text='用当前已知指令/位置填入区间',command=self.fill_zone).pack(side='left')
        ttk.Button(actions,text='添加禁止组合',command=self.add_zone).pack(side='left',padx=8)
        ttk.Button(actions,text='导入同结构边界（保持当前姿态）',command=self.import_constraints).pack(side='left',padx=5)
        ttk.Button(actions,text='停机后删除选中禁区',command=self.delete_zone).pack(side='left',padx=5)
        self.zone_list=tk.Listbox(box,height=8);self.zone_list.pack(fill='both',expand=True)
        ttk.Label(box,text='记录“接近危险/禁止姿态”只保存样本；必须显式添加区间才能成为软件禁区。未测区域不会自动标成安全。',wraplength=1070).pack(anchor='w',pady=8)

    def build_records(self,box):
        ttk.Label(box,text='结构备注：杆长、滑轨零点、安装方向；修改结构应新建版本').pack(anchor='w')
        ttk.Entry(box,textvariable=self.geometry_notes,width=110).pack(fill='x',pady=(2,10))
        row=ttk.Frame(box);row.pack(fill='x');ttk.Label(row,text='姿态/位置名称').pack(side='left');ttk.Entry(row,textvariable=self.label,width=45).pack(side='left',padx=5)
        ttk.Label(box,text='备注：杆长、结构变化、哪两根杆接近、间隙毫米、从哪个方向进入等').pack(anchor='w',pady=(10,2));ttk.Entry(box,textvariable=self.notes,width=110).pack(fill='x')
        buttons=ttk.Frame(box);buttons.pack(fill='x',pady=10)
        for label,risk in [('记录可用姿态','safe'),('记录接近危险','near_danger'),('记录禁止姿态','forbidden')]:ttk.Button(buttons,text=label,command=lambda r=risk:self.record(r)).pack(side='left',padx=5)
        self.record_table=ttk.Treeview(box,columns=('label','risk','notes'),show='headings',height=16)
        for key,text,w in [('label','名称',260),('risk','现场判断',160),('notes','备注',640)]:self.record_table.heading(key,text=text);self.record_table.column(key,width=w)
        self.record_table.pack(fill='both',expand=True)
        ttk.Label(box,text='导出的JSON保留来源、是否正在保持、两丝杆基准和危险组合；CSV方便汇总。载入记录不会恢复输出，也不会回放轨迹。',wraplength=1070).pack(anchor='w',pady=10)

    def real(self):return self.mode.get().startswith('实机')
    def say(self,text):self.status.set(text)
    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            self.port_box['values']=[p.device for p in list_ports.comports()]
        except ImportError:self.port_box['values']=[]
    def mode_changed(self,event=None):
        if self.connected or self.busy:
            self.mode.set('模拟（不接硬件）' if self.board is None else '实机（PS串口）');self.say('请先断开连接再切换模式');return
        self.snapshot=model.new_snapshot();self.observer.set(False);self.render()
    def connect(self):
        if self.busy:return
        if not self.real():
            self.connected=not self.connected
            if not self.connected:self.snapshot=model.new_snapshot()
            self.say('模拟已开始：所有按钮仅更新模拟指令' if self.connected else '模拟已停止');self.render();return
        self.busy=True;self.commands.put(('disconnect',None) if self.connected else ('connect',self.port.get().strip()));self.update_controls()
    def from_board(self,state):
        self.board=state
        mask=state['enabled_mask'] if state.get('armed') and not state.get('pending') and not state.get('faults') and not state.get('output_lost') else 0
        self.snapshot=model.new_snapshot(state['pulse_us'],mask,None,copy.deepcopy(self.snapshot['rails']))
        if state.get('output_lost'):self.say('输出保持已丢失，先停止并现场检查；禁止自动重新启用')
    def select_servo(self,event=None):
        selected=self.servo_table.selection()
        if selected:
            self.channel.set(int(selected[0]));pulse=self.snapshot['pulse_us'][self.channel.get()-1]
            if pulse is not None:self.angle.set(str(pulse) if self.target_unit.get()=='脉宽μs' else f'{pulse_to_angle(pulse):.3f}')
    def target_unit_changed(self,event=None):
        try:pulse=self.snapshot['pulse_us'][self.channel.get()-1] or 1500
        except (ValueError,IndexError,tk.TclError):pulse=1500
        self.angle.set(str(pulse) if self.target_unit.get()=='脉宽μs' else f'{pulse_to_angle(pulse):.3f}')
    def guard(self,target):
        result=model.check_move(self.project,self.snapshot,target)
        if not result['allowed']:raise ValueError('被已记录边界阻止：'+'；'.join(result['reasons']))
    def send_servo(self,pulse=None):
        try:
            if not self.connected or self.busy or not self.observer.get():raise ValueError('先连接/开始模拟，并确认现场监护')
            channel=self.channel.get()
            if not 1<=channel<=10:raise ValueError('编号为1–10')
            if pulse is None:
                if self.target_unit.get()=='脉宽μs':
                    text=self.angle.get().strip()
                    if not text.isascii() or not text.isdigit():raise ValueError('脉宽需为500–2500之间的整数')
                    pulse=validate_pulse(int(text))
                else:pulse=angle_to_pulse(self.angle.get())
            target=copy.deepcopy(self.snapshot);target['pulse_us'][channel-1]=pulse;target['nominal_angle_deg'][channel-1]=pulse_to_angle(pulse)
            target['enabled_mask']|=1<<(channel-1);target['servo_provenance'][channel-1]='commanded_estimate' if self.real() else 'simulation_command'
            self.guard(target)
            if self.real():self.busy=True;self.commands.put(('move',(channel,pulse)))
            else:self.snapshot=target;self.say(f'仅模拟：{channel}号={pulse_to_angle(pulse):.3f}°；其它已启用轴继续保持')
            self.render()
        except Exception as e:self.say(str(e))
    def jog(self,direction):
        try:
            channel=self.channel.get()
            if not self.snapshot['enabled_mask']&(1<<(channel-1)):raise ValueError('该路未持续输出；先显式发送起始角度，不能按旧寄存器点动')
            step=finite_number(self.step.get(),'步长')
            if not 0<step<=10:raise ValueError('点动步长需大于0且不超过10°')
            angle=pulse_to_angle(self.snapshot['pulse_us'][channel-1])+direction*step
            pulse=angle_to_pulse(angle);self.angle.set(str(pulse) if self.target_unit.get()=='脉宽μs' else f'{angle:.3f}');self.send_servo(pulse)
        except Exception as e:self.say(str(e))
    def measure_rail(self,axis,zero=False):
        try:
            if self.busy:raise ValueError('请等当前操作完成')
            if self.real() and not self.observer.get():raise ValueError('请确认现场监护后录入实测值')
            v=self.rail_vars[axis];position=0. if zero else finite_number(v['position'].get(),'实测位置')
            if zero and not messagebox.askokcancel('记录位置基准','这只把当前地点记作0，不会移动丝杆。改变零点会使旧危险区失效，请为新零点新建结构记录。',parent=self.root):return
            if zero and (self.project['samples'] or self.project['forbidden_boxes']):raise ValueError('已有记录时不能改变零点；先新建结构版本')
            kind='manual_measured' if self.real() else 'simulated'
            self.snapshot['rails'][axis]=dict(position_mm=position,origin_known=True,position_kind=kind)
            self.say(f'{axis}已录入{position:g}mm（{kind}），未发运动指令');self.render()
        except Exception as e:self.say(str(e))
    def invalidate_rail(self,axis):
        self.snapshot['rails'][axis]=dict(position_mm=None,origin_known=False,position_kind='unknown');self.render();self.say(axis+'位置已标记未知')
    def save_rail_config(self,axis):
        try:
            v=self.rail_vars[axis];lo=finite_number(v['minimum'].get(),'行程下限');hi=finite_number(v['maximum'].get(),'行程上限')
            if lo>=hi:raise ValueError('行程下限必须小于上限')
            model.set_axis_limit(self.project,axis,lo,hi,True)
            self.project['rails'][axis]['notes']=v['details'].get();self.project['rails'][axis]['drive_enabled']=False
            self.autosave();self.say(axis+'行程及机械参数已保存；真实驱动仍未接入')
        except Exception as e:self.say(str(e))
    def rail_move(self,axis,direction):
        try:
            if not self.connected or not self.observer.get():raise ValueError('先开始模拟并确认现场观察')
            if self.real():raise ValueError(self.driver.reason)
            if not self.snapshot['rails'][axis]['origin_known']:raise ValueError('丝杆基准未知，先录入位置')
            v=self.rail_vars[axis];step=finite_number(v['step'].get(),'步长')
            if not 0<step<=10:raise ValueError('单次模拟步长需大于0且不超过10mm')
            current=self.snapshot['rails'][axis]['position_mm'];position=simulated_relative(current,direction*step,v['minimum'].get(),v['maximum'].get())
            target=copy.deepcopy(self.snapshot);target['rails'][axis]=dict(position_mm=position,origin_known=True,position_kind='simulated');self.guard(target)
            self.snapshot=target;self.say(f'仅模拟：{axis}移动到{position:g}mm，未发真实脉冲');self.render()
        except Exception as e:self.say(str(e))
    def stop(self):
        if self.real() and self.connected:self.busy=True;self.commands.put(('stop',None));self.say('正在请求停止舵机；真实丝杆驱动未连接')
        else:self.snapshot=model.new_snapshot(self.snapshot['pulse_us'],0,None,copy.deepcopy(self.snapshot['rails']));self.say('模拟输出已停止；舵机当前位置未知')
        self.render()
    def set_limit(self):
        try:
            axis=self.limit_axis.get();lo=finite_number(self.limit_min.get(),'下限');hi=finite_number(self.limit_max.get(),'上限')
            if axis.startswith('servo'):lo=angle_to_pulse(lo);hi=angle_to_pulse(hi)
            old=self.project['axis_limits'].get(axis)
            if old and old['enabled'] and (lo<old['minimum'] or hi>old['maximum']):self.archive_before_edit()
            model.set_axis_limit(self.project,axis,lo,hi,True);self.autosave();self.say('已启用'+axis+'软限位');self.render()
        except Exception as e:self.say(str(e))
    def archive_before_edit(self):
        if self.busy or self.snapshot['enabled_mask']:raise ValueError('先停止全部舵机输出，再放宽或删除已记录边界')
        self.autosave()
        archive=self.path.with_name(self.path.stem+'_before_edit_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
        model.save_project(self.project,archive)
        return archive
    def disable_limit(self):
        try:
            axis=self.limit_axis.get()
            if axis not in self.project['axis_limits']:raise ValueError('该轴尚无已保存限位')
            if not messagebox.askokcancel('禁用软限位',f'禁用{axis}的手动软限位？旧版本会归档，样本保留。',parent=self.root):return
            archive=self.archive_before_edit();self.project['axis_limits'][axis]['enabled']=False;self.autosave();self.say('已禁用；旧边界归档：'+str(archive))
        except Exception as e:self.say(str(e))
    def delete_zone(self):
        try:
            selected=self.zone_list.curselection()
            if not selected:raise ValueError('先在列表选中需要修正的禁区')
            index=selected[0];zone=self.project['forbidden_boxes'][index]
            if not messagebox.askokcancel('删除禁区',f"删除手动禁区“{zone['name']}”？旧边界会归档，观察样本保留。",parent=self.root):return
            archive=self.archive_before_edit();self.project['forbidden_boxes'].pop(index);self.autosave();self.render();self.say('已删除；旧边界归档：'+str(archive))
        except Exception as e:self.say(str(e))
    def fill_zone(self):
        for axis,(selected,lo,hi) in self.zone_fields.items():
            if axis.startswith('servo'):
                i=int(axis[5:])-1;known=bool(self.snapshot['enabled_mask']&(1<<i));value=pulse_to_angle(self.snapshot['pulse_us'][i]) if known else None;margin=1
            else:value=self.snapshot['rails'][axis]['position_mm'];known=self.snapshot['rails'][axis]['origin_known'];margin=1
            selected.set(known)
            if known:
                lo.set(f'{max(0,value-margin) if axis.startswith("servo") else value-margin:.3f}')
                hi.set(f'{min(270,value+margin) if axis.startswith("servo") else value+margin:.3f}')
    def add_zone(self):
        try:
            if not self.zone_name.get().strip():raise ValueError('请填写危险组合名称')
            bounds={}
            for axis,(selected,lo,hi) in self.zone_fields.items():
                if selected.get():
                    a=finite_number(lo.get(),'区间下限');b=finite_number(hi.get(),'区间上限')
                    if axis.startswith('servo'):a=angle_to_pulse(a);b=angle_to_pulse(b)
                    bounds[axis]=[a,b]
            model.add_zone(self.project,self.zone_name.get(),bounds);self.autosave();self.render();self.say('已添加禁止组合；后续目标和路径都会检查')
        except Exception as e:self.say(str(e))
    def import_constraints(self):
        if self.busy:self.say('请等当前操作完成');return
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('同结构标定JSON','*.json')])
        if not path:return
        try:
            other=model.load_project(path)
            if other['geometry_id']!=self.project['geometry_id']:raise ValueError('结构版本/零点不一致，不能导入旧边界')
            weaker=False
            for axis,limit in self.project['axis_limits'].items():
                new=other['axis_limits'].get(axis)
                if limit['enabled'] and (not new or not new['enabled'] or new['minimum']<limit['minimum'] or new['maximum']>limit['maximum']):weaker=True
            fingerprints={json.dumps(z['bounds'],sort_keys=True) for z in other['forbidden_boxes']}
            if any(json.dumps(z['bounds'],sort_keys=True) not in fingerprints for z in self.project['forbidden_boxes']):weaker=True
            if weaker and (self.busy or self.snapshot['enabled_mask']):raise ValueError('导入会放宽/删除现有边界，请先停止全部舵机输出')
            trial=copy.deepcopy(self.project);trial['axis_limits']=copy.deepcopy(other['axis_limits']);trial['forbidden_boxes']=copy.deepcopy(other['forbidden_boxes'])
            result=model.check_move(trial,self.snapshot,self.snapshot)
            if not result['allowed']:raise ValueError('当前姿态不足以接入这些边界：'+'；'.join(result['reasons']))
            if not messagebox.askokcancel('导入边界','保持当前指令，使用文件里的同结构软限位和禁区替换当前边界；不会加载姿态或发运动。继续？',parent=self.root):return
            if weaker:self.archive_before_edit()
            # Keep independent observation IDs separate from imported zone IDs.
            existing_ids={s['id'] for s in trial['samples']}
            if any(z['id'] in existing_ids for z in trial['forbidden_boxes']):raise ValueError('记录ID冲突，未导入')
            self.project=trial;self.autosave();self.render();self.say('边界已导入；当前输出和位置未改变')
        except Exception as e:self.say(str(e))
    def record(self,risk):
        try:
            model.record_sample(self.project,self.snapshot,self.label.get(),risk,('实机人工观察：' if self.real() else '仅模拟演练：')+self.notes.get())
            self.autosave();self.render();self.say('已保存完整组合；文件：'+str(self.path))
        except Exception as e:self.say(str(e))
    def autosave(self):
        self.project['geometry_notes']=self.geometry_notes.get()
        if self.path is None:
            folder=ROOT/'logs/mechanism_calibration';folder.mkdir(parents=True,exist_ok=True)
            self.path=folder/('calibration_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
        model.save_project(self.project,self.path)
    def save(self):
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',initialdir=str(ROOT/'logs'),filetypes=[('标定JSON','*.json')])
        if path:
            try:self.project['geometry_notes']=self.geometry_notes.get();model.save_project(self.project,path);self.path=Path(path);self.say('已保存：'+path)
            except Exception as e:self.say(str(e))
    def export(self):
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.csv',initialdir=str(ROOT/'logs'),filetypes=[('标定CSV','*.csv')])
        if path:
            try:model.export_csv(self.project,path);self.say('已导出：'+path)
            except Exception as e:self.say(str(e))
    def load(self):
        if self.connected or self.busy:self.say('先断开连接再载入；载入不会恢复输出');return
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('标定JSON','*.json')])
        if path:
            try:
                self.project=model.load_project(path);self.path=Path(path);self.geometry.set(self.project['geometry_id']);self.geometry_notes.set(self.project['geometry_notes']);self.snapshot=model.new_snapshot()
                for axis,v in self.rail_vars.items():
                    v['details'].set(self.project['rails'][axis]['notes']);v['position'].set('')
                    limit=self.project['axis_limits'].get(axis)
                    v['minimum'].set(str(limit['minimum']) if limit else '0');v['maximum'].set(str(limit['maximum']) if limit else '')
                self.render();self.say('已载入记录，当前实际位置全部未知；未恢复输出')
            except Exception as e:self.say(str(e))
    def new_project(self):
        if self.connected or self.busy:self.say('先断开连接，再新建杆长/零点配置');return
        if (self.project['samples'] or self.project['forbidden_boxes']) and not messagebox.askokcancel('新建结构','旧记录会保留在已保存文件中，新结构从未知位置开始。继续？',parent=self.root):return
        try:
            name=simpledialog.askstring('新建结构版本','填写杆长/零点对应的结构版本名称：',initialvalue='结构-'+datetime.now().strftime('%Y%m%d-%H%M%S'),parent=self.root)
            if not name or not name.strip():return
            if name==self.project['geometry_id'] and (self.project['samples'] or self.project['forbidden_boxes']):raise ValueError('杆长/零点变化请使用新的结构版本名称')
            if self.project['samples'] or self.project['forbidden_boxes']:self.autosave()
            self.geometry.set(name);self.geometry_notes.set('');self.project=model.new_project(name);self.snapshot=model.new_snapshot();self.path=None
            for axis,v in self.rail_vars.items():
                v['position'].set('');v['details'].set(f"{SETUP['rails'][axis]['character']} {SETUP['rails'][axis]['screw_model']}，驱动待确认");v['minimum'].set('0');v['maximum'].set(str(SETUP['rails'][axis]['nominal_travel_mm']))
            self.render()
        except Exception as e:self.say(str(e))
    def render(self):
        for item in self.servo_table.get_children():self.servo_table.delete(item)
        roles=('人物左手','人物头部','人物右手','虎头','虎后端')
        for i,pulse in enumerate(self.snapshot['pulse_us']):
            held=bool(self.snapshot['enabled_mask']&(1<<i));angle='—' if pulse is None else f'{pulse_to_angle(pulse):.3f}'
            self.servo_table.insert('', 'end',iid=str(i+1),values=(f'{i+1} / {PINS[i]} / {roles[i//2]}',angle,pulse if pulse is not None else '—',('模拟保持' if not self.real() else '指令保持中') if held else '未保持；位置未知'))
        for axis,v in self.rail_vars.items():
            s=self.snapshot['rails'][axis];v['status'].set(f"{s['position_mm']}mm / {s['position_kind']}" if s['origin_known'] else '位置未知；基准未建立')
        self.zone_list.delete(0,'end')
        for zone in self.project['forbidden_boxes']:self.zone_list.insert('end',json.dumps(zone,ensure_ascii=False))
        for item in self.record_table.get_children():self.record_table.delete(item)
        for sample in self.project['samples']:self.record_table.insert('', 'end',values=(sample.get('label',''),sample.get('risk',''),sample.get('notes','')))
        self.update_controls()
    def update_controls(self):
        ready=self.connected and not self.busy and self.observer.get() and not self.closing
        for b in self.servo_buttons:b.configure(state='normal' if ready else 'disabled')
        for b in self.rail_buttons:b.configure(state='normal' if ready and not self.real() else 'disabled')
        self.connect_button.configure(text='断开 / 结束模拟' if self.connected else '连接 / 开始模拟',state='disabled' if self.busy or self.closing else 'normal')
        self.mode_box.configure(state='disabled' if self.connected or self.busy else 'readonly')
        self.port_box.configure(state='disabled' if self.connected or self.busy else 'normal')
    def receive(self):
        while True:
            try:event,value=self.events.get_nowait()
            except queue.Empty:break
            if event=='closed':self.root.destroy();return
            if event=='connected':self.connected=True;self.busy=False;self.from_board(value);self.say('真实舵机服务已连接；当前输出状态已读取，未发送运动')
            elif event in ('state','snapshot'):self.from_board(value);self.busy=False if event=='state' else self.busy
            elif event in ('error','disconnected'):
                self.connected=False;self.busy=False;self.board=None;self.snapshot=model.new_snapshot();self.observer.set(False);self.say('连接失败/已断开：'+str(value or '位置基准已失效'))
            self.render()
        self.root.after(80,self.receive)
    def close(self):
        if self.closing:return
        self.closing=True;self.commands.put(('shutdown',None));self.update_controls()

def main():
    p=argparse.ArgumentParser();p.add_argument('--smoke-test',action='store_true');args=p.parse_args()
    root=tk.Tk();app=App(root)
    if args.smoke_test:
        root.update_idletasks()
        for tab in app.notebook.tabs():
            app.notebook.select(tab);root.update_idletasks()
            def check_layout(widget):
                if widget.winfo_ismapped():
                    x=widget.winfo_rootx()-root.winfo_rootx();y=widget.winfo_rooty()-root.winfo_rooty()
                    assert x>=0 and y>=0 and x+widget.winfo_width()<=root.winfo_width()+2 and y+widget.winfo_height()<=root.winfo_height()+2,(str(widget),x,y,widget.winfo_width(),widget.winfo_height(),root.winfo_width(),root.winfo_height())
                for child in widget.winfo_children():check_layout(child)
            check_layout(root)
        assert not app.connected and app.commands.empty() and app.mode.get().startswith('模拟')
        app.send_servo();assert app.commands.empty()
        app.mode.set('实机（PS串口）');app.render();assert all(str(b['state'])=='disabled' for b in app.rail_buttons)
        app.mode.set('模拟（不接硬件）');app.render()
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            app.path=Path(folder)/'smoke.json';app.connect();app.observer.set(True)
            app.angle.set('135');app.send_servo();assert app.snapshot['enabled_mask']==1
            app.channel.set(2);app.angle.set('100');app.send_servo();assert app.snapshot['enabled_mask']==3
            for axis,pos in [('rail1','5'),('rail2','10')]:
                app.rail_vars[axis]['position'].set(pos);app.rail_vars[axis]['maximum'].set('100');app.measure_rail(axis)
            app.label.set('模拟完整姿态');app.record('safe');assert len(app.project['samples'])==1
            model.export_csv(app.project,Path(folder)/'smoke.csv')
            model.add_zone(app.project,'穿越中间区域',{'servo1':[angle_to_pulse(139),angle_to_pulse(141)],'rail1':[4,6]})
            app.channel.set(1);app.angle.set('145');app.send_servo();assert app.snapshot['pulse_us'][0]==1500
            app.stop();model.validate_snapshot(app.snapshot);assert model.axis_value(app.snapshot,'servo1') is None
            app.connect();assert not app.connected
        root.after(100,app.close)
    root.mainloop()

if __name__=='__main__':main()
