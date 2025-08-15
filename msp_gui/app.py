from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

from msp_gui.msp_controller import MSPController
from msp_gui.modes import Mode1View, Mode2View, Mode5FlashView, Mode6View

logger = logging.getLogger(__name__)


class AppGUI(tk.Tk):
    """
    Single-root Tk app with a menu and pluggable mode views.
    """

    def __init__(self, controller: MSPController):
        super().__init__()
        self.title("MSP Controller – Control Panel")
        self.geometry("900x650")

        self.controller = controller
        self._active_view: Optional[tk.Frame] = None

        self._menu = self._build_menu()
        self._menu.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- Menu ----

    def _build_menu(self) -> tk.Frame:
        f = tk.Frame(self, padx=16, pady=16)
        tk.Label(f, text="בחר מצב עבודה", font=("Segoe UI", 16, "bold")).pack(pady=(0, 12))
        tk.Label(f, text=f"Serial: {self.controller.ser.port} @ {self.controller.ser.baudrate} baud")\
            .pack(pady=(0, 16))

        btns = tk.Frame(f)
        btns.pack(pady=8)

        tk.Button(btns, text="מצב 1 – Sonar Object Detector", width=35,
                  command=self._open_mode_1)\
            .grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        tk.Button(btns, text="מצב 2 – Angle Motor Rotation", width=35,
                  command=self._open_mode_2)\
            .grid(row=1, column=0, padx=6, pady=6, sticky="ew")

        # Placeholders for future GUI modes
        tk.Button(btns, text="מצב 3 – LDR Light Detector (GUI soon)", width=35, state="disabled")\
            .grid(row=2, column=0, padx=6, pady=6, sticky="ew")
        tk.Button(btns, text="מצב 4 – Object + Light (GUI soon)", width=35, state="disabled")\
            .grid(row=3, column=0, padx=6, pady=6, sticky="ew")

        tk.Button(btns, text="מצב 5 – ניהול קבצים (Flash)", width=35,
                  command=self._open_mode_5) \
            .grid(row=4, column=0, padx=6, pady=6, sticky="ew")

        tk.Button(btns, text="מצב 6 – כיול LDR", width=35,  # NEW
                  command=self._open_mode_6) \
            .grid(row=5, column=0, padx=6, pady=6, sticky="ew")

        tk.Button(f, text="יציאה מהתוכנה", command=self._on_close).pack(pady=18)

        tk.Label(f, text="כל המצבים ייפתחו בתוך חלון זה. כרגע: מצבים 1 ,2 ו5 זמינים.", fg="#555").pack()
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
