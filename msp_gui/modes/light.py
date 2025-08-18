from __future__ import annotations

import tkinter as tk
from typing import Optional, List, Tuple

import math
from dataclasses import dataclass
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.modes.ldr_utils import LDRCalibration, DISTANCES
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
        self._distances = [None] * 180
        self._saturated = [False] * 180  # True if beyond max distance
        # batching and logging
        self._batch = AngleBatch()
        self._measurements = []
        # plotting handles
        self.figure = None
        self.ax = None
        self.canvas = None

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(wrap, text="מצב 3 – סריקת LDR (פולר)", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, textvariable=self._status_var, style="TLabel").pack(anchor="w", pady=(2, 0))
        logger.info("Mode 3 started: awaiting calibration (10 lines of idx:value)")

        self.figure = Figure(figsize=(10, 8), facecolor='white')
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.canvas.draw()

    def on_stop(self) -> None:
        logger.info("Mode 3 stopping: clearing state and plot")
        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._distances = [None] * 180
        self._saturated = [False] * 180
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
        sat_angles = []
        sat_dists = []
        for angle, dist in enumerate(self._distances):
            if dist is not None:
                if self._saturated[angle]:
                    sat_angles.append(math.radians(angle))
                    sat_dists.append(dist)
                else:
                    angles.append(math.radians(angle))
                    dists.append(dist)
        if angles:
            self.ax.scatter(angles, dists, c="orange", s=10)
        if sat_angles:
            # Plot saturated (beyond max) readings in gray triangles
            self.ax.scatter(sat_angles, sat_dists, c="gray", s=16, marker="^", alpha=0.7)

        # Detect and draw light source markers (red stars)
        sources = self._detect_light_sources()
        if sources:
            src_angles = [math.radians(a) for (a, _d) in sources]
            src_dists = [_d for (_a, _d) in sources]
            self.ax.scatter(src_angles, src_dists, c="red", s=80, marker="*", edgecolors="black", zorder=3)
            # Update status with the strongest (closest) source
            best = min(sources, key=lambda t: t[1])
            self._status_var.set(f"Detected source at angle={best[0]}°, dist≈{best[1]:.1f} cm")
        self.canvas.draw_idle()

    def _configure_axes(self) -> None:
        self.ax.clear()
        self.ax.set_theta_zero_location("E")
        self.ax.set_theta_direction(1)
        self.ax.set_thetamin(0)
        self.ax.set_thetamax(179)
        self.ax.set_rlim(0, 55)
        
        # Add title and improve formatting
        self.ax.set_title("Light Source Detection\nLDR Sensor Readings", pad=20, fontsize=14, fontweight='bold')
        self.ax.set_ylabel("Distance (cm)", labelpad=30, fontsize=12)
        self.ax.grid(True, alpha=0.3)
        
        # Add degree markings
        theta_ticks = range(0, 180, 30)
        self.ax.set_thetagrids(theta_ticks, [f"{t}°" for t in theta_ticks])
        
        # Create legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=8, label='💡 Light Detection'),
            Line2D([0], [0], marker='*', color='w', markerfacecolor='yellow', markersize=12, label='🌟 Light Source'),
            Line2D([0], [0], marker='X', color='w', markerfacecolor='red', markersize=8, label='🚫 Saturated/No Data')
        ]
        self.ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(0.02, 0.98), fontsize=10)

    def _finalize_batch(self) -> None:
        res = self._batch.summarize_mean_raw()
        if res is None:
            return
        angle, mean_raw = res
        logger.debug("Finalize angle=%d: raw_samples=%r mean_raw=%.2f", angle, self._batch.values_raw, mean_raw)
        # Convert the averaged raw value once, with saturation handling
        raw_rounded = int(round(mean_raw))
        dist_cm = self.calib.value_to_distance(raw_rounded)

        # Determine saturation relative to calibration extremes
        sat = False
        if self.calib.is_complete() and self.calib.values[0] is not None and self.calib.values[9] is not None:
            v0 = int(self.calib.values[0])
            v9 = int(self.calib.values[9])
            inc = v9 >= v0
            if inc:
                # If raw >= highest calibration value -> beyond max distance
                if raw_rounded >= v9:
                    sat = True
            else:
                # Decreasing with distance: beyond max distance when raw <= lowest endpoint (index 9)
                if raw_rounded <= v9:
                    sat = True

        if sat:
            beyond = float(DISTANCES[-1] + 1)  # mark slightly beyond max distance
            self._distances[angle] = beyond
            self._saturated[angle] = True
            logger.info("Commit angle=%d → %.2f cm (SATURATED beyond max, raw≈%.1f)", angle, beyond, mean_raw)
            self._status_var.set(f"Angle={angle} → >{DISTANCES[-1]} cm (raw≈{mean_raw:.1f})")
            return

        if dist_cm is None:
            logger.debug("Converted distance is None (out of calibration range) for angle=%d mean_raw=%.2f", angle, mean_raw)
            return
        self._distances[angle] = dist_cm
        self._saturated[angle] = False
        logger.info("Commit angle=%d → %.2f cm (raw≈%.1f)", angle, dist_cm, mean_raw)
        self._status_var.set(f"Angle={angle} → {dist_cm:.2f} cm (raw≈{mean_raw:.1f})")

    def _detect_light_sources(self) -> List[Tuple[int, float]]:
        """
        Find local minima in the distance array, cluster minima within <=20°,
        and return one source per cluster: (angle_deg, distance_cm) for the min point.
        Saturated points are ignored for minima detection.
        """
        d = self._distances
        if not any(x is not None for x in d):
            return []

        def get(i: int) -> Optional[float]:
            v = d[i]
            return None if (v is None or self._saturated[i]) else v

        minima: List[Tuple[int, float]] = []
        # Consider circular neighbors (wrap at 0/179)
        for i in range(180):
            v = get(i)
            if v is None:
                continue
            left = get((i - 1) % 180)
            right = get((i + 1) % 180)
            # If neighbors missing, require at least one valid neighbor and be <= that neighbor
            is_min = False
            if left is not None and right is not None:
                is_min = v <= left and v <= right and (v < left or v < right)
            elif left is not None:
                is_min = v < left
            elif right is not None:
                is_min = v <= right
            if is_min:
                minima.append((i, v))

        if not minima:
            return []

        minima.sort(key=lambda t: t[0])

        # Cluster minima where circular angle distance <= 20°
        clusters: List[List[Tuple[int, float]]] = []
        cur: List[Tuple[int, float]] = [minima[0]]
        for a, v in minima[1:]:
            prev_a = cur[-1][0]
            # circular distance
            da = min(abs(a - prev_a), 180 - abs(a - prev_a))
            if da <= 20:
                cur.append((a, v))
            else:
                clusters.append(cur)
                cur = [(a, v)]
        clusters.append(cur)

        # Merge first/last cluster if they wrap within 20°
        if len(clusters) > 1:
            first_a = clusters[0][0][0]
            last_a = clusters[-1][-1][0]
            wrap_da = min(abs(last_a - first_a), 180 - abs(last_a - first_a))
            if wrap_da <= 20:
                merged = clusters[-1] + clusters[0]
                clusters = [merged] + clusters[1:-1]

        # Pick the minimum in each cluster
        sources: List[Tuple[int, float]] = []
        for group in clusters:
            a, v = min(group, key=lambda t: t[1])
            sources.append((a, v))
        return sources
