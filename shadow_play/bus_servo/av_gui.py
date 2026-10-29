"""Audio and servo motion share one editable, non-destructive timeline."""
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from uuid import uuid4

from .av_editing import AVProject, clip_end, duration, compile_motion, load_file, save_bundle
from .audio import AudioTrack, AudioPlayer, import_audio, export_wav
from .editor_gui import COLORS, read_json
from .model import playback_plan
from .timeline import format_time


class AVWindow:
    def __init__(self, app, directory):
        self.app=app;self.profile=app.profile;self.directory=Path(directory)
        self.project=AVProject(self.profile,app.numbers())
        if app.record and app.record.get('complete'):
            if 'av_project' in app.record:self.project=AVProject(self.profile,data=app.record['av_project'])
            else:self.project.add_motion(app.record,'主窗口轨迹')
        self.draft=self.directory/('av_'+uuid4().hex+'.av.project.json')
        self.player=None;self.previewing=False;self.preview_generation=0;self.busy=False;self.cursor=0.;self.zoom=1.;self.drag=None;self.preview_record=None
        self.window=tk.Toplevel(app.root);self.window.title('皮影 · 音频与轨迹联合剪辑')
        self.window.geometry('1240x860');self.window.minsize(1020,790)
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.bind('<Escape>',lambda e:(self.stop_preview(),app.stop()))
        body=ttk.Frame(self.window,padding=14);body.pack(fill='both',expand=True)
        title=ttk.Frame(body);title.pack(fill='x')
        ttk.Label(title,text='音频与轨迹联合剪辑',font=('Microsoft YaHei UI',18,'bold')).pack(side='left')
        ttk.Button(title,text='使用说明',command=lambda:app.open_guide('av-edit')).pack(side='right')
        self.info=tk.StringVar();ttk.Label(body,textvariable=self.info,foreground='#526b7c').pack(anchor='w',pady=(3,6))
        self.buttons=[]
        def row():
            frame=ttk.Frame(body);frame.pack(fill='x',pady=3);return frame
        def button(parent,text,action):
            b=ttk.Button(parent,text=text,command=lambda:self.run(action));b.pack(side='left',padx=(0,5));self.buttons.append(b);return b
        r=row()
        for label,fn in [('新建（主窗选轴）',self.new),('打开工程…',self.open),('另存工程…',lambda:self.save(False)),
                         ('导入轨迹…',self.import_motion),('导入音频…',self.import_sound),('撤销',lambda:self.history(False)),('重做',lambda:self.history(True))]:button(r,label,fn)
        r=row()
        button(r,'应用到主窗回放',self.apply);button(r,'导出联合回放…',lambda:self.save(True));button(r,'导出剪后音频 WAV…',self.export_audio)
        ttk.Label(r,text='试听与编辑不驱动舵机；原素材保留。',foreground='#526b7c').pack(side='left',padx=10)
        table=ttk.Frame(body);table.pack(fill='x',pady=7)
        self.tree=ttk.Treeview(table,columns=('type','name','at','range','end','speed','gain'),show='headings',height=5,selectmode='browse')
        for name,label,width in [('type','轨道',70),('name','片段',220),('at','轴上起点 / s',105),('range','素材入点 → 出点 / s',190),('end','轴上终点 / s',105),('speed','倍率',65),('gain','音量',65)]:
            self.tree.heading(name,text=label);self.tree.column(name,width=width,stretch=name=='name')
        self.tree.pack(side='left',fill='x',expand=True);scroll=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',self.selected)
        self.fields={name:tk.StringVar() for name in ('name','at_s','in_s','out_s','speed','gain')}
        self.entries={}
        r=row()
        for key,label,width in [('name','名称',15),('at_s','轴上起点',8),('in_s','素材入点',8),('out_s','素材出点',8),('speed','倍率',5),('gain','音量',5)]:
            ttk.Label(r,text=label).pack(side='left',padx=(0,3))
            self.entries[key]=ttk.Entry(r,textvariable=self.fields[key],width=width);self.entries[key].pack(side='left',padx=(0,6))
        button(r,'应用参数',self.properties)
        r=row()
        button(r,'对齐到播放头',lambda:self.project_edit(lambda:self.project.update(self.ident(),at_s=self.cursor)))
        button(r,'分割选中片段',lambda:self.project_edit(lambda:self.project.split(self.cursor,self.ident())))
        button(r,'同时分割两轨',lambda:self.project_edit(lambda:self.project.split(self.cursor)))
        button(r,'删除选中片段',lambda:self.project_edit(lambda:self.project.delete(self.ident())))
        self.range_start=tk.StringVar(value='0');self.range_end=tk.StringVar(value='1')
        r=row();ttk.Label(r,text='共同选区 / 秒').pack(side='left',padx=(0,6))
        ttk.Entry(r,textvariable=self.range_start,width=8).pack(side='left');button(r,'起点←播放头',lambda:self.range_start.set(f'{self.cursor:.3f}'))
        ttk.Entry(r,textvariable=self.range_end,width=8).pack(side='left');button(r,'终点←播放头',lambda:self.range_end.set(f'{self.cursor:.3f}'))
        button(r,'两轨删段并前移',lambda:self.range_edit(False));button(r,'两轨只保留选区',lambda:self.range_edit(True))
        r=row();button(r,'▶ 从播放头试听',self.play_preview)
        ttk.Button(r,text='■ 停止试听',command=self.stop_preview).pack(side='left',padx=5)
        self.preview_speed=tk.StringVar(value='1.0')
        ttk.Label(r,text='试听倍率').pack(side='left',padx=(12,3));ttk.Combobox(r,textvariable=self.preview_speed,values=['0.5','1.0','1.5','2.0'],state='readonly',width=5).pack(side='left')
        button(r,'放大 +',lambda:self.set_zoom(2));button(r,'缩小 −',lambda:self.set_zoom(.5))
        self.clock_text=tk.StringVar();ttk.Label(r,textvariable=self.clock_text,font=('Microsoft YaHei UI',10,'bold')).pack(side='right')
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x')
        self.status=tk.StringVar(value='导入音频和轨迹后，拖动片段对齐；点击时间刻度定位播放头。')
        ttk.Label(footer,textvariable=self.status,foreground='#25566a',wraplength=1160).pack(anchor='w')
        ttk.Label(footer,text='电脑出声随动作进度变速，音调也随速度变化；通信等待处暂停声音。间隔保留上一姿势，接缝和快段会按限速放慢。',foreground='#627987',wraplength=1160).pack(anchor='w',pady=(4,0))
        area=ttk.Frame(body);area.pack(fill='both',expand=True,pady=6)
        self.canvas=tk.Canvas(area,bg='white',height=260,highlightthickness=1,highlightbackground='#dce4eb');self.canvas.pack(fill='both',expand=True)
        bar=ttk.Scrollbar(area,orient='horizontal',command=self.canvas.xview);bar.pack(fill='x');self.canvas.configure(xscrollcommand=bar.set)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.mouse_down);self.canvas.bind('<B1-Motion>',self.mouse_move);self.canvas.bind('<ButtonRelease-1>',self.mouse_up)
        self.refresh();self.autosave()

    def run(self, fn):
        try:
            if self.busy:raise RuntimeError('正在处理音频，请稍候。')
            return fn()
        except Exception as exc:self.status.set(str(exc));messagebox.showerror('剪辑未完成',str(exc),parent=self.window)

    def ident(self):
        rows=self.tree.selection()
        if not rows:raise ValueError('请先选择一个片段。')
        return rows[0]

    def selected(self,event=None):
        rows=self.tree.selection()
        if rows:
            c=next(c for c in self.project.data['clips'] if c['id']==rows[0])
            for key,var in self.fields.items():var.set(str(c.get(key,1)))
            self.entries['gain'].configure(state='normal' if c['kind']=='audio' else 'disabled')
        self.draw()

    def refresh(self):
        chosen=self.tree.selection();self.tree.delete(*self.tree.get_children())
        for c in sorted(self.project.data['clips'],key=lambda c:(c['kind'],c['at_s'])):
            self.tree.insert('', 'end',iid=c['id'],values=('音频' if c['kind']=='audio' else '轨迹',c['name'],f'{c["at_s"]:.3f}',f'{c["in_s"]:.3f} → {c["out_s"]:.3f}',f'{clip_end(c):.3f}',c['speed'],c.get('gain',1)))
        ids=self.tree.get_children()
        if ids:self.tree.selection_set(chosen[0] if chosen and chosen[0] in ids else ids[-1])
        self.info.set('工程轴 '+', '.join(map(str,self.project.data['selected']))+'   ·   音频与轨迹共享秒数，拖动片段改变起点，源文件不覆盖。')
        self.preview_record=None
        if any(c['kind']=='motion' for c in self.project.data['clips']):self.preview_record=compile_motion(self.project.data,self.profile)
        self.cursor=min(self.cursor,duration(self.project.data));self.selected();self.draw()

    def autosave(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        temporary=self.draft.with_suffix('.pending')
        temporary.write_text(json.dumps(self.project.data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temporary.replace(self.draft)

    def project_edit(self,fn):
        self.stop_preview();fn();self.refresh();self.autosave();self.status.set('剪辑已保存到草稿；原素材保持不变。')

    def properties(self):
        values={k:(v.get() if k=='name' else float(v.get())) for k,v in self.fields.items()}
        self.project_edit(lambda:self.project.update(self.ident(),**values))

    def range_edit(self,keep):
        self.project_edit(lambda:self.project.cut_range(float(self.range_start.get()),float(self.range_end.get()),keep))

    def history(self,redo):self.project_edit(lambda:self.project.history(redo))

    def new(self):
        self.stop_preview();self.autosave();self.project=AVProject(self.profile,self.app.numbers());self.cursor=0
        self.draft=self.directory/('av_'+uuid4().hex+'.av.project.json');self.refresh();self.autosave()

    def open(self):
        path=filedialog.askopenfilename(parent=self.window,title='打开联合工程或联合回放',filetypes=[('JSON','*.json')])
        if not path:return
        data=load_file(path,self.profile);self.stop_preview();self.autosave()
        self.project=AVProject(self.profile,data=data.get('av_project',data));self.cursor=0
        self.draft=self.directory/('av_'+uuid4().hex+'.av.project.json');self.refresh();self.autosave()
        self.status.set('已打开：'+path)

    def import_motion(self):
        paths=filedialog.askopenfilenames(parent=self.window,title='导入原始或编辑后的轨迹',filetypes=[('轨迹','*.json')])
        for path in paths:self.project_edit(lambda path=path:self.project.add_motion(read_json(path),Path(path).stem))

    def background(self,job,done,label):
        self.stop_preview();self.busy=True;self.status.set(label)
        for b in self.buttons:b.configure(state='disabled')
        result=queue.Queue()
        def work():
            try:result.put((True,job()))
            except Exception as exc:result.put((False,exc))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            if not self.window.winfo_exists():return
            try:ok,value=result.get_nowait()
            except queue.Empty:self.window.after(50,poll);return
            self.busy=False
            for b in self.buttons:b.configure(state='normal')
            if ok:self.run(lambda:done(value))
            else:self.run(lambda:(_ for _ in ()).throw(value))
        self.window.after(50,poll)

    def import_sound(self):
        paths=filedialog.askopenfilenames(parent=self.window,title='导入音频',filetypes=[('音频','*.wav *.mp3 *.m4a *.aac *.flac *.ogg'),('所有文件','*.*')])
        if not paths:return
        at=self.cursor
        def done(assets):
            for asset in assets:self.project.add_audio(asset,at)
            self.refresh();self.autosave();self.status.set('音频已导入；可拖动波形片段与轨迹对齐，重叠音频会混音。')
        self.background(lambda:[import_audio(p,self.directory/'media') for p in paths],done,'正在解码音频和生成波形…')

    def apply(self):
        if self.app.busy or self.app.recording or self.app.playing:raise ValueError('先结束主窗口当前操作，再应用剪辑。')
        self.stop_preview();record=compile_motion(self.project.data,self.profile)
        AudioTrack(self.project.data) # verify all referenced audio before handing off
        self.app.record=record;self.app.live_samples=[];self.app.select(record['selected'])
        self.app.describe_record(None);self.app.plot();self.app.update_controls()
        self.app.status.set('已载入音频联合轨迹；电脑出声跟随回放，请先缓慢到首帧。')
        self.status.set('已应用到主窗口，尚未发送动作。主窗“④ 回放所选轴”将联动电脑音频。')

    def save(self,motion):
        data=compile_motion(self.project.data,self.profile) if motion else self.project.data
        name='第一部分.av.motion.json' if motion else '第一部分.av.project.json'
        path=filedialog.asksaveasfilename(parent=self.window,title='另存联合工程（连同音频素材）',initialfile=name,defaultextension='.json',filetypes=[('JSON','*.json')])
        if path:self.background(lambda:save_bundle(path,data),lambda _:self.status.set('已保存；移动文件时请带上旁边的 .assets 文件夹。'),'正在保存工程与音频素材…')

    def export_audio(self):
        if not any(c['kind']=='audio' for c in self.project.data['clips']):raise ValueError('请先导入音频。')
        path=filedialog.asksaveasfilename(parent=self.window,title='导出时间轴音频（不含实物通信等待）',initialfile='剪后音频.wav',defaultextension='.wav',filetypes=[('WAV','*.wav')])
        if path:self.background(lambda:export_wav(path,AudioTrack(self.project.data),duration(self.project.data)),lambda _:self.status.set('已导出时间轴音频；实物联动请使用联合回放文件。'),'正在导出音频…')

    def play_preview(self):
        if self.app.playing:raise ValueError('请先停止主窗口回放，再试听。')
        self.stop_preview();end=duration(self.project.data)
        if end<=0:raise ValueError('请先添加素材。')
        speed=float(self.preview_speed.get());self.preview_wall=time.monotonic()
        if self.preview_record:
            plan=playback_plan(self.preview_record,self.profile,self.project.data['selected'],speed)
            self.preview_times=plan.playback_times;self.source_times=plan.source_times
        else:self.preview_times=[0,end/speed];self.source_times=[0,end]
        import numpy as np
        if self.cursor>=end-.001:self.cursor=0
        self.preview_offset=float(np.interp(self.cursor,self.source_times,self.preview_times))
        track=AudioTrack(self.project.data)
        if track.clips:
            self.player=AudioPlayer(track);self.preview_wall=time.monotonic()
            self.player.preview(self.preview_times,self.source_times,self.preview_wall,self.preview_offset)
        self.previewing=True;self.status.set('正在离线试听：曲线与音频共用进度；不会连接或驱动舵机。');self.tick_preview(self.preview_generation)

    def tick_preview(self,generation):
        if not self.previewing or generation!=self.preview_generation or not self.window.winfo_exists():return
        if self.player and self.player.error:
            error=self.player.error;self.stop_preview();self.status.set(str(error));return
        import numpy as np
        t=time.monotonic()-self.preview_wall+self.preview_offset
        self.cursor=float(np.interp(t,self.preview_times,self.source_times));self.draw_cursor()
        if t>=self.preview_times[-1]:self.stop_preview();self.status.set('试听完成；未发送舵机命令。');return
        self.window.after(25,lambda:self.tick_preview(generation))

    def stop_preview(self):
        was_playing=self.previewing;self.previewing=False;self.preview_generation+=1
        if self.player:self.player.close();self.player=None
        if was_playing:self.status.set('试听已停止；播放头保留在当前位置。')

    def set_zoom(self,factor):self.zoom=max(1,min(16,self.zoom*factor));self.draw()

    def x_time(self,event):return min(duration(self.project.data),max(0,(self.canvas.canvasx(event.x)-75)/self.pixels_s))

    def mouse_down(self,event):
        if self.busy:return
        self.stop_preview();tags=self.canvas.gettags('current');ident=next((s[5:] for s in tags if s.startswith('clip:')),None)
        if ident:
            self.tree.selection_set(ident);c=next(c for c in self.project.data['clips'] if c['id']==ident)
            self.drag=(ident,self.canvas.canvasx(event.x),c['at_s'])
        else:self.cursor=self.x_time(event);self.draw_cursor()

    def mouse_move(self,event):
        if self.busy:return
        if self.drag:
            ident,x,at=self.drag;self.cursor=max(0,at+(self.canvas.canvasx(event.x)-x)/self.pixels_s)
            self.status.set(f'释放鼠标将片段移到 {self.cursor:.3f} 秒')
        else:self.cursor=self.x_time(event)
        self.draw_cursor()

    def mouse_up(self,event):
        if self.drag:
            ident,x,at=self.drag;self.drag=None
            target=round(max(0,at+(self.canvas.canvasx(event.x)-x)/self.pixels_s),3)
            self.run(lambda:self.project_edit(lambda:self.project.update(ident,at_s=target)))

    def draw_cursor(self):
        self.canvas.delete('playhead');x=75+self.cursor*self.pixels_s
        self.canvas.create_line(x,24,x,self.plot_height-12,fill='#bc4547',width=2,tags='playhead')
        self.clock_text.set(f'{format_time(self.cursor)} / {format_time(duration(self.project.data))}')

    def draw(self):
        c=self.canvas;c.delete('all');end=max(1,duration(self.project.data));w=max(900,c.winfo_width())*self.zoom
        h=max(220,c.winfo_height());self.plot_height=h;self.pixels_s=(w-100)/end;c.configure(scrollregion=(0,0,w,h))
        c.create_rectangle(0,0,w,30,fill='#edf2f6',outline='')
        for i in range(11):
            x=75+(w-100)*i/10;c.create_line(x,30,x,h,fill='#edf1f5');c.create_text(x,15,text=f'{end*i/10:.1f}s',fill='#526b7c')
        c.create_text(10,65,text='音频',anchor='w',fill='#1b7d7b');c.create_text(10,132,text='轨迹',anchor='w',fill='#526ac0')
        c.create_text(10,180,text='角度',anchor='w',fill='#526b7c')
        chosen=self.tree.selection()
        for clip in self.project.data['clips']:
            x=75+clip['at_s']*self.pixels_s;x2=75+clip_end(clip)*self.pixels_s
            top,bottom=(40,102) if clip['kind']=='audio' else (114,154)
            color='#d5efeb' if clip['kind']=='audio' else '#e1e6fa';tag='clip:'+clip['id']
            c.create_rectangle(x,top,x2,bottom,fill=color,outline='#245c72' if clip['id'] in chosen else '#b6c8d5',width=2 if clip['id'] in chosen else 1,tags=tag)
            c.create_text(x+5,top+10,text=clip['name'],anchor='w',fill='#234455',width=max(20,x2-x-10),tags=tag)
            if clip['kind']=='audio':
                asset=self.project.data['audio_sources'][clip['source_id']];peaks=asset.get('peaks',[])
                if peaks:
                    step=max(2,(x2-x)/600)
                    for px in range(0,max(1,int(x2-x)),max(1,int(step))):
                        t=clip['in_s']+px/self.pixels_s*clip['speed'];p=peaks[min(len(peaks)-1,int(t/asset['duration_s']*len(peaks)))]
                        c.create_line(x+px,79-p*19,x+px,79+p*19,fill='#278b85',tags=tag)
        if self.preview_record:
            rows=self.preview_record['samples'];rows=rows[::max(1,len(rows)//1500)]+[rows[-1]]
            span=max(self.profile.axes[n].span for n in self.project.data['selected'])
            for n in self.project.data['selected']:
                points=[]
                for r in rows:points.extend([75+r['t']*self.pixels_s,h-15-(h-185)*self.profile.axes[n].degrees(r['positions'][str(n)])/span])
                c.create_line(*points,fill=COLORS[n-1],width=1.5)
        self.draw_cursor()

    def close(self):
        if self.busy:self.status.set('正在处理文件，完成后即可关闭。');return
        self.stop_preview()
        try:self.autosave()
        except Exception as exc:messagebox.showerror('草稿未保存',str(exc),parent=self.window);return
        self.window.destroy();self.app.av_editor=None
