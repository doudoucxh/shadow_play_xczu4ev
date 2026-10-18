"""Local ten-servo initial-angle window. Only an explicit click sends targets."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox

from initial_pose_session import InitialPoseSession
from initial_pose_model import (PINS,RODS,DEGREE_LIMITS,DEFAULT_ANGLES,
                                angles_to_pulses,encode_profile,decode_profile)
from servo_center_session import all_off

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'logs/servo_initial_pose'


class Worker(threading.Thread):
    def __init__(self,commands,events,cancel):
        super().__init__(daemon=True)
        self.commands,self.events,self.cancel=commands,events,cancel
        self.session=None;self.active=False

    def release(self):
        try:
            if self.session:self.session.close()
        finally:self.session=None;self.active=False

    def run(self):
        poll=0
        while True:
            try:
                try:op,value=self.commands.get(timeout=.1)
                except queue.Empty:op,value=None,None
                if op in ('disconnect','shutdown'):
                    self.release();self.events.put(('closed' if op=='shutdown' else 'disconnected',None))
                    if op=='shutdown':return
                elif op=='connect':
                    if self.session:raise RuntimeError('请先断开旧连接。')
                    LOCAL.mkdir(parents=True,exist_ok=True)
                    log=LOCAL/('serial_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.jsonl')
                    self.session=InitialPoseSession(value,log)
                    self.events.put(('connected',self.session.status()))
                elif op=='initialize':
                    if not self.session or self.active:raise RuntimeError('请先连接并停止全部输出。')
                    if self.cancel.is_set():self.events.put(('cancelled',None))
                    else:
                        state=self.session.initialize(value,True)
                        self.active=True;self.events.put(('initialized',state))
                elif op=='stop' and self.session:
                    state=self.session.stop();self.active=False;self.events.put(('stopped',state))
                if self.session and time.monotonic()>=poll:
                    state=self.session.status();poll=time.monotonic()+.4
                    if state.get('output_lost') or (self.active and (all_off(state) or state.get('enabled_mask')!=1023)):
                        raise RuntimeError('保持输出已丢失或被停止；请检查机构后重新连接，不会自动重发。')
                    self.events.put(('snapshot',state))
            except Exception as error:
                try:self.release()
                except Exception:pass
                self.events.put(('error',str(error)))


class App:
    def __init__(self,root):
        self.root=root;root.title('十路舵机 · 初始角度设定');root.geometry('960x800');root.minsize(920,760)
        root.option_add('*Font',('Microsoft YaHei UI',10))
        self.commands,self.events=queue.Queue(),queue.Queue();self.cancel=threading.Event()
        self.worker=Worker(self.commands,self.events,self.cancel);self.worker.start()
        self.connected=self.busy=self.active=self.closing=False
        self.port=tk.StringVar(value='COM17');self.confirmed=tk.BooleanVar(value=False)
        self.status=tk.StringVar(value='未连接 · 135° / 1500 μs 是装配参考，不代表当前真实姿态。')
        body=ttk.Frame(root,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='十路舵机初始角度',font=('Microsoft YaHei UI',21,'bold')).pack(anchor='w')
        ttk.Label(body,text='填写十路目标 → 连接板子 → 确认现场条件 → 一键设定').pack(anchor='w',pady=(4,10))
        row=ttk.Frame(body);row.pack(fill='x',pady=(0,8))
        ttk.Label(row,text='PS调试串口').pack(side='left')
        self.port_box=ttk.Combobox(row,textvariable=self.port,width=12);self.port_box.pack(side='left',padx=8)
        self.refresh_button=ttk.Button(row,text='刷新串口',command=self.refresh_ports);self.refresh_button.pack(side='left')
        self.connect_button=ttk.Button(row,text='连接板子',command=self.connect);self.connect_button.pack(side='right')
        ttk.Label(body,text='连接前：关闭其他串口工具，板端已登录 root；本窗口不保存登录密码。').pack(anchor='w',pady=(0,8))
        table=ttk.Frame(body);table.pack(fill='x')
        headers=('编号 / 引脚','控制部位','初始角度（°）','目标（μs）','填写范围（°）','板端指令（无实际角度反馈）')
        for col,text in enumerate(headers):ttk.Label(table,text=text).grid(row=0,column=col,padx=7,pady=7,sticky='w')
        self.angles=[];self.targets=[];self.readbacks=[];self.entries=[]
        for i in range(10):
            angle=tk.StringVar(value='135');target=tk.StringVar(value='1500');readback=tk.StringVar(value='未读取')
            self.angles.append(angle);self.targets.append(target);self.readbacks.append(readback)
            for col,text in [(0,f'{i+1}号 / {PINS[i]}'),(1,RODS[i//2]),(4,f'{DEGREE_LIMITS[i][0]}–{DEGREE_LIMITS[i][1]}')]:
                ttk.Label(table,text=text).grid(row=i+1,column=col,sticky='w',padx=7,pady=5)
            entry=ttk.Entry(table,textvariable=angle,width=12);entry.grid(row=i+1,column=2,padx=7,pady=5);self.entries.append(entry)
            ttk.Label(table,textvariable=target,width=11).grid(row=i+1,column=3,sticky='w',padx=7)
            ttk.Label(table,textvariable=readback).grid(row=i+1,column=5,sticky='w',padx=7)
        row=ttk.Frame(body);row.pack(fill='x',pady=10)
        self.profile_buttons=[]
        for text,command in [('填入全部135°',self.defaults),('保存角度…',self.save),('载入角度…',self.load)]:
            button=ttk.Button(row,text=text,command=command);button.pack(side='left',padx=(0,8));self.profile_buttons.append(button)
        ttk.Label(body,text='填写范围沿用既有内缩限制；接杆后的组合和中间路径仍须现场检查。').pack(anchor='w',pady=(0,8))
        self.confirm_box=ttk.Checkbutton(body,text='我在现场可立即断电，已检查这十路目标及联动空间，接受首次启用可能快速转动。',
                    variable=self.confirmed,command=self.update_controls);self.confirm_box.pack(anchor='w')
        row=ttk.Frame(body);row.pack(fill='x',pady=12)
        self.send_button=ttk.Button(row,text='一键设定全部初始角度',command=self.send);self.send_button.pack(side='left',fill='x',expand=True,ipady=10,padx=(0,14))
        self.stop_button=tk.Button(row,text='全部停止 / Esc',command=self.stop,bg='#aa2929',fg='white',font=('Microsoft YaHei UI',13,'bold'))
        self.stop_button.pack(side='right',ipadx=15,ipady=7)
        ttk.Label(body,textvariable=self.status,foreground='#145577',wraplength=915).pack(anchor='w',pady=(0,8))
        ttk.Label(body,text='设定后十路持续保持，直到停止、断开或关闭窗口；通信失联由看门狗停止输出。\n'
                  '停止PWM不是切断电源。此工具只发送初始目标，不证明已完成回中或V20路线标定。',wraplength=915).pack(anchor='w')
        for value in self.angles:value.trace_add('write',self.changed)
        self.refresh_ports();self.update_controls()
        root.bind('<Escape>',lambda event:self.stop());root.protocol('WM_DELETE_WINDOW',self.close);root.after(80,self.receive)

    def refresh_ports(self):
        from serial.tools import list_ports
        self.port_box['values']=[p.device for p in list_ports.comports()]

    def values(self):return [v.get().strip() for v in self.angles]

    def changed(self,*args):
        self.confirmed.set(False)
        try:
            pulses=angles_to_pulses(self.values())
            for field,pulse in zip(self.targets,pulses):field.set(str(pulse))
        except (ValueError,TypeError):
            for field in self.targets:field.set('请检查')
        self.update_controls()

    def update_controls(self):
        locked=self.busy or self.active or self.closing
        try:angles_to_pulses(self.values());valid=True
        except (ValueError,TypeError):valid=False
        self.send_button.configure(state='normal' if self.connected and not locked and valid and self.confirmed.get() else 'disabled')
        self.stop_button.configure(state='normal' if self.connected and not self.closing else 'disabled')
        self.connect_button.configure(text='断开连接' if self.connected else '连接板子',state='disabled' if self.busy or self.closing else 'normal')
        self.confirm_box.configure(state='disabled' if locked else 'normal')
        self.port_box.configure(state='disabled' if self.connected or self.busy or self.closing else 'normal')
        self.refresh_button.configure(state='disabled' if self.connected or self.busy or self.closing else 'normal')
        for widget in self.entries+self.profile_buttons:widget.configure(state='disabled' if locked else 'normal')

    def defaults(self):
        if self.busy or self.active or self.closing:return
        for field,value in zip(self.angles,DEFAULT_ANGLES):field.set(f'{value:g}')

    def save(self):
        try:profile=encode_profile(self.values())
        except ValueError as error:messagebox.showerror('角度填写有误',str(error),parent=self.root);return
        LOCAL.mkdir(parents=True,exist_ok=True)
        path=filedialog.asksaveasfilename(parent=self.root,initialdir=str(LOCAL),initialfile='初始角度.json',defaultextension='.json',filetypes=[('角度配置','*.json')])
        if path:
            target=Path(path);staged=target.with_name(target.name+'.tmp')
            staged.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');staged.replace(target)
            self.status.set('角度已保存：'+path)

    def load(self):
        path=filedialog.askopenfilename(parent=self.root,initialdir=str(LOCAL if LOCAL.exists() else ROOT),filetypes=[('角度配置','*.json')])
        if not path:return
        try:values=decode_profile(json.loads(Path(path).read_text(encoding='utf-8-sig')))
        except (ValueError,TypeError,OSError) as error:messagebox.showerror('无法载入',str(error),parent=self.root);return
        for field,value in zip(self.angles,values):field.set(f'{value:g}')
        self.status.set('已载入角度，仅更新填写内容：'+path)

    def connect(self):
        if self.busy or self.closing:return
        self.confirmed.set(False);self.busy=True
        self.commands.put(('disconnect',None) if self.connected else ('connect',self.port.get().strip()))
        self.status.set('正在停止并断开…' if self.connected else '正在连接，只读核对输出状态…');self.update_controls()

    def send(self):
        if not self.connected or self.busy or self.active or self.closing or not self.confirmed.get():return
        try:pulses=angles_to_pulses(self.values())
        except ValueError as error:self.status.set(str(error));return
        self.confirmed.set(False);self.busy=True;self.cancel.clear()
        self.commands.put(('initialize',pulses));self.status.set('正在发送这十路初始目标，请现场观察。');self.update_controls()

    def stop(self):
        self.cancel.set();self.confirmed.set(False)
        if self.connected:self.commands.put(('stop',None));self.status.set('正在请求全部停止；异常时请直接断开舵机电源。')
        self.update_controls()

    def snapshot(self,state):
        for i,pulse in enumerate(state['pulse_us']):
            active=state['armed'] and bool(state['enabled_mask']&(1<<i))
            self.readbacks[i].set(f'{(pulse-500)*270/2000:.2f}° / {pulse} μs' if active else f'未输出（历史 {pulse} μs）')

    def receive(self):
        while True:
            try:event,value=self.events.get_nowait()
            except queue.Empty:break
            if event=='closed':self.root.destroy();return
            if event in ('connected','initialized','stopped','snapshot'):self.snapshot(value)
            if event=='connected':self.connected=True;self.busy=False;self.status.set('已连接，十路输出均关闭。检查填写值后勾选现场确认。')
            elif event=='initialized':self.active=True;self.busy=False;self.status.set('十路目标已收到板端回执，正在保持。实际姿态请现场观察；点击全部停止可关闭输出。')
            elif event=='stopped':self.active=self.busy=False;self.status.set('已确认十路输出关闭；关闭后的指令记录不能证明实际姿态。')
            elif event=='disconnected':self.connected=self.active=self.busy=False;self.status.set('已断开，串口已释放。')
            elif event=='cancelled':self.busy=False;self.status.set('已取消尚未发送的初始目标。')
            elif event=='error':
                self.connected=self.active=self.busy=False;self.confirmed.set(False)
                self.status.set('连接/操作失败：'+value+' 如机构异常，请立即断开舵机电源。')
            self.update_controls()
        self.root.after(80,self.receive)

    def close(self):
        if self.closing:return
        self.closing=True;self.cancel.set();self.commands.put(('shutdown',None));self.update_controls()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke-test',action='store_true');args=parser.parse_args()
    root=tk.Tk();app=App(root)
    if args.smoke_test:
        assert not app.connected and app.commands.empty()
        app.confirmed.set(True);app.send();assert app.commands.empty()
        app.angles[0].set('136');assert not app.confirmed.get()
        assert str(app.send_button['state'])=='disabled'
        root.update();assert app.stop_button.winfo_rooty()+app.stop_button.winfo_height()<root.winfo_rooty()+root.winfo_height()
        root.after(150,app.close)
    root.mainloop()


if __name__=='__main__':main()
