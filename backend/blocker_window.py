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

BACKEND_URL = "http://127.0.0.1:" + os.environ.get("FOCUSGUARD_PORT", "8899")


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
        self._root = tk.Tk()
        self._root.withdraw()  # Start hidden
        self._root.configure(bg="#0f0f23")
        self._root.overrideredirect(True)

        # Force fullscreen covering entire screen
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        self._root.geometry(f"{screen_w}x{screen_h}+0+0")
        self._root.attributes("-topmost", True)

        self._content_frame = tk.Frame(self._root, bg="#0f0f23")
        self._content_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Process commands from queue periodically
        self._process_queue()
        self._root.mainloop()

    def _process_queue(self):
        """Check command queue every 100ms."""
        try:
            while not self._command_queue.empty():
                cmd = self._command_queue.get_nowait()
                cmd()
        except Exception:
            pass
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
        # Force fullscreen size again in case resolution changed
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        self._root.geometry(f"{screen_w}x{screen_h}+0+0")
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._load_quiz(task, activity, reason)

    def _do_hide(self):
        """Hide window (runs on tk thread)."""
        self._clear_content()
        self._root.withdraw()

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


# Singleton - starts the persistent tk thread immediately
blocker = BlockerWindow()
