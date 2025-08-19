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

    def __init__(self, master: tk.Misc, controller: MSPController, script_mode: bool = False):
        # We handle the initial '2' + angle ourselves in on_start
        super().__init__(master, controller,
                         title="מצב 2 – Angle Motor Rotation",
                         enter_command=None,
                         exit_command="8")
        # State
        self._current_angle: Optional[int] = None
        self._recent_cm: List[float] = []
        self._script_mode = script_mode  # True when opened from flash execution

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
        import tkinter.ttk as ttk
        # Clear any residual data from previous modes
        self.controller.flush_input()
        
        # Controls row
        ctr = ttk.Frame(self.body, style="TFrame")
        ctr.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(ctr, text="זווית (0–179):", style="Sub.TLabel").pack(side="left")
        spin = tk.Spinbox(ctr, from_=0, to=179, width=5, textvariable=self.angle_var, font=("Segoe UI", 11))
        spin.pack(side="left", padx=(6, 12))

        apply_btn = ttk.Button(ctr, text="סובב לזווית", command=self._apply_angle, style="TButton")
        apply_btn.pack(side="left", padx=(0, 14))
        
        # Disable controls in script mode
        if self._script_mode:
            spin.config(state="disabled")
            apply_btn.config(state="disabled")
            ttk.Label(ctr, text="(Script Mode - Servo Controlled by Firmware)", style="Sub.TLabel").pack(side="left", padx=(10, 0))

        # Live readout row
        info = ttk.Frame(self.body, style="TFrame")
        info.pack(fill="x", padx=12, pady=(6, 12))

        ttk.Label(info, text="זווית נבחרת:", style="Sub.TLabel").pack(side="left")
        self.lbl_angle_value = ttk.Label(info, text="—", style="TLabel")
        self.lbl_angle_value.pack(side="left", padx=(4, 24))

        ttk.Label(info, text="מרחק:", style="Sub.TLabel").pack(side="left")
        self.lbl_dist_value = ttk.Label(info, text="— cm", style="TLabel")
        self.lbl_dist_value.pack(side="left", padx=(4, 24))

        # Plot
        self.figure = Figure(figsize=(10, 7), facecolor='white')
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_axes()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.body)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.canvas.draw()

        # Initialize state differently based on mode
        if self._script_mode:
            # In script mode, we accept whatever angle the firmware sends
            self._current_angle = None  # Will be set from first received data
            self._recent_cm.clear()
            self.update_status("Script mode - waiting for angle data from firmware...")
            # Don't send any commands - the firmware is in control
        else:
            # In manual mode, we control the angle
            initial = int(self.angle_var.get())
            self._current_angle = initial
            self._recent_cm.clear()
            
            # Update status
            self.update_status(f"Manual mode - setting initial angle to {initial}°")
            
            # Send initial angle command
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
        """Expect 'angle:micros' and accept samples based on mode."""
        
        # Check for '8' command from firmware when in flash integration mode (though servo_deg doesn't auto-end)
        if self._script_mode and line.strip() == "8":
            logger.info("Angle mode received '8' - operation finished, closing mode")
            # Stop the mode and return to flash
            self.stop()
            if self._back_cb:
                self._back_cb()
            return
            
        try:
            a_s, us_s = line.split(":")
            angle = int(a_s)
            micros = int(us_s)
            cm = micros * US_TO_CM
            if cm <= 0:
                return
        except ValueError:
            # Log non-matching lines for debugging
            logger.debug(f"Mode2 received non-parseable line: '{line}'")
            return

        if self._script_mode:
            # In script mode, accept any angle and update our current angle
            if self._current_angle is None:
                self._current_angle = angle
                self.angle_var.set(str(angle))  # Update the UI spinbox
                self.update_status(f"Script mode - servo at {angle}°, collecting measurements...")
            elif angle != self._current_angle:
                # Angle changed in script, update our tracking
                self._current_angle = angle
                self.angle_var.set(str(angle))
                self._recent_cm.clear()  # Reset measurements for new angle
                self.update_status(f"Script mode - servo moved to {angle}°, collecting measurements...")
        else:
            # In manual mode, only accept data for the angle we commanded
            if self._current_angle is None or angle != self._current_angle:
                logger.debug(f"Mode2 ignoring angle {angle}, expecting {self._current_angle}")
                return

        self._recent_cm.append(cm)
        if len(self._recent_cm) > MAX_SAMPLES:
            del self._recent_cm[:-MAX_SAMPLES]
            
        # Update status with latest measurement
        if self._script_mode:
            self.update_status(f"Script mode - measuring angle {angle}° - {len(self._recent_cm)} samples collected")
        else:
            self.update_status(f"Manual mode - measuring angle {angle}° - {len(self._recent_cm)} samples collected")

    def render(self) -> None:
        # Labels
        if self._current_angle is None:
            self.lbl_angle_value.config(text="—")
            self.lbl_dist_value.config(text="— cm")
        else:
            self.lbl_angle_value.config(text=f"{self._current_angle}°")
            cm = robust_mean(self._recent_cm)
            if cm is not None:
                self.lbl_dist_value.config(text=f"{cm:.1f} cm")
                # Update connection status to show active measurement
                self.update_connection_status(True)
            else:
                self.lbl_dist_value.config(text="— cm")

        # Plot
        if not (self.ax and self.canvas):
            return
        self._configure_axes()

        if self._current_angle is not None:
            a = deg_to_rad(self._current_angle)
            cm = robust_mean(self._recent_cm)
            r = PLOT_R_MAX_CM if cm is None else min(cm, PLOT_R_MAX_CM)
            
            # Draw servo direction line
            self.ax.plot([a, a], [0, r], linewidth=3, color='blue', alpha=0.8, label='Servo Direction')
            
            # Draw measurement point if we have valid data
            if cm is not None and cm <= PLOT_R_MAX_CM:
                self.ax.scatter([a], [cm], s=50, color='red', zorder=5, label='Distance Measurement')
                
                # Add text annotation with distance
                self.ax.text(a, cm + 5, f"{cm:.1f} cm", 
                           ha="center", va="bottom", fontsize=10, fontweight='bold',
                           bbox=dict(facecolor="white", alpha=0.8, edgecolor="black"))

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
        self.ax.set_title("Servo Motor Angle Control\nDistance Measurement", pad=20, fontsize=14, fontweight='bold')
        self.ax.set_ylabel("Distance (cm)", labelpad=30, fontsize=12)
        self.ax.grid(True, alpha=0.3)
        
        # Add degree markings
        theta_ticks = range(0, 180, 30)
        self.ax.set_thetagrids(theta_ticks, [f"{t}°" for t in theta_ticks])
        
        # Create legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color='C0', linewidth=3, label='-> Servo Direction'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='C0', markersize=10, label='* Distance Point'),
        ]
        self.ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(0.02, 0.98), fontsize=10)

    def _apply_angle(self) -> None:
        """Button: send '2' (no newline) then the chosen angle with newline. Only works in manual mode."""
        if self._script_mode:
            self.update_status("Cannot change angle in script mode - servo controlled by firmware")
            return
            
        try:
            val = int(self.angle_var.get())
        except Exception:
            self.update_status("Error: Invalid angle value")
            return
        if not (0 <= val < 180):
            self.update_status("Error: Angle must be between 0-179°")
            return

        self._current_angle = val
        self._recent_cm.clear()

        # Update status before sending command
        self.update_status(f"Manual mode - setting servo to angle {val}°...")

        self.controller.send_command('2')           # no newline
        self.controller.send_command(f"{val}\n")    # angle with newline
        
        logger.info(f"Mode2: Commanded servo to angle {val}°")
