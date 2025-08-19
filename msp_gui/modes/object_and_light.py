from __future__ import annotations

import logging
import math
import tkinter as tk
from dataclasses import dataclass
from typing import List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.modes.ldr_utils import LDRCalibration, DISTANCES

logger = logging.getLogger(__name__)

# Shared-ish parameters to mirror Modes 1 and 3
MAX_ANGLE_DEG = 180
US_TO_CM = 1.0 / 58.0
PLOT_R_MAX_CM = 100
CLUSTER_MAX_GAP_CM = 10
CLUSTER_MIN_SIZE = 30
BEAM_WIDTH_DEG = 30
SONAR_SAMPLES_PER_ANGLE = 7
LDR_SAMPLES_PER_ANGLE = 7
SAME_VALUE_TOLERANCE_CM = 2.5


def deg_to_rad(deg: float) -> float:
    return math.radians(deg)


@dataclass
class CombinedBatch:
    angle: Optional[int] = None
    sonar_cm: List[float] = None
    ldr_raw: List[int] = None

    def __post_init__(self) -> None:
        if self.sonar_cm is None:
            self.sonar_cm = []
        if self.ldr_raw is None:
            self.ldr_raw = []

    def reset(self, angle: int, sonar: Optional[float], ldr: Optional[int]) -> None:
        self.angle = angle
        self.sonar_cm = [] if sonar is None else [sonar]
        self.ldr_raw = [] if ldr is None else [ldr]

    def add(self, sonar: Optional[float], ldr: Optional[int]) -> None:
        if sonar is not None:
            self.sonar_cm.append(sonar)
        if ldr is not None:
            self.ldr_raw.append(ldr)

    def sonar_full(self) -> bool:
        return len(self.sonar_cm) >= SONAR_SAMPLES_PER_ANGLE

    def ldr_full(self) -> bool:
        return len(self.ldr_raw) >= LDR_SAMPLES_PER_ANGLE

    def summarize(self) -> Optional[Tuple[int, Optional[float], Optional[float]]]:
        if self.angle is None:
            return None
        sonar_mean: Optional[float] = None
        if self.sonar_cm:
            vals = self.sonar_cm
            clusters = []
            for v in vals:
                c = [x for x in vals if abs(x - v) <= SAME_VALUE_TOLERANCE_CM]
                clusters.append(c)
            best = max(clusters, key=lambda c: (len(c), -(max(c) - min(c))))
            sonar_mean = round(sum(best) / len(best), 1)

        ldr_mean: Optional[float] = None
        if self.ldr_raw:
            ldr_mean = sum(self.ldr_raw) / float(len(self.ldr_raw))
        return self.angle, sonar_mean, ldr_mean


