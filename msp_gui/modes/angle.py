from __future__ import annotations

import logging
import math
from typing import List, Optional

import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController

logger = logging.getLogger(__name__)

# --- Parameters for Mode 2 (Single-angle readout) ---
MAX_ANGLE_DEG = 180           # angles 0..179 inclusive
US_TO_CM = 1.0 / 58.0         # HC-SR04-ish conversion
PLOT_R_MAX_CM = 100           # visible radius on polar plot
MAX_SAMPLES = 15              # store last N samples
SAME_VALUE_TOLERANCE_CM = 4   # simple robust mean

def deg_to_rad(deg: float) -> float:
    return math.radians(deg)

def robust_mean(values: List[float], tol_cm: float = SAME_VALUE_TOLERANCE_CM) -> Optional[float]:
    if not values:
        return None
    clusters = []
    for v in values:
        c = [x for x in values if abs(x - v) <= tol_cm]
        clusters.append(c)
    best = max(clusters, key=lambda c: (len(c), -(max(c) - min(c))))
    return round(sum(best) / len(best), 1)


class Mode2View(ModeBase):
    """
    Angle Motor Rotation:
      - On start, send '2' (no newline) then default angle (90) with newline.
      - User chooses an angle [0..179]; we send '2' then "<angle>\\n".
      - Firmware rotates to that angle and streams "angle:micros" lines.
      - UI shows the selected angle + live robust distance and a simple polar line.
    """

    def __init__(self, master: tk.Misc, controller: MSPController):
        # We handle the initial '2' + angle ourselves in on_start
        super().__init__(master, controller,
                         title="מצב 2 – Angle Motor Rotation",
                         enter_command=None,
                         exit_command="8")
        # State
        self._current_angle: Optional[int] = None
        self._recent_cm: List[float] = []

        # UI
        self.angle_var = tk.StringVar(value="90")
        self.lbl_angle_value: Optional[tk.Label] = None
        self.lbl_dist_value: Optional[tk.Label] = None

        # Plot
        self.figure: Optional[Figure] = None
        self.ax = None
        self.canvas: Optional[FigureCanvasTkAgg] = None

    # ----- ModeBase hooks -----

    def on_start(self) -> None:
        # Controls row
        ctr = tk.Frame(self.body)
        ctr.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(ctr, text="זווית (0–179):").pack(side="left")
        spin = tk.Spinbox(ctr, from_=0, to=179, width=5, textvariable=self.angle_var)
        spin.pack(side="left", padx=(6, 10))

        tk.Button(ctr, text="סובב לזווית", command=self._apply_angle).pack(side="left", padx=(0, 10))

        # Live readout row
        info = tk.Frame(self.body)
        info.pack(fill="x", padx=8, pady=(4, 8))

        tk.Label(info, text="זווית נבחרת:", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.lbl_angle_value = tk.Label(info, text="—")
        self.lbl_angle_value.pack(side="left", padx=(4, 20))

        tk.Label(info, text="מרחק:", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.lbl_dist_value = tk.Label(info, text="— cm")
        self.lbl_dist_value.pack(side="left", padx=(4, 20))

        # Plot
        self.figure = Figure(figsize=(6.5, 5.0))
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas.draw()

        # Initial angle: send '2' (no newline) then default angle with newline
        initial = int(self.angle_var.get())
        self._current_angle = initial
        self._recent_cm.clear()
        self.controller.send_command('2')                 # no newline
        self.controller.send_command(f"{initial}\n")      # angle with newline

    def on_stop(self) -> None:
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        self.figure = None
        self.ax = None
        self.canvas = None
        self._recent_cm.clear()
        self._current_angle = None

    def handle_line(self, line: str) -> None:
        """Expect 'angle:micros' and accept only samples for the selected angle."""
        try:
            a_s, us_s = line.split(":")
            angle = int(a_s)
            micros = int(us_s)
            cm = micros * US_TO_CM
            if cm <= 0:
                return
        except ValueError:
            return

        if self._current_angle is None or angle != self._current_angle:
            return

        self._recent_cm.append(cm)
        if len(self._recent_cm) > MAX_SAMPLES:
            del self._recent_cm[:-MAX_SAMPLES]

    def render(self) -> None:
        # Labels
        if self._current_angle is None:
            self.lbl_angle_value.config(text="—")
            self.lbl_dist_value.config(text="— cm")
        else:
            self.lbl_angle_value.config(text=f"{self._current_angle}°")
            cm = robust_mean(self._recent_cm)
            self.lbl_dist_value.config(text=f"{cm:.1f} cm" if cm is not None else "— cm")

        # Plot
        if not (self.ax and self.canvas):
            return
        self._configure_axes()

        if self._current_angle is not None:
            a = deg_to_rad(self._current_angle)
            cm = robust_mean(self._recent_cm)
            r = PLOT_R_MAX_CM if cm is None else min(cm, PLOT_R_MAX_CM)
            self.ax.plot([a, a], [0, r], linewidth=2)
            if cm is not None:
                self.ax.scatter([a], [cm], s=30)

        self.canvas.draw_idle()

    # ----- Helpers -----

    def _configure_axes(self) -> None:
        self.ax.clear()
        self.ax.set_theta_zero_location("E")  # 0° at right
        self.ax.set_theta_direction(1)        # clockwise
        self.ax.set_thetamin(0)
        self.ax.set_thetamax(MAX_ANGLE_DEG)
        self.ax.set_rlim(0, PLOT_R_MAX_CM)

    def _apply_angle(self) -> None:
        """Button: send '2' (no newline) then the chosen angle with newline."""
        try:
            val = int(self.angle_var.get())
        except Exception:
            return
        if not (0 <= val < 180):
            return

        self._current_angle = val
        self._recent_cm.clear()

        self.controller.send_command('2')           # no newline
        self.controller.send_command(f"{val}\n")    # angle with newline
