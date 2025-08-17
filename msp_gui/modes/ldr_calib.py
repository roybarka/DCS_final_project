from __future__ import annotations

import tkinter as tk
from typing import Optional

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController


class Mode6LDRCalibView(ModeBase):
    """
    Mode 6 – LDR Calibration.
    On start: send '6' (controller does the calibration).
    Use the top bar "עצור וחזור לתפריט" to exit (sends '8').
    """

    def __init__(self, master: tk.Misc, controller: MSPController):
        super().__init__(master, controller,
                         title="מצב 6 – כיול LDR",
                         enter_command="6",   # enter calibration mode
                         exit_command="8")    # default exit

        self._last_line_var = tk.StringVar(value="מחכה לעדכון מהבקר...")

    # --- ModeBase hooks ---

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        wrap = ttk.Frame(self.body, style="TFrame")
        wrap.pack(fill="both", expand=True, padx=18, pady=18)

        ttk.Label(wrap, text="הכיול מתבצע בבקר. המתן להשלמה.", style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(wrap, text="סטטוס אחרון מהבקר:", style="Sub.TLabel").pack(anchor="w")
        ttk.Label(wrap, textvariable=self._last_line_var, style="TLabel").pack(anchor="w", pady=(2, 0))

        # (Optional) small note
        ttk.Label(wrap, text="ניתן לצאת בכל עת באמצעות הכפתור למעלה.", style="TLabel").pack(anchor="w", pady=(14, 0))

    def on_stop(self) -> None:
        # no special cleanup needed
        pass

    def handle_line(self, line: str) -> None:
        # Just show the latest line from the controller (if it prints progress/done)
        self._last_line_var.set(line)

    def render(self) -> None:
        # No periodic UI other than incoming lines
        pass
