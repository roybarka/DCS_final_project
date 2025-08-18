from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

from msp_gui.msp_controller import MSPController
from msp_gui.modes import (
    Mode1View,
    Mode2View,
    Mode3View,
    Mode4View,
    Mode5FlashView,
    Mode6View,
)

logger = logging.getLogger(__name__)


class AppGUI(tk.Tk):
    """
    Single-root Tk app with a menu and pluggable mode views.
    """

    def __init__(self, controller: MSPController):
        super().__init__()
        self.title("MSP Controller – Control Panel")
        self.geometry("900x650")
        self.configure(bg="#f4f6fa")

        # Use ttk for modern widgets
        import tkinter.ttk as ttk
        self.ttk = ttk
        self._init_styles()

        self.controller = controller
        self._active_view: Optional[tk.Frame] = None

        self._menu = self._build_menu()
        self._menu.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_styles(self):
        style = self.ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6fa")
        style.configure("TLabel", background="#f4f6fa", font=("Segoe UI", 11))
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#2d415a", background="#f4f6fa")
        style.configure("Sub.TLabel", font=("Segoe UI", 12), foreground="#4a6073", background="#f4f6fa")
        style.configure("TButton", font=("Segoe UI", 11), padding=8, background="#e3eaf2", foreground="#2d415a")
        style.map("TButton",
                  background=[("active", "#d0d8e8"), ("pressed", "#b8c2d1")],
                  foreground=[("active", "#1a2633")])
        style.configure("Exit.TButton", font=("Segoe UI", 11, "bold"), background="#f8d7da", foreground="#721c24")
        style.map("Exit.TButton",
                  background=[("active", "#f5c6cb"), ("pressed", "#f1b0b7")],
                  foreground=[("active", "#721c24")])

    # ---- Menu ----

    def _build_menu(self) -> tk.Frame:
        ttk = self.ttk
        f = ttk.Frame(self, padding=24, style="TFrame")
        ttk.Label(f, text="בחר מצב עבודה", style="Title.TLabel").pack(pady=(0, 14))
        ttk.Label(f, text=f"Serial: {self.controller.ser.port} @ {self.controller.ser.baudrate} baud", style="Sub.TLabel").pack(pady=(0, 18))

        btns = ttk.Frame(f, style="TFrame")
        btns.pack(pady=10)

        ttk.Button(btns, text="מצב 1 – Sonar Object Detector", width=35, command=self._open_mode_1, style="TButton").grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(btns, text="מצב 2 – Angle Motor Rotation", width=35, command=self._open_mode_2, style="TButton").grid(row=1, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(btns, text="מצב 3 – LDR Light Detector", width=35, command=self._open_mode_3, style="TButton").grid(row=2, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(btns, text="מצב 4 – Object + Light", width=35, command=self._open_mode_4, style="TButton").grid(row=3, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(btns, text="מצב 5 – ניהול קבצים (Flash)", width=35, command=self._open_mode_5, style="TButton").grid(row=4, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(btns, text="מצב 6 – כיול LDR", width=35, command=self._open_mode_6, style="TButton").grid(row=5, column=0, padx=8, pady=8, sticky="ew")

        ttk.Button(f, text="יציאה מהתוכנה", command=self._on_close, style="Exit.TButton").pack(pady=22)
        ttk.Label(f, text="כל המצבים ייפתחו בתוך חלון זה.", style="Sub.TLabel").pack(pady=(8, 0))
        return f

    # ---- Navigation ----

    def _mount_view(self, view: tk.Frame) -> None:
        if self._active_view is not None:
            self._active_view.pack_forget()
            if hasattr(self._active_view, "stop"):
                try:
                    self._active_view.stop()
                except Exception:
                    pass
        self._menu.pack_forget()
        self._active_view = view
        self._active_view.pack(fill="both", expand=True)

    def navigate_to_menu(self) -> None:
        if self._active_view is not None:
            self._active_view.pack_forget()
            if hasattr(self._active_view, "stop"):
                try:
                    self._active_view.stop()
                except Exception:
                    pass
            self._active_view = None
        self._menu.pack(fill="both", expand=True)

    # ---- Open modes ----

    def _open_mode_1(self) -> None:
        view = Mode1View(self, self.controller)
        view.set_back_callback(self.navigate_to_menu)
        self._mount_view(view)
        view.start()

    def _open_mode_2(self) -> None:
        view = Mode2View(self, self.controller)
        view.set_back_callback(self.navigate_to_menu)
        self._mount_view(view)
        view.start()

    def _open_mode_5(self) -> None:
        view = Mode5FlashView(self, self.controller)
        view.set_back_callback(self.navigate_to_menu)
        self._mount_view(view)
        view.start()

    def _open_mode_6(self) -> None:  # NEW
        view = Mode6View(self, self.controller)
        view.set_back_callback(self.navigate_to_menu)
        self._mount_view(view)
        view.start()

    def _open_mode_3(self) -> None:
        view = Mode3View(self, self.controller)
        view.set_back_callback(self.navigate_to_menu)
        self._mount_view(view)
        view.start()

    def _open_mode_4(self) -> None:
        view = Mode4View(self, self.controller)
        view.set_back_callback(self.navigate_to_menu)
        self._mount_view(view)
        view.start()

    # ---- Close ----

    def _on_close(self) -> None:
        try:
            if self._active_view is not None and hasattr(self._active_view, "stop"):
                self._active_view.stop()
        finally:
            try:
                self.controller.close()
            finally:
                self.destroy()
