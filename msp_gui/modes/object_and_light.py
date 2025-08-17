from __future__ import annotations

import tkinter as tk
from typing import Optional
from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.modes.ldr_utils import LDRCalibration

class Mode4ObjectAndLightDetectorView(ModeBase):
    """
    Mode 4 – Object and Light Detector (combined scan).
    On start: expects 10 calibration lines, then measurement lines.
    """
    def __init__(self, master: tk.Misc, controller: MSPController):
        super().__init__(master, controller,
                         title="מצב 4 – Object & Light Detector",
                         enter_command="4",
                         exit_command="8")
        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._last_distance = None
        self._last_raw = None
        self._status_var = tk.StringVar(value="Awaiting calibration...")

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(wrap, text="מצב 4 – סריקת אובייקטים ו-LDR", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, textvariable=self._status_var, style="TLabel").pack(anchor="w", pady=(2, 0))

    def on_stop(self) -> None:
        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._last_distance = None
        self._last_raw = None
        self._status_var.set("Awaiting calibration...")

    def handle_line(self, line: str) -> None:
        # Calibration phase: expect 10 lines of the form 'idx:value'
        if not self.calib.is_complete():
            try:
                idx, val = map(int, line.strip().split(":"))
                self.calib.add(idx, val)
                self._calib_lines += 1
                self._status_var.set(f"Calibration {self._calib_lines}/10...")
            except Exception:
                pass
            if self.calib.is_complete():
                self._status_var.set("Calibration complete. Awaiting measurements...")
            return
        # Measurement phase: expect 'idx:value' or just 'value' (could be more complex for combined mode)
        try:
            # Example: 'angle:dist:ldr' or 'angle:ldr' or 'ldr' (adapt as needed)
            parts = line.strip().split(":")
            ldr_val = None
            if len(parts) == 3:
                # angle:dist:ldr
                ldr_val = int(parts[2])
            elif len(parts) == 2:
                # angle:ldr or idx:value
                ldr_val = int(parts[1])
            elif len(parts) == 1:
                ldr_val = int(parts[0])
            if ldr_val is not None:
                dist = self.calib.value_to_distance(ldr_val)
                self._last_raw = ldr_val
                self._last_distance = dist
                if dist is not None:
                    self._status_var.set(f"LDR={ldr_val} → {dist:.1f} cm")
                else:
                    self._status_var.set(f"LDR={ldr_val} (out of range)")
        except Exception:
            pass

    def render(self) -> None:
        pass
