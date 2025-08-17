from __future__ import annotations

import tkinter as tk
from typing import Optional

import math
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.modes.ldr_utils import LDRCalibration

class Mode3LightDetectorView(ModeBase):
    """
    Mode 3 – Light Detector (LDR scan).
    On start: expects 10 calibration lines, then LDR measurement lines.
    """
    def __init__(self, master: tk.Misc, controller: MSPController):
        super().__init__(master, controller,
                         title="מצב 3 – Light Detector",
                         enter_command="3",
                         exit_command="8")
        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._status_var = tk.StringVar(value="Awaiting calibration...")
        self._distances = [None] * 180  # angle-indexed
        self._recent = {}  # angle: list of recent LDR values
        self.figure = None
        self.ax = None
        self.canvas = None

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(wrap, text="מצב 3 – סריקת LDR (פולר)", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, textvariable=self._status_var, style="TLabel").pack(anchor="w", pady=(2, 0))

        self.figure = Figure(figsize=(6.5, 5.0))
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.canvas.draw()

    def on_stop(self) -> None:
        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._distances = [None] * 180
        self._recent = {}
        self._status_var.set("Awaiting calibration...")
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        self.figure = None
        self.ax = None
        self.canvas = None

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
        # Measurement phase: expect 'angle:ldr' or similar
        try:
            a_s, ldr_s = line.strip().split(":")
            angle = int(a_s)
            ldr_val = int(ldr_s)
            dist = self.calib.value_to_distance(ldr_val)
            if 0 <= angle < 180:
                self._recent.setdefault(angle, []).append(ldr_val)
                if len(self._recent[angle]) > 7:
                    self._recent[angle] = self._recent[angle][-7:]
                # Robust mean of recent LDR values
                ldr_mean = sum(self._recent[angle]) / len(self._recent[angle])
                dist_mean = self.calib.value_to_distance(int(ldr_mean))
                self._distances[angle] = dist_mean
            self._status_var.set(f"Angle={angle} LDR={ldr_val} → {dist:.1f} cm" if dist is not None else f"Angle={angle} LDR={ldr_val} (out of range)")
        except Exception:
            pass

    def render(self) -> None:
        if not (self.ax and self.canvas):
            return
        self._configure_axes()
        angles = []
        dists = []
        for angle, dist in enumerate(self._distances):
            if dist is not None:
                angles.append(math.radians(angle))
                dists.append(dist)
        if angles:
            self.ax.scatter(angles, dists, c="orange", s=10)
        self.canvas.draw_idle()

    def _configure_axes(self) -> None:
        self.ax.clear()
        self.ax.set_theta_zero_location("E")
        self.ax.set_theta_direction(1)
        self.ax.set_thetamin(0)
        self.ax.set_thetamax(179)
        self.ax.set_rlim(0, 55)
