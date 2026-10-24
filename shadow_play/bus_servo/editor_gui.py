"""Pose and clip editing window. Editing/preview never sends motion commands."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from uuid import uuid4

from .editing import EditProject, PROJECT_SCHEMA, compile_project
from .model import save_recording

COLORS = ['#26a69a', '#5477d4', '#db9239', '#d85c74', '#8a69d2', '#639d49', '#d16635', '#4d9aba', '#b477b0', '#a19a35']


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 64*1024*1024:
        raise ValueError('文件超过64MB，请拆分工程。')
    return json.loads(path.read_text(encoding='utf-8-sig'))


class EditorWindow:
    def __init__(self, app, directory):
        self.app, self.profile, self.directory = app, app.profile, Path(directory)
        self.project = EditProject(self.profile, app.numbers())
        if app.record and app.record.get('complete'):
            self.project.add_recording(app.record, '主窗口轨迹')
        self.pending = False; self.replace_index = None; self.preview = None
        self.draft_path = self.directory/('edit_'+uuid4().hex+'.project.json')
        self.window = tk.Toplevel(app.root); self.window.title('皮影 · 分步录入与轨迹剪辑')
        self.window.geometry('1160x790'); self.window.minsize(1020, 740)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda e: app.stop())
        body = ttk.Frame(self.window, padding=14); body.pack(fill='both', expand=True)
        ttk.Label(body, text='分步录入与轨迹剪辑', font=('Microsoft YaHei UI', 18, 'bold')).pack(anchor='w')
        self.info = tk.StringVar(); ttk.Label(body, textvariable=self.info).pack(anchor='w', pady=(3, 6))
        self.edit_controls = []
        def bar():
            row = ttk.Frame(body); row.pack(fill='x', pady=3); return row
        def button(parent, label, action):
            b = ttk.Button(parent, text=label, command=lambda: self.run(action)); b.pack(side='left', padx=(0, 5))
            self.edit_controls.append(b); return b
        row = bar()
        button(row, '新建（主窗选轴）', self.new)
        button(row, '打开工程…', self.open_project)
        button(row, '另存工程…', lambda: self.save(False))
        button(row, '导入轨迹…', self.import_recordings)
        button(row, '添加主窗口轨迹', self.add_current)
        self.undo_button = button(row, '撤销', lambda: self.history(False))
        self.redo_button = button(row, '重做', lambda: self.history(True))
        row = bar()
        self.release_button = button(row, '① 卸力摆姿势', self.release)
        self.capture_button = button(row, '② 录入当前姿势', lambda: self.capture(False))
        self.replace_button = button(row, '重新录入选中姿势', lambda: self.capture(True))
        self.drag_button = button(row, '模拟拖到主窗目标', self.drag)
        ttk.Label(row, text='录入时只读新反馈；预览不驱动舵机。', foreground='#526b7c').pack(side='left', padx=6)
        # Reserve the output/stop controls before the flexible table and plot.
        footer = ttk.Frame(body); footer.pack(side='bottom', fill='x', pady=(4,0))
        row = ttk.Frame(footer); row.pack(fill='x')
        button(row, '检查并预览', self.check_preview)
        button(row, '应用到主窗口', self.apply_motion)
        button(row, '另存回放轨迹…', lambda: self.save(True))
        tk.Button(row, text='停止全部 / Esc', bg='#b84443', fg='white', relief='flat', command=app.stop, padx=15, pady=4).pack(side='right')
        self.status = tk.StringVar(value='编辑副本；原始录制不覆盖。修改会自动保存到本地草稿。')
        ttk.Label(footer, textvariable=self.status, foreground='#25566a', wraplength=1090).pack(fill='x', pady=(3,0))
        table = ttk.Frame(body); table.pack(fill='both', expand=True, pady=5)
        self.tree = ttk.Treeview(table, columns=('type','name','range','speed','transition','hold','source'), show='tree headings', height=7, selectmode='browse')
        self.tree.heading('#0', text='顺序'); self.tree.column('#0', width=52, stretch=False)
        columns = [('type','类型',70),('name','片段 / 姿势名称',185),('range','素材入点–出点 / s',180),('speed','倍率',60),('transition','移入 / s',75),('hold','停留 / s',75),('source','来源',90)]
        for key, label, width in columns:
            self.tree.heading(key, text=label); self.tree.column(key, width=width, stretch=key=='name')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview); scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set); self.tree.bind('<<TreeviewSelect>>', self.selected)
        row = bar()
        button(row, '上移', lambda: self.reorder(-1)); button(row, '下移', lambda: self.reorder(1))
        button(row, '复制', self.duplicate); button(row, '删除整段', self.delete)
        self.pose_text = tk.StringVar(value='选择一行查看原始姿势或片段参数。')
        ttk.Label(row, textvariable=self.pose_text, foreground='#526b7c', wraplength=650).pack(side='left', padx=8)
        self.fields = {key: tk.StringVar() for key in ('name','start_s','end_s','speed','transition_s','hold_s')}
        self.entries = {}
        row = bar()
        for key, label, width in [('name','名称',17),('start_s','入点/s',7),('end_s','出点/s',7),('speed','倍率',5),('transition_s','移入/s',6),('hold_s','停留/s',6)]:
            ttk.Label(row, text=label).pack(side='left', padx=(0, 3))
            e = ttk.Entry(row, textvariable=self.fields[key], width=width); e.pack(side='left', padx=(0, 8)); self.entries[key] = e
        button(row, '应用参数 / 裁剪', self.apply_properties)
        row = bar()
        self.cut_start, self.cut_end = tk.StringVar(value='0'), tk.StringVar(value='1')
        ttk.Label(row, text='区间（原素材秒）').pack(side='left', padx=(0, 5))
        ttk.Entry(row, textvariable=self.cut_start, width=8).pack(side='left')
        ttk.Label(row, text='至').pack(side='left', padx=5)
        ttk.Entry(row, textvariable=self.cut_end, width=8).pack(side='left', padx=(0, 8))
        button(row, '在起点分割', self.split)
        button(row, '删除此区间', self.remove_range)
        ttk.Label(row, text='拼接过渡自动限速；首段移入时间忽略，回放前单独到首帧。', foreground='#526b7c').pack(side='left', padx=6)
        self.canvas = tk.Canvas(body, height=135, background='white', highlightthickness=1, highlightbackground='#dce4eb')
        self.canvas.pack(fill='both', expand=True, pady=7); self.canvas.bind('<Configure>', lambda e: self.plot())
        self.refresh(); self.run(self.autosave)

    def run(self, action):
        try:
            if self.pending: raise RuntimeError('正在读取姿势，请等待本次反馈。')
            return action()
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror('操作未完成', str(exc), parent=self.window)

    def index(self):
        chosen = self.tree.selection()
        if not chosen: raise ValueError('请先选择一行。')
        return int(chosen[0])

    def autosave(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        # This UUID draft belongs only to this window; source files are never replaced.
        temporary = self.directory/('pending_'+uuid4().hex+'.json')
        save_recording(temporary, self.project.data)
        temporary.replace(self.draft_path)

    def changed(self, select=None):
        self.preview = None; self.refresh(select); self.autosave()
        self.status.set('草稿已保存：'+str(self.draft_path))

    def refresh(self, select=None):
        previous = self.tree.selection()
        if select is None and previous: select = int(previous[0])
        self.tree.delete(*self.tree.get_children())
        d = self.project.data
        for i, s in enumerate(d['segments']):
            source = d['sources'][s['source_id']]
            span = '—' if s['kind']=='pose' else f'{s["start_s"]:.3f} – {s["end_s"]:.3f}'
            self.tree.insert('', 'end', iid=str(i), text=str(i+1), values=(
                '姿势' if s['kind']=='pose' else '录制', s['name'], span,
                s.get('speed','—'), s['transition_s'], s.get('hold_s','—'), '模拟' if source['source']=='simulation' else '实测素材'))
        self.info.set('工程轴：'+', '.join(map(str,d['selected']))+f'   ·   {len(d["segments"])} 个姿势/片段   ·   模拟素材不能用于实机回放')
        if d['segments']:
            i = min(select if select is not None else len(d['segments'])-1, len(d['segments'])-1)
            self.tree.selection_set(str(max(0,i))); self.tree.see(str(max(0,i)))
        self.selected(); self.sync_controls(); self.plot()

    def selected(self, event=None):
        chosen = self.tree.selection()
        s = self.project.data['segments'][int(chosen[0])] if chosen else None
        for key, var in self.fields.items(): var.set(str(s.get(key,'')) if s else '')
        for key, entry in self.entries.items():
            entry.configure(state='normal' if s and key in s and not self.pending else 'disabled')
        if s and s['kind']=='pose':
            p = self.project.data['sources'][s['source_id']]['positions']
            self.pose_text.set('  '.join(f'{n}号 {self.profile.axes[n].degrees(p[str(n)]):.1f}°' for n in self.project.data['selected']))
        else:
            self.pose_text.set('入点/出点按原素材时间；倍率只影响这一片段。' if s else '选择一行编辑参数。')

    def sync_controls(self):
        for b in self.edit_controls: b.configure(state='disabled' if self.pending else 'normal')
        live = self.app.connected and not self.app.busy and not self.app.recording and not self.app.playing and not self.app.closing and not self.pending
        for b in (self.release_button,self.capture_button,self.replace_button): b.configure(state='normal' if live else 'disabled')
        self.drag_button.configure(state='normal' if live and self.app.mode.get()=='离线模拟' else 'disabled')
        self.undo_button.configure(state='normal' if self.project.undo_stack and not self.pending else 'disabled')
        self.redo_button.configure(state='normal' if self.project.redo_stack and not self.pending else 'disabled')

    def guard_device(self, motion=False):
        if not self.app.connected or self.app.busy or self.app.recording or self.app.playing or self.app.closing:
            raise RuntimeError('请先在主窗口连接，并结束连续录制/回放。')
        if motion: self.app.check_operator()

    def release(self):
        self.guard_device(True); self.app.send('release', self.project.data['selected'][:])
        self.status.set('已请求所选轴卸力；扶稳机构后摆好姿势，再点录入。')

    def drag(self):
        self.guard_device()
        if self.app.mode.get()!='离线模拟': raise RuntimeError('此功能只用于模拟。')
        targets = {str(n): self.profile.axes[n].position(self.app.targets[n].get()) for n in self.project.data['selected']}
        self.app.send('drag', targets)

    def capture(self, replace):
        self.guard_device()
        index = self.index() if replace else None
        if replace and self.project.data['segments'][index]['kind']!='pose':
            raise ValueError('请选择要重新录入的姿势行。')
        self.replace_index = index; self.pending = True; self.sync_controls()
        self.app.send('capture_pose', self.project.data['selected'][:])
        self.status.set('正在读取所选轴的新鲜位置反馈…')

    def accept_pose(self, pose):
        if not self.pending: return
        self.pending = False
        def accept():
            if self.replace_index is None:
                self.project.add_pose(pose); selected = len(self.project.data['segments'])-1
            else:
                self.project.replace_pose(self.replace_index,pose); selected = self.replace_index
            self.changed(selected)
        self.run(accept); self.sync_controls()

    def cancel_capture(self):
        self.pending = False; self.sync_controls()

    def new(self):
        fresh = EditProject(self.profile, self.app.numbers())
        self.autosave(); self.project = fresh
        self.draft_path = self.directory/('edit_'+uuid4().hex+'.project.json'); self.changed()

    def open_project(self):
        path = filedialog.askopenfilename(parent=self.window,title='打开编辑工程',filetypes=[('编辑工程','*.json')])
        if not path: return
        data = read_json(path)
        if data.get('schema') != PROJECT_SCHEMA: raise ValueError('这不是编辑工程；录制或回放文件请用“导入轨迹”。')
        fresh = EditProject(self.profile,data=data)
        self.autosave(); self.project = fresh
        self.draft_path = self.directory/('edit_'+uuid4().hex+'.project.json'); self.changed()

    def import_recordings(self):
        paths = filedialog.askopenfilenames(parent=self.window,title='导入轨迹（按选择顺序追加）',filetypes=[('轨迹文件','*.json')])
        for path in paths:
            self.project.add_recording(read_json(path),Path(path).stem[:120]); self.changed(len(self.project.data['segments'])-1)

    def add_current(self):
        if not self.app.record: raise ValueError('主窗口尚无完整轨迹。')
        self.project.add_recording(self.app.record,'主窗口轨迹'); self.changed(len(self.project.data['segments'])-1)

    def apply_properties(self):
        i = self.index(); s = self.project.data['segments'][i]
        keys = ('transition_s','hold_s') if s['kind']=='pose' else ('start_s','end_s','speed','transition_s')
        values = {key:float(self.fields[key].get()) for key in keys}; values['name'] = self.fields['name'].get().strip()
        self.project.update(i,**values); self.changed(i)

    def reorder(self, delta):
        i = self.index(); destination = i+delta
        if not 0 <= destination < len(self.project.data['segments']): return
        self.project.move(i,destination); self.changed(destination)

    def duplicate(self):
        i = self.index(); self.project.duplicate(i); self.changed(i+1)

    def delete(self):
        i = self.index(); self.project.delete(i); self.changed(i)

    def split(self):
        i = self.index(); self.project.split(i,float(self.cut_start.get())); self.changed(i)

    def remove_range(self):
        i = self.index(); self.project.remove_range(i,float(self.cut_start.get()),float(self.cut_end.get())); self.changed(i)

    def history(self, redo):
        (self.project.redo if redo else self.project.undo)(); self.changed()

    def check_preview(self):
        self.preview = None; self.plot()
        self.preview = compile_project(self.project.data,self.profile); self.plot()
        extended = [str(s['index']+1) for s in self.preview['segments_summary'] if s['extended']]
        self.status.set(f'检查通过 · {self.preview["samples"][-1]["t"]:.3f}秒 / {len(self.preview["samples"])}帧 · '+
                        ('自动延长移入过渡：第'+', '.join(extended)+'段' if extended else '过渡时间满足速度限制')+'。预览没有发运动指令。')
        return self.preview

    def apply_motion(self):
        if self.app.busy or self.app.recording or self.app.playing or self.app.closing:
            raise RuntimeError('请先结束主窗口当前操作。')
        record = self.check_preview()
        self.app.record = record; self.app.live_samples = []; self.app.select(record['selected'])
        self.app.describe_record(None); self.app.plot(); self.app.update_controls()
        self.app.status.set('已载入编辑后的动作；请先缓慢到首帧，再回放。')
        self.status.set('已应用到主窗口，未发运动指令。回到主窗口执行首帧准备和回放。')

    def save(self, motion):
        data = self.check_preview() if motion else self.project.data
        name = '第一部分.motion.json' if motion else '第一部分.project.json'
        path = filedialog.asksaveasfilename(parent=self.window,title='另存副本（不覆盖原文件）',defaultextension='.json',initialfile=name,filetypes=[('JSON','*.json')])
        if path: save_recording(path,data); self.status.set('已保存：'+path)

    def plot(self):
        c = self.canvas; c.delete('all'); w=max(300,c.winfo_width()); h=max(80,c.winfo_height())
        if not self.preview:
            c.create_text(w/2,h/2,text='编辑后点“检查并预览”查看合成轨迹；原始反馈保存在工程内。',fill='#7c8b9b'); return
        rows=self.preview['samples']; end=rows[-1]['t']; span=max(self.profile.axes[n].span for n in self.project.data['selected'])
        left,right,top,bottom=40,w-20,18,h-25
        for deg in range(0,span+1,90):
            y=bottom-(bottom-top)*deg/span
            c.create_line(left,y,right,y,fill='#edf1f5'); c.create_text(left-7,y,text=str(deg),anchor='e',fill='#7c8b9b')
        for n in self.project.data['selected']:
            points=[]
            drawn=rows[::max(1,len(rows)//1000)]
            if drawn[-1] is not rows[-1]: drawn=drawn+[rows[-1]]
            for r in drawn:
                points.extend([left+(right-left)*r['t']/end,bottom-(bottom-top)*self.profile.axes[n].degrees(r['positions'][str(n)])/span])
            if len(points)>=4: c.create_line(*points,fill=COLORS[n-1],width=2)
        for s in self.preview['segments_summary'][1:]:
            x=left+(right-left)*s['start_s']/end; c.create_line(x,top,x,bottom,fill='#c9d4de',dash=(3,3))
        c.create_text(left,bottom+14,text='0s',fill='#7c8b9b'); c.create_text(right,bottom+14,text=f'{end:.2f}s',anchor='e',fill='#7c8b9b')

    def close(self):
        if self.pending:
            self.status.set('等待这次姿势反馈后再关闭；Esc仍可停止全部。'); return
        try:
            self.autosave()
        except Exception as exc:
            messagebox.showerror('草稿尚未保存',str(exc),parent=self.window); return
        self.window.destroy(); self.app.editor = None
