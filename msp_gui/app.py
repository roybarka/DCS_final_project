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
        self.geometry("1200x800")  # Increased size for better graph visibility
        self.configure(bg="#f4f6fa")
        # Center the window on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1200 // 2)
        y = (self.winfo_screenheight() // 2) - (800 // 2)
        self.geometry(f"1200x800+{x}+{y}")

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
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#2d415a", background="#f4f6fa")
        style.configure("Sub.TLabel", font=("Segoe UI", 12), foreground="#4a6073", background="#f4f6fa")
        style.configure("Status.TLabel", font=("Segoe UI", 10), foreground="#28a745", background="#f4f6fa")
        style.configure("TButton", font=("Segoe UI", 12), padding=10, background="#e3eaf2", foreground="#2d415a")
        style.map("TButton",
                  background=[("active", "#d0d8e8"), ("pressed", "#b8c2d1")],
                  foreground=[("active", "#1a2633")])
        style.configure("Mode.TButton", font=("Segoe UI", 13, "bold"), padding=12, background="#d4edda", foreground="#155724")
        style.map("Mode.TButton",
                  background=[("active", "#c3e6cb"), ("pressed", "#b1dfbb")],
                  foreground=[("active", "#155724")])
        style.configure("Exit.TButton", font=("Segoe UI", 12, "bold"), background="#f8d7da", foreground="#721c24")
        style.map("Exit.TButton",
                  background=[("active", "#f5c6cb"), ("pressed", "#f1b0b7")],
                  foreground=[("active", "#721c24")])

    # ---- Menu ----

    def _build_menu(self) -> tk.Frame:
        ttk = self.ttk
        f = ttk.Frame(self, padding=30, style="TFrame")
        
        # Header section
        header = ttk.Frame(f, style="TFrame")
        header.pack(fill="x", pady=(0, 20))
        
        ttk.Label(header, text="MSP430 Control Center", style="Title.TLabel").pack(anchor="center")
        ttk.Label(header, text="Choose an operation mode below", style="Sub.TLabel").pack(anchor="center", pady=(5, 15))
        
        # Connection status
        status_frame = ttk.Frame(header, style="TFrame")
        status_frame.pack(anchor="center")
        
        connection_status = "🟢 Connected" if self.controller.ser.is_open else "🔴 Disconnected"
        ttk.Label(status_frame, text=f"Serial: {self.controller.ser.port} @ {self.controller.ser.baudrate} baud", style="Sub.TLabel").pack(side="left")
        ttk.Label(status_frame, text=f" • {connection_status}", style="Status.TLabel").pack(side="left")

        # Mode buttons grid
        btns_frame = ttk.Frame(f, style="TFrame")
        btns_frame.pack(pady=20)

        # Create a 2x3 grid for better layout
        modes = [
            ("🔍 Mode 1 – Sonar Object Detector", "Detect objects using ultrasonic sensor", self._open_mode_1),
            ("🎯 Mode 2 – Angle Motor Rotation", "Control servo motor angle positioning", self._open_mode_2),
            ("💡 Mode 3 – LDR Light Detector", "Detect light sources using photoresistor", self._open_mode_3),
            ("🔍💡 Mode 4 – Object + Light", "Combined object and light detection", self._open_mode_4),
            ("💾 Mode 5 – Flash Management", "Manage microcontroller flash memory", self._open_mode_5),
            ("⚙️ Mode 6 – LDR Calibration", "Calibrate light detection sensor", self._open_mode_6),
        ]

        for i, (title, desc, cmd) in enumerate(modes):
            row = i // 2
            col = i % 2
            
            mode_frame = ttk.Frame(btns_frame, style="TFrame", padding=10)
            mode_frame.grid(row=row, column=col, padx=15, pady=10, sticky="ew")
            
            ttk.Button(mode_frame, text=title, width=40, command=cmd, style="Mode.TButton").pack(fill="x")
            ttk.Label(mode_frame, text=desc, style="Sub.TLabel").pack(pady=(5, 0))

        # Configure grid weights
        btns_frame.columnconfigure(0, weight=1)
        btns_frame.columnconfigure(1, weight=1)

        # Exit button
        ttk.Button(f, text="🚪 Exit Application", command=self._on_close, style="Exit.TButton").pack(pady=30)
        
        # Instructions
        ttk.Label(f, text="All modes will open in this window. Use the 'Stop and Return to Menu' button to go back.", 
                 style="Sub.TLabel").pack(pady=(10, 0))
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
