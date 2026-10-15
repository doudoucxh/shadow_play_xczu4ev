"""Attended story-start panel. Opening this window never connects hardware."""
from __future__ import annotations

import argparse
import itertools
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

TARGET = [1470, 1212, 1425, 1514, 1416, 1740, 1730, 1250, 1770, 1740]


class StoryStartPanel:
    def __init__(self, root):
        self.root = root
        self.session = None
        self.connected = False
        self.closing = False
        self.busy = False
        self.generation = 0
        self.jobs = queue.PriorityQueue()
        self.results = queue.Queue()
        self.counter = itertools.count()
        self.last_status = {}
        self.last_status_summary = None
        self.poll_inflight = False
        self.port = tk.StringVar(value="COM3")
        self.state_text = tk.StringVar(value="未连接；打开窗口不会发送指令")
        self.plan_text = tk.StringVar(value="未加载审核计划")
        root.title("皮影 · 剧本起势控制")
        root.geometry("940x720")
        bar = ttk.Frame(root, padding=12)
        bar.pack(fill="x")
        ttk.Label(bar, text="PS 串口").pack(side="left")
        self.port_box = ttk.Combobox(bar, textvariable=self.port, values=[f"COM{i}" for i in range(1, 33)], width=10)
        self.port_box.pack(side="left", padx=8)
        self.connect_button = ttk.Button(bar, text="连接", command=self.connect)
        self.connect_button.pack(side="left", padx=4)
        self.disconnect_button = ttk.Button(bar, text="断开", command=self.disconnect)
        self.disconnect_button.pack(side="left", padx=4)
        self.refresh_button = ttk.Button(bar, text="读取状态", command=lambda: self.submit("status"))
        self.refresh_button.pack(side="left", padx=4)
        ttk.Label(root, textvariable=self.state_text, wraplength=900, padding=10).pack(fill="x")
        ttk.Label(root, text="下表均为 PWM 指令脉宽（μs），不是实测角度反馈。目标仅供预览，不能直接发送。", padding=10).pack(fill="x")
        self.table = ttk.Treeview(root, columns=("axis", "current", "target"), show="headings", height=10)
        for column, title in zip(("axis", "current", "target"), ("舵机", "当前指令 μs（非反馈）", "剧本起势参考 μs")):
            self.table.heading(column, text=title)
            self.table.column(column, anchor="center", width=220)
        for i, value in enumerate(TARGET, 1):
            self.table.insert("", "end", iid=str(i), values=(i, "未知", value))
        self.table.pack(fill="x", padx=12)
        actions = ttk.Frame(root, padding=12)
        actions.pack(fill="x")
        self.load_button = ttk.Button(actions, text="加载已审核 JSON", command=self.load_plan)
        self.load_button.pack(side="left", padx=4)
        ttk.Button(actions, text="预览起势", command=self.preview).pack(side="left", padx=4)
        self.start_button = ttk.Button(actions, text="启动审核路线", command=lambda: self.submit("start"))
        self.start_button.pack(side="left", padx=4)
        self.stop_button = tk.Button(actions, text="停止 PWM", bg="#bc2028", fg="white", font=("Microsoft YaHei UI", 12, "bold"), command=self.stop)
        self.stop_button.pack(side="right", padx=4)
        ttk.Label(root, textvariable=self.plan_text, wraplength=900, padding=8).pack(fill="x")
        ttk.Label(root, text="停止 PWM 不等于切断 8V 电源；机械异常时由现场人员切断独立电源。", padding=8).pack(fill="x")
        self.log = tk.Text(root, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=8)
        root.protocol("WM_DELETE_WINDOW", self.shutdown)
        threading.Thread(target=self.worker, daemon=True).start()
        self.refresh_controls()
        root.after(80, self.drain)
        root.after(500, self.poll_status)

    def append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S} {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_controls(self):
        available = self.connected and not self.busy and not self.closing
        self.connect_button.configure(state="normal" if not self.connected and not self.busy and not self.closing else "disabled")
        self.port_box.configure(state="disabled" if self.connected or self.busy else "normal")
        for widget in (self.refresh_button, self.load_button):
            widget.configure(state="normal" if available else "disabled")
        self.disconnect_button.configure(state="normal" if self.connected and not self.closing else "disabled")
        self.start_button.configure(state="normal" if available and self.last_status.get("ready") is True and not self.last_status.get("running") else "disabled")
        self.stop_button.configure(state="normal" if self.connected and not self.closing else "disabled")

    def submit(self, action, data=None, priority=10):
        if self.closing and action != "shutdown":
            return
        if action == "start" and (self.busy or self.last_status.get("ready") is not True):
            return
        self.busy = True
        self.refresh_controls()
        self.jobs.put((priority, next(self.counter), self.generation, action, data))

    def connect(self):
        self.submit("connect", self.port.get().strip())

    def poll_status(self):
        if self.connected and not self.busy and not self.closing and not self.poll_inflight:
            self.poll_inflight = True
            # Polls share the serial worker, but never disable the stop control.
            self.submit("poll_status", priority=20)
        if not self.closing:
            self.root.after(500, self.poll_status)

    def stop(self):
        # Invalidate queued commands; a request already inside the session must
        # obey the backend's bounded I/O timeout before this stop can execute.
        self.generation += 1
        self.poll_inflight = False
        self.submit("stop", priority=0)
        self.append("停止请求已优先排队；尚未确认停输出。")

    def disconnect(self):
        self.generation += 1
        self.poll_inflight = False
        self.submit("disconnect", priority=0)

    def shutdown(self):
        if self.closing:
            return
        self.generation += 1
        self.poll_inflight = False
        self.closing = True
        self.submit("shutdown", priority=-1)

    def load_plan(self):
        path = filedialog.askopenfilename(title="选择已审核路线", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            plan = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if not isinstance(plan, dict):
                raise ValueError("计划必须是 JSON 对象")
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))
            return
        self.plan_text.set(f"待后端审核：{path}")
        self.submit("load_plan", plan)

    def preview(self):
        messagebox.showinfo("起势预览（不发送）", "武松左下、手收低；老虎右下树下。\n\n十路参考 μs：\n" + ", ".join(map(str, TARGET)) + "\n\n这只是目标指令，不证明当前机械位置。实际启动仅执行后端批准的路线。")

    def worker(self):
        while True:
            _, _, generation, action, data = self.jobs.get()
            if generation != self.generation:
                continue
            try:
                result = None
                if action == "connect":
                    from story_start_session import StoryStartSession
                    log_dir = Path(__file__).resolve().parents[1] / "logs" / "story_start"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    self.session = StoryStartSession(data, log_dir / f"session-{datetime.now():%Y%m%d-%H%M%S-%f}.jsonl")
                    result = self.session.status()
                elif action in ("disconnect", "shutdown"):
                    if self.session is not None:
                        try:
                            result = self.session.stop()
                        finally:
                            self.session.close()
                            self.session = None
                else:
                    if self.session is None:
                        raise RuntimeError("尚未连接")
                    method = "status" if action == "poll_status" else action
                    result = getattr(self.session, method)(data) if action == "load_plan" else getattr(self.session, method)()
                    if method != "status":
                        result = {"operation": result, "status": self.session.status()}
                self.results.put((generation, action, result, None))
            except Exception as exc:
                self.results.put((generation, action, None, str(exc)))
            if action == "shutdown":
                return

    def drain(self):
        while True:
            try:
                generation, action, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            if action == "shutdown":
                if error:
                    messagebox.showwarning("停止未确认", f"{error}\n请现场确认输出并按需切断8V电源。")
                self.root.destroy()
                return
            if generation != self.generation:
                continue
            if action == "poll_status":
                self.poll_inflight = False
            self.busy = False
            self.connected = self.session is not None
            if error:
                self.last_status = {}
                self.state_text.set("操作失败：" + error)
                summary = ("error", error)
                if action != "poll_status" or summary != self.last_status_summary:
                    self.append(f"{action} 失败：{error}")
                self.last_status_summary = summary
            else:
                status = result.get("status", result) if isinstance(result, dict) else {}
                # Sequence/pulses change continually during motion. Keep the
                # table current without flooding the log at the polling rate.
                pwm = status.get("pwm_state", {}) or {}
                summary = json.dumps({key: status.get(key) for key in ("ready", "running", "blocked_reasons", "plan_loaded")}, ensure_ascii=False, sort_keys=True)
                summary += json.dumps({key: pwm.get(key) for key in ("armed", "enabled_mask", "faults")}, sort_keys=True)
                if action != "poll_status" or summary != self.last_status_summary:
                    self.append(f"{action}: {json.dumps(result, ensure_ascii=False, default=str)}")
                self.last_status_summary = summary
                self.last_status = status
                reasons = status.get("blocked_reasons", [])
                self.state_text.set(("已断开" if not self.connected else "运行中" if status.get("running") else "可启动" if status.get("ready") else "启动受限") + ("；" + "；".join(map(str, reasons)) if reasons else ""))
                if action == "load_plan":
                    self.plan_text.set("后端已加载计划" if status.get("plan_loaded") else "后端未接受计划")
                pulses = status.get("pwm_state", {}).get("pulse_us", []) or []
                for i, target in enumerate(TARGET, 1):
                    self.table.item(str(i), values=(i, pulses[i-1] if len(pulses) >= i else "未知", target))
            self.refresh_controls()
        self.root.after(80, self.drain)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    StoryStartPanel(root)
    if args.smoke_test:
        root.update()
        root.destroy()
        print("UI_SMOKE_OK no hardware connection")
    else:
        root.mainloop()


if __name__ == "__main__":
    main()
