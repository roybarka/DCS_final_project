from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController

logger = logging.getLogger(__name__)

# --- Parameters for Mode 1 (Sonar) ---

MAX_ANGLE_DEG = 180          # angles 0..179 inclusive
US_TO_CM = 1.0 / 58.0        # HC-SR04-ish conversion
PLOT_R_MAX_CM = 100          # visible radius on polar plot
CLUSTER_MAX_GAP_CM = 10      # split a cluster if jump > this
CLUSTER_MIN_SIZE = 30        # min contiguous points after trimming
BEAM_WIDTH_DEG = 30          # trim beam edges (±15°)
MAX_SAMPLES_PER_ANGLE = 10
SAME_VALUE_TOLERANCE_CM = 2.5  # within ±4 cm → same cluster


def deg_to_rad(deg: float) -> float:
    return math.radians(deg)


@dataclass
class AngleBatch:
    angle: Optional[int] = None
    values_cm: List[float] = None

    def __post_init__(self):
        if self.values_cm is None:
            self.values_cm = []

    def reset(self, angle: int, first_value: float) -> None:
        self.angle = angle
        self.values_cm = [first_value]

    def add(self, value_cm: float) -> None:
        self.values_cm.append(value_cm)

    def is_full(self) -> bool:
        return len(self.values_cm) >= MAX_SAMPLES_PER_ANGLE

    def summarize(self) -> Optional[Tuple[int, float]]:
        if self.angle is None or not self.values_cm:
            return None
        vals = self.values_cm
        clusters = []
        for v in vals:
            c = [x for x in vals if abs(x - v) <= SAME_VALUE_TOLERANCE_CM]
            clusters.append(c)
        best = max(clusters, key=lambda c: (len(c), -(max(c) - min(c))))
        mean_val = round(sum(best) / len(best), 1)
        return self.angle, mean_val


class Mode1View(ModeBase):
    """
    Sonar Object Detector:
      - Reads "angle:micros" lines
      - Aggregates N samples per angle into a robust mean
      - Renders a polar scatter and overlays detected object arcs
    """

    def __init__(self, master: tk.Misc, controller: MSPController, flash_integration: bool = False):
        super().__init__(master, controller, title="מצב 1 – Sonar Object Detector",
                         enter_command="1" if not flash_integration else None, 
                         exit_command="8")
        self._flash_integration = flash_integration  # True when opened from flash mode
        
        # Data model: distances per angle (None if missing)
        self._distances_cm: List[Optional[float]] = [None] * MAX_ANGLE_DEG

        # Matplotlib bits
        self.figure: Optional[Figure] = None
        self.ax = None
        self.canvas: Optional[FigureCanvasTkAgg] = None

    # ----- ModeBase hooks -----

    def on_start(self) -> None:
        # Clear any residual data from previous modes
        self.controller.flush_input()
        
        # Reset state
        self._distances_cm = [None] * MAX_ANGLE_DEG

        # Build plot with larger size
        self.figure = Figure(figsize=(10, 8), facecolor='white')
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.canvas.draw()

        # Prepare batch for listener loop
        self._batch = AngleBatch()
        
        # Update status
        self.update_status("Mode started - scanning for objects...")

    def on_stop(self) -> None:
        # Destroy canvas widget to free resources
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        self.figure = None
        self.ax = None
        self.canvas = None

    def handle_line(self, line: str) -> None:
        # Check for '8' command from firmware when in flash integration mode
        if self._flash_integration and line.strip() == "8":
            logger.info("Sonar mode received '8' - scan finished, closing mode")
            # Stop the mode and return to flash
            self.stop()
            if self._back_cb:
                self._back_cb()
            return
            
        # Parse "angle:micros"
        try:
            a_s, us_s = line.split(":")
            angle = int(a_s)
            us = int(us_s)
            dist_cm = us * US_TO_CM
            if not (0 <= angle < MAX_ANGLE_DEG) or dist_cm <= 0:
                return
        except ValueError:
            # Log non-matching lines for debugging
            logger.debug(f"Mode1 received non-parseable line: '{line}'")
            return

        # Accumulate samples per angle
        b = self._batch
        if b.angle is None:
            b.reset(angle, dist_cm)
            # Update status when starting a new angle
            self.update_status(f"Scanning angle {angle}° - collecting samples...")
            return

        if angle != b.angle:
            self._finalize_batch()
            b.reset(angle, dist_cm)
            # Update status when moving to new angle
            self.update_status(f"Scanning angle {angle}° - collecting samples...")
            return

        b.add(dist_cm)
        if b.is_full():
            self._finalize_batch()
            b.angle = None
            b.values_cm.clear()

    def render(self) -> None:
        if not self.ax or not self.canvas:
            return

        self._configure_axes()

        # Collect points & contiguous clusters
        angles_all: List[float] = []
        dists_all: List[float] = []
        clusters: List[List[tuple[int, float]]] = []
        cur: List[tuple[int, float]] = []

        for idx, dist in enumerate(self._distances_cm):
            if dist is not None:
                angles_all.append(deg_to_rad(idx))
                dists_all.append(dist)

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

        # Plot all scan points
        if angles_all:
            self.ax.scatter(angles_all, dists_all, c="lime", s=10)

        # Draw object arcs + labels
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

        self.canvas.draw_idle()

    # ----- Helpers -----

    def _configure_axes(self) -> None:
        self.ax.clear()
        self.ax.set_theta_zero_location("E")  # 0° at right
        self.ax.set_theta_direction(1)        # clockwise
        self.ax.set_thetamin(0)
        self.ax.set_thetamax(MAX_ANGLE_DEG)
        self.ax.set_rlim(0, PLOT_R_MAX_CM)
        
        # Add title and improve formatting
        self.ax.set_title("Sonar Object Detection\nPolar View", pad=20, fontsize=14, fontweight='bold')
        self.ax.set_ylabel("Distance (cm)", labelpad=30, fontsize=12)
        self.ax.grid(True, alpha=0.3)
        
        # Add degree markings
        theta_ticks = range(0, 180, 30)
        self.ax.set_thetagrids(theta_ticks, [f"{t}°" for t in theta_ticks])
        
        # Create legend elements (will be added during render)
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='lime', markersize=8, label='* Scan Points'),
            Line2D([0], [0], color='red', linewidth=3, label='-> Detected Objects'),
            Patch(facecolor='white', edgecolor='blue', alpha=0.6, label='[i] Object Info')
        ]
        self.ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(0.02, 0.98), fontsize=10)

    def _finalize_batch(self) -> None:
        res = self._batch.summarize()
        if res is None:
            return
        angle, mean_cm = res
        self._distances_cm[angle] = mean_cm
