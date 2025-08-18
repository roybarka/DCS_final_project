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
        # Distances per step (consistent with ldr_utils: 3,6,...,30 cm)
        self._distances_cm = [3 * i for i in range(1, 11)]
        self._next_step = 1  # what we instruct the user to do next

    # --- ModeBase hooks ---

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        
        # Header section
        header = ttk.Frame(self.body, style="TFrame")
        header.pack(fill="x", padx=20, pady=(20, 15))
        
        ttk.Label(header, text="⚙️ LDR Sensor Calibration", 
                 style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Follow the step-by-step instructions to calibrate the light sensor", 
                 style="Sub.TLabel").pack(anchor="w", pady=(5, 0))

        # Progress section
        progress_frame = ttk.LabelFrame(self.body, text="📊 Calibration Progress", padding=15)
        progress_frame.pack(fill="x", padx=20, pady=10)

        self.progress_var = tk.StringVar(value="0/10 measurements completed")
        ttk.Label(progress_frame, textvariable=self.progress_var, style="Sub.TLabel").pack(anchor="w")

        # Progress bar
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress_bar.pack(fill="x", pady=(10, 0))
        self.progress_bar['maximum'] = 10

        # Instructions section
        instruction_frame = ttk.LabelFrame(self.body, text="📋 Current Step", padding=15)
        instruction_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Instruction text with larger, more readable font
        self.instruction_label = ttk.Label(instruction_frame, textvariable=self._msg_var, 
                                         style="TLabel", wraplength=700, justify="left")
        self.instruction_label.pack(anchor="w", pady=10)
        
        # Tips section
        tips_frame = ttk.LabelFrame(self.body, text="💡 Calibration Tips", padding=15)
        tips_frame.pack(fill="x", padx=20, pady=10)
        
        tips_text = """
• Use a ruler or measuring tape for accurate distance measurements
• Ensure consistent lighting conditions throughout calibration
• Position the light source directly in front of the LDR sensor
• Wait for the measurement to complete before moving to the next step
• Keep the sensor and light source stable during each measurement
        """
        
        ttk.Label(tips_frame, text=tips_text.strip(), style="TLabel", justify="left").pack(anchor="w")

        # Initialize calibration
        self._done = False
        self._next_step = 1
        self._update_instruction()
        self._update_progress()

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
                self._msg_var.set("🎉 Calibration complete! The LDR sensor is now ready for use. You can exit this mode.")
                self._update_progress()
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
                self._msg_var.set("🎉 Calibration complete! The LDR sensor is now ready for use. You can exit this mode.")
                self._update_progress()
            else:
                self._next_step = last_completed + 1
                self._update_instruction()
                self._update_progress()
        else:
            # Fallback: show raw line
            self._msg_var.set(s)

    def render(self) -> None:
        pass

    # --- Helpers ---

    def _update_instruction(self) -> None:
        if self._done:
            self._msg_var.set("🎉 Calibration complete! The LDR sensor is now ready for use. You can exit this mode.")
            return

        step = self._next_step
        # Guard
        if step < 1:
            step = 1
        if step > 10:
            step = 10

        dist = self._distances_cm[step - 1]
        # Build enhanced instruction message
        msg = (
            f"📍 Step {step} of 10\n\n"
            f"🎯 Target Distance: {dist} cm\n\n"
            f"📋 Instructions:\n"
            f"1. Position the light source exactly {dist} cm from the LDR sensor\n"
            f"2. Ensure the light is pointing directly at the sensor\n"
            f"3. Press push button 1 on the MSP430 to take the measurement\n"
            f"4. Wait for confirmation before proceeding to the next step"
        )
        self._msg_var.set(msg)

    def _update_progress(self) -> None:
        """Update progress bar and progress text."""
        if self._done:
            completed = 10
            self.progress_var.set("10/10 measurements completed - Calibration finished!")
        else:
            completed = max(0, self._next_step - 1)
            self.progress_var.set(f"{completed}/10 measurements completed")
        
        if hasattr(self, 'progress_bar'):
            self.progress_bar['value'] = completed
