from __future__ import annotations

import tkinter as tk
from typing import Optional, List, Tuple

import math
from dataclasses import dataclass
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.modes.ldr_utils import LDRCalibration
import logging

MAX_ANGLE_DEG = 180
MAX_SAMPLES_PER_ANGLE = 15

logger = logging.getLogger(__name__)


@dataclass
class AngleBatch:
    angle: Optional[int] = None
    values_raw: List[int] = None  # raw LDR samples

    def __post_init__(self):
        if self.values_raw is None:
            self.values_raw = []

    def reset(self, angle: int, first_raw: int) -> None:
        self.angle = angle
        self.values_raw = [first_raw]

    def add_raw(self, raw: int) -> None:
        self.values_raw.append(raw)

    def is_full(self) -> bool:
        return len(self.values_raw) >= MAX_SAMPLES_PER_ANGLE

    def summarize_mean_raw(self) -> Optional[Tuple[int, float]]:
        if self.angle is None or not self.values_raw:
            return None
        mean_raw = sum(self.values_raw) / float(len(self.values_raw))
        return self.angle, mean_raw


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
        # angle-indexed distances in cm (0..179)
        self._distances: List[Optional[float]] = [None] * 180
        # batching and logging
        self._batch = AngleBatch()
        self._measurements: List[Tuple[int, int]] = []
        # plotting handles
        self.figure: Optional[Figure] = None
        self.ax = None
        self.canvas: Optional[FigureCanvasTkAgg] = None

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(wrap, text="מצב 3 – סריקת LDR (פולר)", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, textvariable=self._status_var, style="TLabel").pack(anchor="w", pady=(2, 0))
        logger.info("Mode 3 started: awaiting calibration (10 lines of idx:value)")

        self.figure = Figure(figsize=(6.5, 5.0))
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.canvas.draw()

    def on_stop(self) -> None:
        logger.info("Mode 3 stopping: clearing state and plot")
        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._distances = [None] * 180
        self._batch = AngleBatch()
        self._measurements = []
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
                logger.debug("Calibration recv: idx=%s val=%s (%d/10)", idx, val, self._calib_lines)
            except Exception:
                logger.debug("Calibration parse failed for line: %r", line)
            if self.calib.is_complete():
                self._status_var.set("Calibration complete. Awaiting measurements...")
                logger.info("Calibration complete; ready to process measurements")
            return
    # Measurement phase: expect repeated 'angle:ldr' samples; batch raw values and average once
        try:
            a_s, ldr_s = line.strip().split(":")
            angle = int(a_s)
            ldr_val = int(ldr_s)
        except Exception:
            logger.debug("Measure parse failed for line: %r", line)
            return

        if not (0 <= angle < MAX_ANGLE_DEG):
            logger.debug("Skip out-of-range angle: %s (raw line=%r)", angle, line.strip())
            return

        b = self._batch
        if b.angle is None:
            b.reset(angle, ldr_val)
            logger.debug("Start batch: angle=%d raw=[%d]", angle, ldr_val)
            return

        if angle != b.angle:
            logger.debug("Angle changed %d→%d; finalize previous batch", b.angle, angle)
            self._finalize_batch()
            b.reset(angle, ldr_val)
            logger.debug("Start batch: angle=%d raw=[%d]", angle, ldr_val)
            return

        b.add_raw(ldr_val)
        logger.debug("Append raw: angle=%d raw=%d (n=%d)", angle, ldr_val, len(b.values_raw))
        if b.is_full():
            logger.debug("Batch full at angle=%d (n=%d); finalizing", angle, len(b.values_raw))
            self._finalize_batch()
            b.angle = None
            b.values_raw.clear()

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

    def _finalize_batch(self) -> None:
        res = self._batch.summarize_mean_raw()
        if res is None:
            return
        angle, mean_raw = res
        logger.debug("Finalize angle=%d: raw_samples=%r mean_raw=%.2f", angle, self._batch.values_raw, mean_raw)
        # Convert the averaged raw value once
        dist_cm = self.calib.value_to_distance(int(round(mean_raw)))
        if dist_cm is None:
            logger.debug("Converted distance is None (out of calibration range) for angle=%d mean_raw=%.2f", angle, mean_raw)
            return
        self._distances[angle] = dist_cm
        logger.info("Commit angle=%d → %.2f cm (raw≈%.1f)", angle, dist_cm, mean_raw)
        self._status_var.set(f"Angle={angle} → {dist_cm:.2f} cm (raw≈{mean_raw:.1f})")