class Mode4ObjectAndLightDetectorView(ModeBase):
    """
    Mode 4 – Combined scan of sonar + LDR:
      - Calibration phase identical to Mode 3 (10 idx:value lines)
      - Measurement phase: expects repeated lines per angle in the form "angle:us:ldr"
        where 'us' is sonar echo time (converted to cm), and 'ldr' is raw LDR.
      - Aggregation mirrors Mode 1 (robust mean for sonar) and Mode 3 (mean raw -> distance with saturation) per angle.
      - UI shows both: object arcs (sonar clusters) and light-source stars (minima in LDR-inferred distances).
    """

    def __init__(self, master: tk.Misc, controller: MSPController):
        super().__init__(master, controller,
                         title="מצב 4 – Object & Light Detector",
                         enter_command="4",
                         exit_command="8")
        self.calib = LDRCalibration()
        self._calib_lines = 0

        # Angle-indexed arrays
        self._sonar_cm: List[Optional[float]] = [None] * MAX_ANGLE_DEG
        self._ldr_cm: List[Optional[float]] = [None] * MAX_ANGLE_DEG
        self._ldr_sat: List[bool] = [False] * MAX_ANGLE_DEG

        # Plot handles
        self.figure: Optional[Figure] = None
        self.ax = None
        self.canvas: Optional[FigureCanvasTkAgg] = None

        # Batching per angle
        self._batch = CombinedBatch()

        # Status
        self._status_var = tk.StringVar(value="Awaiting calibration...")

    # ----- ModeBase hooks -----

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(wrap, text="מצב 4 – סריקת אובייקטים + מקור אור", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, textvariable=self._status_var, style="TLabel").pack(anchor="w", pady=(2, 0))

        self.figure = Figure(figsize=(10, 8), facecolor='white')
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.canvas.draw()

        # Reset data
        self._sonar_cm = [None] * MAX_ANGLE_DEG
        self._ldr_cm = [None] * MAX_ANGLE_DEG
        self._ldr_sat = [False] * MAX_ANGLE_DEG
        self._batch = CombinedBatch()
        self._calib_lines = 0
        self._status_var.set("Awaiting calibration...")

    def on_stop(self) -> None:
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        self.figure = None
        self.ax = None
        self.canvas = None

        self.calib = LDRCalibration()
        self._calib_lines = 0
        self._sonar_cm = [None] * MAX_ANGLE_DEG
        self._ldr_cm = [None] * MAX_ANGLE_DEG
        self._ldr_sat = [False] * MAX_ANGLE_DEG
        self._batch = CombinedBatch()
        self._status_var.set("Awaiting calibration...")

    def handle_line(self, line: str) -> None:
        # Calibration: 10 lines 'idx:value'
        if not self.calib.is_complete():
            try:
                idx, val = map(int, line.strip().split(":"))
                self.calib.add(idx, val)
                self._calib_lines += 1
                self._status_var.set(f"Calibration {self._calib_lines}/10...")
                logger.debug("Mode4 calib: idx=%s val=%s", idx, val)
            except Exception:
                logger.debug("Mode4 calib parse failed: %r", line)
            if self.calib.is_complete():
                self._status_var.set("Calibration complete. Awaiting measurements...")
                logger.info("Mode4 calibration complete")
            return

        # Measurements: expect 'angle:us:ldr' and possibly repeated per angle
        try:
            parts = line.strip().split(":")
            if len(parts) < 3:
                return
            angle = int(parts[0])
            us = int(parts[1])
            ldr_raw = int(parts[2])
        except Exception:
            return

        if not (0 <= angle < MAX_ANGLE_DEG):
            return

        sonar_cm = us * US_TO_CM
        if sonar_cm <= 0:
            sonar_cm = None

        b = self._batch
        if b.angle is None:
            b.reset(angle, sonar_cm, ldr_raw)
            return

        if angle != b.angle:
            self._finalize_batch()
            b.reset(angle, sonar_cm, ldr_raw)
            return

        b.add(sonar_cm, ldr_raw)
        # Finalize when both streams have reached targets -> one commit per angle
        if b.sonar_full() and b.ldr_full():
            self._finalize_batch()
            b.angle = None
            b.sonar_cm.clear()
            b.ldr_raw.clear()

    def render(self) -> None:
        if not (self.ax and self.canvas):
            return

        self._configure_axes()

        # Plot sonar points
        sonar_angles = []
        sonar_dists = []
        for a, d in enumerate(self._sonar_cm):
            if d is not None:
                sonar_angles.append(deg_to_rad(a))
                sonar_dists.append(d)
        if sonar_angles:
            self.ax.scatter(sonar_angles, sonar_dists, c="lime", s=10)

        # Plot LDR points
        ldr_angles = []
        ldr_dists = []
        sat_angles = []
        sat_dists = []
        for a, d in enumerate(self._ldr_cm):
            if d is None:
                continue
            if self._ldr_sat[a]:
                sat_angles.append(deg_to_rad(a))
                sat_dists.append(d)
            else:
                ldr_angles.append(deg_to_rad(a))
                ldr_dists.append(d)
        if ldr_angles:
            self.ax.scatter(ldr_angles, ldr_dists, c="orange", s=10)
        if sat_angles:
            self.ax.scatter(sat_angles, sat_dists, c="gray", s=16, marker="^", alpha=0.7)

        # Sonar object arcs (borrowed from Mode 1)
        clusters: List[List[tuple[int, float]]] = []
        cur: List[tuple[int, float]] = []
        for idx, dist in enumerate(self._sonar_cm):
            if dist is not None:
                if dist <= PLOT_R_MAX_CM:
                    if cur and abs(dist - cur[-1][1]) > CLUSTER_MAX_GAP_CM:
                        if len(cur) >= CLUSTER_MIN_SIZE:
                            clusters.append(cur)
                        cur = []
                    cur.append((idx, dist))
                else:
                    if len(cur) >= CLUSTER_MIN_SIZE:
                        clusters.append(cur)
                    cur = []
            else:
                if len(cur) >= CLUSTER_MIN_SIZE:
                    clusters.append(cur)
                cur = []
        if len(cur) >= CLUSTER_MIN_SIZE:
            clusters.append(cur)

        for cluster in clusters:
            angle_idxs = [i for i, _ in cluster]
            dists = [d for _, d in cluster]
            trim = int(BEAM_WIDTH_DEG / 2)
            if len(cluster) <= 2 * trim:
                continue
            angle_idxs = angle_idxs[trim:-trim]
            dists = dists[trim:-trim]
            if not angle_idxs:
                continue
            phi_center = sum(angle_idxs) / len(angle_idxs)
            phi_center_rad = deg_to_rad(phi_center)
            p_mean = sum(dists) / len(dists)
            valid_width_deg = angle_idxs[-1] - angle_idxs[0]
            l_real = 2 * math.pi * p_mean * (valid_width_deg / 360.0)
            arc_angles = [deg_to_rad(a) for a in range(angle_idxs[0], angle_idxs[-1] + 1)]
            arc_r = [p_mean] * len(arc_angles)
            self.ax.plot(arc_angles, arc_r, c="red", linewidth=2)
            label = f"φ={int(phi_center)}°\np={int(p_mean)} cm\nl={int(l_real)} cm"
            self.ax.text(
                phi_center_rad, p_mean + 5, label,
                fontsize=7, ha="center", color="blue",
                bbox=dict(facecolor="white", alpha=0.6, edgecolor="none", pad=1),
            )

        # Light sources from LDR minima
        sources = self._detect_light_sources()
        if sources:
            src_angles = [deg_to_rad(a) for (a, _d) in sources]
            src_dists = [_d for (_a, _d) in sources]
            self.ax.scatter(src_angles, src_dists, c="red", s=80, marker="*", edgecolors="black", zorder=3)
            best = min(sources, key=lambda t: t[1])
            self._status_var.set(f"Detected light at {best[0]}°, ≈{best[1]:.1f} cm")

        self.canvas.draw_idle()

    # ----- Helpers -----

    def _configure_axes(self) -> None:
        self.ax.clear()
        self.ax.set_theta_zero_location("E")
        self.ax.set_theta_direction(1)
        self.ax.set_thetamin(0)
        self.ax.set_thetamax(MAX_ANGLE_DEG)
        self.ax.set_rlim(0, max(PLOT_R_MAX_CM, DISTANCES[-1] + 10))
        
        # Add title and improve formatting
        self.ax.set_title("Combined Object & Light Detection\nSonar + LDR Sensors", pad=20, fontsize=14, fontweight='bold')
        self.ax.set_ylabel("Distance (cm)", labelpad=30, fontsize=12)
        self.ax.grid(True, alpha=0.3)
        
        # Add degree markings
        theta_ticks = range(0, 180, 30)
        self.ax.set_thetagrids(theta_ticks, [f"{t}°" for t in theta_ticks])
        
        # Create comprehensive legend
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='lime', markersize=8, label='* Sonar Points'),
            Line2D([0], [0], color='red', linewidth=3, label='-> Objects (Sonar)'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=8, label='+ Light Detection'),
            Line2D([0], [0], marker='*', color='w', markerfacecolor='yellow', markersize=12, label='* Light Sources'),
            Patch(facecolor='white', edgecolor='blue', alpha=0.6, label='[i] Object Info')
        ]
        self.ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(0.02, 0.98), fontsize=9)

    def _finalize_batch(self) -> None:
        res = self._batch.summarize()
        if res is None:
            return
        angle, sonar_mean, ldr_mean = res

        # Sonar commit
        if sonar_mean is not None:
            self._sonar_cm[angle] = sonar_mean

        # LDR commit with saturation handling
        if ldr_mean is not None:
            raw = int(round(ldr_mean))
            dist_cm = self.calib.value_to_distance(raw)

            sat = False
            if self.calib.is_complete() and self.calib.values[0] is not None and self.calib.values[9] is not None:
                v0 = int(self.calib.values[0])
                v9 = int(self.calib.values[9])
                inc = v9 >= v0
                if inc:
                    if raw >= v9:
                        sat = True
                else:
                    if raw <= v9:
                        sat = True

            if sat:
                self._ldr_cm[angle] = float(DISTANCES[-1] + 1)
                self._ldr_sat[angle] = True
            else:
                if dist_cm is not None:
                    self._ldr_cm[angle] = dist_cm
                    self._ldr_sat[angle] = False

    def _detect_light_sources(self) -> List[Tuple[int, float]]:
        d = self._ldr_cm
        if not any(x is not None for x in d):
            return []

        def get(i: int) -> Optional[float]:
            v = d[i]
            return None if (v is None or self._ldr_sat[i]) else v

        minima: List[Tuple[int, float]] = []
        for i in range(MAX_ANGLE_DEG):
            v = get(i)
            if v is None:
                continue
            left = get((i - 1) % MAX_ANGLE_DEG)
            right = get((i + 1) % MAX_ANGLE_DEG)
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

        clusters: List[List[Tuple[int, float]]] = []
        cur: List[Tuple[int, float]] = [minima[0]]
        for a, v in minima[1:]:
            prev_a = cur[-1][0]
            da = min(abs(a - prev_a), MAX_ANGLE_DEG - abs(a - prev_a))
            if da <= 20:
                cur.append((a, v))
            else:
                clusters.append(cur)
                cur = [(a, v)]
        clusters.append(cur)

        if len(clusters) > 1:
            first_a = clusters[0][0][0]
            last_a = clusters[-1][-1][0]
            wrap_da = min(abs(last_a - first_a), MAX_ANGLE_DEG - abs(last_a - first_a))
            if wrap_da <= 20:
                merged = clusters[-1] + clusters[0]
                clusters = [merged] + clusters[1:-1]

        sources: List[Tuple[int, float]] = []
        for group in clusters:
            a, v = min(group, key=lambda t: t[1])
            sources.append((a, v))
        return sources
