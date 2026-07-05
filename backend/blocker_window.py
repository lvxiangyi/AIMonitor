"""
System-level fullscreen blocker window using tkinter.
Uses a persistent tkinter thread to avoid Tcl_AsyncDelete crashes.
The window is hidden/shown rather than created/destroyed.
"""

import tkinter as tk
import threading
import requests
import os
import queue
import ctypes
from ctypes import wintypes

BACKEND_URL = "http://127.0.0.1:" + os.environ.get("FOCUSGUARD_PORT", "8899")

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _rect_tuple(rect: RECT):
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def _virtual_screen_rect():
    try:
        user32 = ctypes.windll.user32
        return (
            user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
        )
    except Exception:
        return (0, 0, 0, 0)


def _cursor_monitor_rect():
    try:
        user32 = ctypes.windll.user32
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            raise RuntimeError("GetCursorPos failed")
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise RuntimeError("GetMonitorInfoW failed")
        return _rect_tuple(info.rcMonitor)
    except Exception:
        virtual = _virtual_screen_rect()
        if virtual[2] > 0 and virtual[3] > 0:
            return virtual
        return (0, 0, 1024, 768)


def _centered_rect(container, width, height):
    left, top, container_width, container_height = container
    return (
        left + max(0, int((container_width - width) / 2)),
        top + max(0, int((container_height - height) / 2)),
        width,
        height,
    )


def _content_position(window_rect, monitor_rect):
    window_left, window_top, _, _ = window_rect
    monitor_left, monitor_top, monitor_width, monitor_height = monitor_rect
    return (
        monitor_left - window_left + int(monitor_width / 2),
        monitor_top - window_top + int(monitor_height / 2),
    )


def _force_window_rect(root, rect, activate=True):
    left, top, width, height = rect
    root.geometry(f"{width}x{height}+{left}+{top}")
    try:
        hwnd = wintypes.HWND(root.winfo_id())
        flags = SWP_NOZORDER
        if not activate:
            flags |= SWP_NOACTIVATE
        ctypes.windll.user32.SetWindowPos(hwnd, None, left, top, width, height, flags)
    except Exception:
        pass


