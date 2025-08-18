from __future__ import annotations

import tkinter as tk
from typing import Optional

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController


class Mode6LDRCalibView(ModeBase):
    """
    Mode 6 – LDR Calibration.
    Shows a step-by-step instruction message for each of the 10 calibration points.
    The MCU sends lines "6:<step>" when a measurement is stored and "6:DONE" at the end.
    """

    def __init__(self, master: tk.Misc, controller: MSPController):
        super().__init__(master, controller,
                         title="Mode 6 – LDR Calibration",
                         enter_command="6",
                         exit_command="8")

        self._msg_var = tk.StringVar()
        self._done = False
        # Predefined distances for each calibration step (1..10)
        # Distances per step (consistent with ldr_utils: 4,8,...,40 cm)
        self._distances_cm = [4 * i for i in range(1, 11)]
        self._next_step = 1  # what we instruct the user to do next

    # --- ModeBase hooks ---

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)

        ttk.Label(wrap, text="Follow the on-screen instructions to collect 10 calibration points.", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, textvariable=self._msg_var, style="TLabel", wraplength=800, justify="left").pack(anchor="w")

        # Initialize first instruction
        self._done = False
        self._next_step = 1
        self._update_instruction()

    def on_stop(self) -> None:
        pass

    def handle_line(self, line: str) -> None:
        """Handle MCU progress lines: "6:<step>" or "6:DONE"."""
        if not line:
            return

        # Trim potential echo/whitespace
        s = line.strip()

        if s.startswith("6:"):
            payload = s[2:]
            if payload.upper() == "DONE":
                self._done = True
                self._msg_var.set("Calibration complete. You can exit the mode.")
                return
            # Expect a number after "6:"
            try:
                last_completed = int(payload)
            except ValueError:
                # Not a number; show raw line
                self._msg_var.set(s)
                return

            # Compute the next step to instruct
            if last_completed >= 10:
                self._done = True
                self._msg_var.set("Calibration complete. You can exit the mode.")
            else:
                self._next_step = last_completed + 1
                self._update_instruction()
        else:
            # Fallback: show raw line
            self._msg_var.set(s)

    def render(self) -> None:
        pass

    # --- Helpers ---

    def _update_instruction(self) -> None:
        if self._done:
            self._msg_var.set("Calibration complete. You can exit the mode.")
            return

        step = self._next_step
        # Guard
        if step < 1:
            step = 1
        if step > 10:
            step = 10

        dist = self._distances_cm[step - 1]
        # Build the required sentence:
        # "Measurement y - The controller is waiting for calibration x centimeters, ... press push button 1"
        msg = (
            f"Measurement {step} - The controller is waiting for calibration {dist} centimeters, "
            f"please place a light spot in front of the sensor at a distance of {dist} centimeters "
            f"and press push button 1."
        )
        self._msg_var.set(msg)
