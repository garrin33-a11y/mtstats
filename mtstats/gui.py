"""Небольшое окно управления (tkinter) и выбор папки через системный диалог.

Окно живёт в главном потоке, HTTP-сервер — в фоновом, поэтому диалог выбора
папки запрашивается через очереди: сервер кладёт запрос, окно открывает
проводник и возвращает путь.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog

_requests: "queue.Queue" = queue.Queue()
_state: dict = {"window": None}


class ControlWindow:
    def __init__(self, title: str, subtitle: str, callbacks: dict):
        self.callbacks = callbacks
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("520x260")
        self.root.minsize(460, 240)
        self.root.configure(bg="#f5f5f7")
        self._center()

        title_label = tk.Label(
            self.root, text="MTstats", font=("Segoe UI", 20, "bold"),
            bg="#f5f5f7", fg="#1d1d1f",
        )
        title_label.pack(anchor="w", padx=22, pady=(18, 0))

        self.status = tk.Label(
            self.root, text=subtitle, font=("Segoe UI", 10),
            bg="#f5f5f7", fg="#5f5f66", justify="left", wraplength=470,
        )
        self.status.pack(anchor="w", padx=22, pady=(4, 10))

        buttons = tk.Frame(self.root, bg="#f5f5f7")
        buttons.pack(anchor="w", padx=18, pady=4)

        self._button(buttons, "Открыть статистику", callbacks.get("open"), primary=True)
        self._button(buttons, "Папка с реплеями", callbacks.get("folder"))
        self._button(buttons, "Обновить", callbacks.get("refresh"))

        self.hint = tk.Label(
            self.root, text="Окно можно свернуть — программа работает в фоне.",
            font=("Segoe UI", 9), bg="#f5f5f7", fg="#86868b",
        )
        self.hint.pack(anchor="w", padx=22, pady=(8, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.after(150, self._poll)
        _state["window"] = self

    def _center(self) -> None:
        self.root.update_idletasks()
        width, height = 520, 260
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2 - 60
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _button(self, parent, text, callback, primary=False) -> None:
        if not callback:
            return
        tk.Button(
            parent, text=text, command=callback,
            font=("Segoe UI", 10), relief="flat", cursor="hand2",
            bg="#0071e3" if primary else "#ffffff",
            fg="#ffffff" if primary else "#1d1d1f",
            activebackground="#0077ed" if primary else "#ececf0",
            activeforeground="#ffffff" if primary else "#1d1d1f",
            highlightthickness=0, padx=14, pady=7,
        ).pack(side="left", padx=(0, 8))

    def _quit(self) -> None:
        callback = self.callbacks.get("quit")
        if callback:
            callback()
        else:
            self.root.destroy()

    def _poll(self) -> None:
        try:
            while True:
                initial, box, event = _requests.get_nowait()
                try:
                    path = filedialog.askdirectory(
                        title="Где лежат реплеи «Мир танков»?",
                        initialdir=initial or os.path.expanduser("~"),
                    )
                except tk.TclError:
                    path = ""
                box["path"] = path or None
                event.set()
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def set_status(self, text: str) -> None:
        try:
            self.status.config(text=text)
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def available() -> bool:
    return _state.get("window") is not None


def ask_folder(initial: str = "", timeout: float = 300.0) -> str | None:
    """Открывает системный выбор папки. Возвращает путь или None."""
    window = _state.get("window")
    if not window:
        return None
    box: dict = {}
    event = threading.Event()
    _requests.put((initial, box, event))
    if not event.wait(timeout):
        return None
    return box.get("path")