class BlockerWindow:
    """Persistent tkinter-based fullscreen blocker with quiz."""

    def __init__(self):
        self._is_showing = False
        self._task = ""
        self._root = None
        self._content_frame = None
        self._result_label = None
        self._command_queue = queue.Queue()
        # Start persistent tkinter thread
        self._thread = threading.Thread(target=self._tk_thread, daemon=True)
        self._thread.start()

    def _tk_thread(self):
        """Persistent tkinter thread. Window lives here forever."""
        _enable_dpi_awareness()
        self._root = tk.Tk()
        self._root.withdraw()  # Start hidden
        self._root.configure(bg="#0f0f23")
        self._root.overrideredirect(True)
        try:
            self._root.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass

        # Force fullscreen covering the whole virtual desktop, including secondary monitors.
        rect = _virtual_screen_rect()
        if rect[2] <= 0 or rect[3] <= 0:
            rect = (0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        _force_window_rect(self._root, rect)
        self._root.attributes("-topmost", True)

        self._content_frame = tk.Frame(self._root, bg="#0f0f23")
        x, y = _content_position(rect, _cursor_monitor_rect())
        self._content_frame.place_forget()
        self._content_frame.place(x=x, y=y, anchor="center")

        # Process commands from queue periodically
        self._process_queue()
        self._root.mainloop()

    def _process_queue(self):
        """Check command queue every 100ms."""
        try:
            while not self._command_queue.empty():
                cmd = self._command_queue.get_nowait()
                cmd()
        except Exception as e:
            print(f"[blocker] UI command error: {e}")
        if self._root:
            self._root.after(100, self._process_queue)

    def show(self, task: str, activity: str, reason: str):
        """Show the blocker window with a quiz."""
        if self._is_showing:
            return
        self._is_showing = True
        self._task = task
        # Queue the show command to run on tkinter thread
        self._command_queue.put(lambda: self._do_show(task, activity, reason))

    def show_message(self, title: str, message: str):
        """Show a dismissible desktop message."""
        if self._is_showing:
            return
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_message(title, message))

    def show_flow_prompt(self, summary: dict):
        """Ask the user what to do after a completed work block."""
        if self._is_showing:
            return
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_flow_prompt(summary))

    def show_resume_prompt(self, payload: dict):
        """Ask the user to confirm returning to work after a break."""
        if self._is_showing:
            return
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_resume_prompt(payload))

    def dismiss(self):
        """Hide the blocker window."""
        if not self._is_showing:
            return
        self._is_showing = False
        self._command_queue.put(self._do_hide)

    @property
    def is_showing(self):
        return self._is_showing

    def _do_show(self, task, activity, reason):
        """Show window and load quiz (runs on tk thread)."""
        # Force fullscreen size again in case resolution changed.
        rect = _virtual_screen_rect()
        if rect[2] <= 0 or rect[3] <= 0:
            rect = (0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        monitor_rect = _cursor_monitor_rect()
        _force_window_rect(self._root, rect)
        x, y = _content_position(rect, monitor_rect)
        self._content_frame.place_forget()
        self._content_frame.place(x=x, y=y, anchor="center")
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._grab_modal()
        self._load_quiz(task, activity, reason)

    def _do_show_message(self, title, message):
        """Show a small dismissible message window (runs on tk thread)."""
        self._clear_content()
        width = 520
        height = 260
        rect = _centered_rect(_cursor_monitor_rect(), width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._grab_modal()

        frame = self._content_frame
        frame.place_forget()
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame,
            text=title,
            font=("Segoe UI", 20, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
            wraplength=460,
        ).pack(pady=(0, 14))
        tk.Label(
            frame,
            text=message,
            font=("Segoe UI", 12),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=460,
            justify="center",
        ).pack(pady=(0, 22))
        tk.Button(
            frame,
            text="知道了",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg="#4a9eff",
            activebackground="#2f80ed",
            activeforeground="#ffffff",
            relief="flat",
            padx=28,
            pady=8,
            cursor="hand2",
            command=self._message_dismiss,
        ).pack()

    def _message_dismiss(self):
        self._is_showing = False
        self._do_hide()

    def _do_show_flow_prompt(self, summary):
        """Render post-block options (runs on tk thread)."""
        self._clear_content()
        width = 680
        height = 560
        rect = _centered_rect(_cursor_monitor_rect(), width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._grab_modal()

        frame = self._content_frame
        frame.place_forget()
        frame.place(relx=0.5, rely=0.5, anchor="center")

        task = summary.get("task", "")
        duration = int(summary.get("duration_minutes") or 30)
        interval = int(summary.get("check_interval_seconds") or 30)
        focus_minutes = summary.get("focus_minutes", 0)
        distracted = summary.get("distracted_checks", 0)
        api_errors = summary.get("api_error_checks", 0)

        tk.Label(
            frame,
            text="Block 已结束",
            font=("Segoe UI", 22, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
        ).pack(pady=(0, 8))
        tk.Label(
            frame,
            text=f"{task}\n专注 {focus_minutes} 分钟，分心 {distracted} 次，AI 错误 {api_errors} 次。",
            font=("Segoe UI", 11),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=600,
            justify="center",
        ).pack(pady=(0, 16))

        error_label = tk.Label(frame, text="", font=("Segoe UI", 10), fg="#ff8a80", bg="#0f0f23", wraplength=560)
        error_label.pack(pady=(0, 8))

        continue_box = tk.Frame(frame, bg="#15172a", padx=14, pady=12)
        continue_box.pack(fill="x", pady=(0, 8))
        tk.Label(continue_box, text="1. 继续任务", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#15172a").pack(anchor="w")
        continue_task = tk.Entry(continue_box, font=("Segoe UI", 11), width=48, bg="#0f0f23", fg="#ffffff", insertbackground="#ffffff", relief="flat")
        continue_task.insert(0, task)
        continue_task.pack(fill="x", pady=(8, 8))
        duration_row = tk.Frame(continue_box, bg="#15172a")
        duration_row.pack(fill="x")
        tk.Label(duration_row, text="下一轮分钟", font=("Segoe UI", 10), fg="#cbd5e1", bg="#15172a").pack(side="left")
        continue_duration = tk.Entry(duration_row, font=("Segoe UI", 10), width=8, bg="#0f0f23", fg="#ffffff", insertbackground="#ffffff", relief="flat")
        continue_duration.insert(0, str(duration))
        continue_duration.pack(side="left", padx=(8, 12))
        tk.Button(
            duration_row,
            text="开始下一轮",
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg="#2ecc71",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=lambda: self._submit_continue(continue_task, continue_duration, interval, error_label),
        ).pack(side="right")

        break_box = tk.Frame(frame, bg="#15172a", padx=14, pady=12)
        break_box.pack(fill="x", pady=(0, 8))
        tk.Label(break_box, text="2. 休息一下", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#15172a").pack(anchor="w")
        break_row = tk.Frame(break_box, bg="#15172a")
        break_row.pack(fill="x", pady=(8, 8))
        tk.Label(break_row, text="休息分钟", font=("Segoe UI", 10), fg="#cbd5e1", bg="#15172a").pack(side="left")
        break_minutes = tk.Entry(break_row, font=("Segoe UI", 10), width=8, bg="#0f0f23", fg="#ffffff", insertbackground="#ffffff", relief="flat")
        break_minutes.insert(0, "10")
        break_minutes.pack(side="left", padx=(8, 12))
        break_activity = tk.Entry(break_box, font=("Segoe UI", 11), width=48, bg="#0f0f23", fg="#ffffff", insertbackground="#ffffff", relief="flat")
        break_activity.insert(0, "散步 / 喝水 / 放松")
        break_activity.pack(fill="x", pady=(0, 8))
        tk.Button(
            break_box,
            text="开始休息",
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg="#4a9eff",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=lambda: self._submit_break(break_minutes, break_activity, task, duration, interval, error_label),
        ).pack(anchor="e")

        pause_box = tk.Frame(frame, bg="#15172a", padx=14, pady=12)
        pause_box.pack(fill="x")
        tk.Label(pause_box, text="3. 暂停今天的学习", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#15172a").pack(anchor="w")
        pause_activity = tk.Entry(pause_box, font=("Segoe UI", 11), width=48, bg="#0f0f23", fg="#ffffff", insertbackground="#ffffff", relief="flat")
        pause_activity.insert(0, "接下来要做的活动")
        pause_activity.pack(fill="x", pady=(8, 8))
        tk.Button(
            pause_box,
            text="记录并暂停",
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg="#e74c3c",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=lambda: self._submit_pause_day(pause_activity, error_label),
        ).pack(anchor="e")

    def _do_show_resume_prompt(self, payload):
        """Render break-finished confirmation (runs on tk thread)."""
        self._clear_content()
        width = 560
        height = 320
        rect = _centered_rect(_cursor_monitor_rect(), width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._grab_modal()

        frame = self._content_frame
        frame.place_forget()
        frame.place(relx=0.5, rely=0.5, anchor="center")

        task = payload.get("task", "")
        activity = payload.get("activity", "")
        error_label = tk.Label(frame, text="", font=("Segoe UI", 10), fg="#ff8a80", bg="#0f0f23", wraplength=500)

        tk.Label(frame, text="休息结束", font=("Segoe UI", 22, "bold"), fg="#ffffff", bg="#0f0f23").pack(pady=(0, 10))
        tk.Label(
            frame,
            text=f"刚才休息：{activity}\n准备回到：{task}",
            font=("Segoe UI", 12),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=500,
            justify="center",
        ).pack(pady=(0, 16))
        error_label.pack(pady=(0, 8))
        tk.Button(
            frame,
            text="确认，开始下一轮",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg="#2ecc71",
            relief="flat",
            padx=24,
            pady=8,
            cursor="hand2",
            command=lambda: self._post_flow("/flow/resume", payload, error_label),
        ).pack()

    def _submit_continue(self, task_entry, duration_entry, interval, error_label):
        task = task_entry.get().strip()
        if not task:
            error_label.config(text="请输入要继续的任务。")
            return
        try:
            duration = int(duration_entry.get().strip())
            if duration <= 0:
                raise ValueError()
        except Exception:
            error_label.config(text="下一轮分钟需要是正整数。")
            return
        self._post_flow("/flow/continue", {
            "task": task,
            "duration_minutes": duration,
            "check_interval_seconds": interval,
        }, error_label)

    def _submit_break(self, minutes_entry, activity_entry, task, duration, interval, error_label):
        try:
            minutes = int(minutes_entry.get().strip())
            if minutes <= 0:
                raise ValueError()
        except Exception:
            error_label.config(text="休息分钟需要是正整数。")
            return
        activity = activity_entry.get().strip()
        if not activity:
            error_label.config(text="请输入休息方式。")
            return
        self._post_flow("/flow/break", {
            "break_minutes": minutes,
            "activity": activity,
            "task": task,
            "duration_minutes": duration,
            "check_interval_seconds": interval,
        }, error_label)

    def _submit_pause_day(self, activity_entry, error_label):
        activity = activity_entry.get().strip()
        if not activity:
            error_label.config(text="请输入接下来要做的活动。")
            return
        self._post_flow("/flow/pause-day", {"activity": activity}, error_label)

    def _post_flow(self, path, payload, error_label):
        error_label.config(text="")
        threading.Thread(target=lambda: self._do_post_flow(path, payload, error_label), daemon=True).start()

    def _do_post_flow(self, path, payload, error_label):
        try:
            res = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=10)
            if res.status_code >= 400:
                raise RuntimeError(res.text)
            self._command_queue.put(self._message_dismiss)
        except Exception as e:
            self._command_queue.put(lambda: error_label.config(text=f"操作失败：{e}"))

    def _do_hide(self):
        """Hide window (runs on tk thread)."""
        self._release_modal()
        self._clear_content()
        self._root.withdraw()

    def _grab_modal(self):
        try:
            self._root.grab_set_global()
        except Exception as e:
            print(f"[blocker] Could not grab input globally: {e}")

    def _release_modal(self):
        try:
            self._root.grab_release()
        except Exception:
            pass

    def _clear_content(self):
        """Clear all widgets from content frame."""
        for widget in self._content_frame.winfo_children():
            widget.destroy()

    def _load_quiz(self, task, activity, reason):
        """Show loading state then fetch quiz in background."""
        self._clear_content()
        frame = self._content_frame

        loading = tk.Label(frame, text="\u554f\u984c\u3092\u8aad\u307f\u8fbc\u307f\u4e2d...",
                           font=("Segoe UI", 18), fg="#4a9eff", bg="#0f0f23")
        loading.pack(pady=50)

        # Fetch quiz in background
        threading.Thread(
            target=self._fetch_and_render,
            args=(task, activity, reason),
            daemon=True,
        ).start()

    def _fetch_and_render(self, task, activity, reason):
        """Fetch quiz then queue render on tk thread."""
        quiz = self._fetch_quiz(task)
        self._command_queue.put(lambda: self._render_quiz(quiz, task, activity, reason))

    def _fetch_quiz(self, task: str) -> dict:
        """Fetch a quiz from the backend."""
        try:
            res = requests.get(f"{BACKEND_URL}/quiz/generate", params={"task": task}, timeout=15)
            return res.json()
        except Exception as e:
            print(f"[blocker] Quiz fetch error: {e}")
            return {
                "question": "\u96c6\u4e2d\u529b\u3092\u4fdd\u3064\u305f\u3081\u306b\u6700\u3082\u52b9\u679c\u7684\u306a\u65b9\u6cd5\u306f\uff1f",
                "options": ["\u30dd\u30e2\u30c9\u30fc\u30ed\u30fb\u30c6\u30af\u30cb\u30c3\u30af", "3\u6642\u9593\u9023\u7d9a\u4f5c\u696d", "SNS\u3092\u958b\u3044\u305f\u307e\u307e", "\u97f3\u697d\u3092\u5927\u97f3\u91cf\u3067"],
                "correct_index": 0,
                "explanation": "\u30dd\u30e2\u30c9\u30fc\u30ed\u30fb\u30c6\u30af\u30cb\u30c3\u30af\u306f\u79d1\u5b66\u7684\u306b\u52b9\u679c\u304c\u5b9f\u8a3c\u3055\u308c\u3066\u3044\u307e\u3059\u3002"
            }

    def _render_quiz(self, quiz, task, activity, reason):
        """Render quiz UI (runs on tk thread)."""
        self._clear_content()
        frame = self._content_frame

        # Title
        tk.Label(frame, text="\u26a0\ufe0f \u6c17\u304c\u6563\u3063\u3066\u3044\u307e\u3059\uff01\u554f\u984c\u306b\u7b54\u3048\u3066\u304f\u3060\u3055\u3044",
                 font=("Segoe UI", 24, "bold"), fg="#e74c3c", bg="#0f0f23").pack(pady=(0, 8))

        # Info
        info = f"\u30bf\u30b9\u30af\uff1a{task}"
        if activity and activity not in ("", "テストモード"):
            info += f"  |  \u691c\u51fa\uff1a{activity}"
        tk.Label(frame, text=info, font=("Segoe UI", 11), fg="#888", bg="#0f0f23").pack(pady=(0, 20))

        # Question
        tk.Label(frame, text=quiz.get("question", ""), font=("Segoe UI", 18, "bold"),
                 fg="#fff", bg="#0f0f23", wraplength=700).pack(pady=(0, 20))

        # Options
        options = quiz.get("options", [])
        correct_idx = quiz.get("correct_index", 0)
        labels = ["A", "B", "C", "D"]
        btn_frame = tk.Frame(frame, bg="#0f0f23")
        btn_frame.pack(pady=(0, 15))

        for i, opt in enumerate(options):
            tk.Button(
                btn_frame, text=f"  {labels[i]}.  {opt}",
                font=("Segoe UI", 14), fg="#fff", bg="#2a2a4a",
                activebackground="#3a3a5a", activeforeground="#fff",
                relief="flat", anchor="w", width=50, pady=10, padx=15, cursor="hand2",
                command=lambda idx=i: self._on_answer(idx, correct_idx, quiz, task),
            ).pack(pady=3)

        # Result
        self._result_label = tk.Label(frame, text="", font=("Segoe UI", 14), fg="#fff", bg="#0f0f23", wraplength=600)
        self._result_label.pack(pady=(10, 0))

        # Dispute
        tk.Button(frame, text="\u7570\u8b70\u3042\u308a\uff08\u5b9f\u306f\u96c6\u4e2d\u3057\u3066\u3044\u308b\uff09",
                  font=("Segoe UI", 10), fg="#4a9eff", bg="#0f0f23",
                  activebackground="#0f0f23", activeforeground="#4a9eff",
                  relief="flat", cursor="hand2",
                  command=lambda: self._show_dispute(frame, task)).pack(pady=(15, 0))

        # TEMP: Close button for testing
        tk.Button(frame, text="[DEBUG] \u9589\u3058\u308b",
                  font=("Segoe UI", 9), fg="#666", bg="#0f0f23",
                  activebackground="#0f0f23", activeforeground="#999",
                  relief="flat", cursor="hand2",
                  command=self._correct_dismiss).pack(pady=(10, 0))

    def _on_answer(self, selected_idx, correct_idx, quiz, task):
        """Handle answer (runs on tk thread)."""
        options = quiz.get("options", [])
        explanation = quiz.get("explanation", "")

        if selected_idx == correct_idx:
            self._result_label.config(text=f"\u2705 \u6b63\u89e3\uff01 {explanation}", fg="#2ecc71")
            # Hide after 1.5s
            self._root.after(1500, self._correct_dismiss)
        else:
            user_ans = options[selected_idx] if selected_idx < len(options) else "?"
            correct_ans = options[correct_idx] if correct_idx < len(options) else "?"
            self._result_label.config(
                text=f"\u274c \u4e0d\u6b63\u89e3\u3002\u6b63\u89e3\u306f\u300c{correct_ans}\u300d\u3002{explanation}\n\n\u6b21\u306e\u554f\u984c\u3078...",
                fg="#e74c3c",
            )
            # Record wrong
            threading.Thread(
                target=self._record_wrong,
                args=(quiz.get("question", ""), user_ans, correct_ans, task),
                daemon=True,
            ).start()
            # New question after 3s
            self._root.after(3000, lambda: self._load_quiz(task, "", ""))

    def _correct_dismiss(self):
        """Correct answer: hide and acknowledge."""
        self._is_showing = False
        self._do_hide()
        threading.Thread(target=self._call_acknowledge, daemon=True).start()

    def _record_wrong(self, question, user_ans, correct_ans, task):
        try:
            requests.post(f"{BACKEND_URL}/quiz/wrong",
                          json={"question": question, "user_answer": user_ans,
                                "correct_answer": correct_ans, "task": task}, timeout=5)
        except Exception:
            pass

    def _call_acknowledge(self):
        try:
            requests.post(f"{BACKEND_URL}/session/acknowledge", json={}, timeout=5)
        except Exception:
            pass

    def _show_dispute(self, parent_frame, task):
        """Show dispute input."""
        d_frame = tk.Frame(parent_frame, bg="#0f0f23")
        d_frame.pack(pady=(10, 0))

        entry = tk.Entry(d_frame, font=("Segoe UI", 12), width=40,
                         bg="#1a1a2e", fg="#fff", insertbackground="#fff",
                         relief="flat", highlightthickness=1, highlightcolor="#4a9eff")
        entry.pack(side="left", padx=(0, 8))
        entry.focus_set()

        result_lbl = tk.Label(parent_frame, text="", font=("Segoe UI", 11), fg="#aaa", bg="#0f0f23", wraplength=500)
        result_lbl.pack(pady=(5, 0))

        def submit():
            reason = entry.get().strip()
            if not reason:
                return
            result_lbl.config(text="AI\u8a55\u4fa1\u4e2d...", fg="#4a9eff")
            threading.Thread(target=lambda: self._do_dispute(reason, result_lbl), daemon=True).start()

        tk.Button(d_frame, text="\u9001\u4fe1", font=("Segoe UI", 12, "bold"),
                  fg="#fff", bg="#4a9eff", relief="flat", padx=15, pady=5, cursor="hand2",
                  command=submit).pack(side="left")

    def _do_dispute(self, reason, result_lbl):
        try:
            res = requests.post(f"{BACKEND_URL}/session/dispute", json={"reason": reason}, timeout=30)
            result = res.json()
            if result.get("accepted"):
                self._command_queue.put(lambda: result_lbl.config(text="\u2705 \u7570\u8b70\u304c\u8a8d\u3081\u3089\u308c\u307e\u3057\u305f", fg="#2ecc71"))
                self._command_queue.put(lambda: self._root.after(1500, self._correct_dismiss))
            else:
                msg = f"\u274c \u5374\u4e0b: {result.get('ai_reason', '')}"
                self._command_queue.put(lambda: result_lbl.config(text=msg, fg="#e74c3c"))
        except Exception as e:
            self._command_queue.put(lambda: result_lbl.config(text=f"Error: {e}", fg="#e74c3c"))


class _NoopBlocker:
    is_showing = False

    def show(self, *args, **kwargs):
        self.is_showing = True

    def show_message(self, *args, **kwargs):
        self.is_showing = True

    def show_flow_prompt(self, *args, **kwargs):
        self.is_showing = True

    def show_resume_prompt(self, *args, **kwargs):
        self.is_showing = True

    def dismiss(self):
        self.is_showing = False


# Singleton - starts the persistent tk thread immediately unless tests opt out.
if os.getenv("AIMONITOR_NO_BLOCKER_SINGLETON") == "1":
    blocker = _NoopBlocker()
else:
    blocker = BlockerWindow()
