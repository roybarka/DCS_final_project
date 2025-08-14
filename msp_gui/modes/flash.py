from __future__ import annotations

import os
import time
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController


# ---- Protocol constants (adjust EOF_CHAR if your firmware differs) ----
RX_EOF = b"\n"
EOF_CHAR = b"+"     # but ideally stop sending this and rely on size
CHUNK_SIZE = 60      # safe for RX_BUF_SIZE = 80 (allows delimiter + headroom)



def detect_file_type(path: str) -> str:
    """Return 'text' if the file looks textual, otherwise 'executable'."""
    exec_exts = {".exe", ".elf", ".bin", ".hex", ".img", ".o", ".dll"}
    ext = os.path.splitext(path)[1].lower()
    if ext in exec_exts:
        return "executable"
    try:
        with open(path, "rb") as f:
            sample = f.read(4096)
        if b"\x00" in sample:
            return "executable"
        sample.decode("utf-8")
        return "text"
    except Exception:
        return "executable"


def make_name_10_bytes(path: str) -> bytes:
    """
    MCU stores up to 10 bytes for the name (no extension in this helper).
    Use the stem, ASCII only, truncated/padded by protocol on MCU side.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    name_bytes = stem.encode("ascii", "ignore")
    if not name_bytes:
        name_bytes = b"file"
    return name_bytes[:10]  # MCU will copy up to 10 anyway


class Mode5FlashView(ModeBase):
    """
    Mode 5 – Flash / File Manager (Write implemented)
      - On start: send '5'
      - Write: 'w' → send Name\n → Type('1' text / '0' script)\n → Size\n → Content (chunks '\n', final EOF_CHAR)
    """

    def __init__(self, master: tk.Misc, controller: MSPController):
        super().__init__(master, controller,
                         title="מצב 5 – ניהול קבצים (Flash)",
                         enter_command="5",
                         exit_command="8")
        self.lbl_status: Optional[tk.Label] = None
        self.lbl_name: Optional[tk.Label] = None
        self.lbl_type: Optional[tk.Label] = None
        self.lbl_size: Optional[tk.Label] = None
        self._busy = False  # simple guard to avoid double-sends

    # ----- Lifecycle -----

    def on_start(self) -> None:
        # Controls
        ctr = tk.Frame(self.body)
        ctr.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(ctr, text="בחר פעולה:").pack(side="left", padx=(0, 10))
        tk.Button(ctr, text="Write", command=self._do_write).pack(side="left", padx=4)
        tk.Button(ctr, text="Read", state="disabled",
                  command=lambda: messagebox.showinfo("בקרוב", "קריאה טרם מומשה")).pack(side="left", padx=4)
        tk.Button(ctr, text="Execute", state="disabled",
                  command=lambda: messagebox.showinfo("בקרוב", "הרצה טרם מומשה")).pack(side="left", padx=4)

        # Metadata panel
        info = tk.LabelFrame(self.body, text="מידע קובץ")
        info.pack(fill="x", padx=10, pady=(6, 10))

        row1 = tk.Frame(info); row1.pack(fill="x", padx=8, pady=4)
        tk.Label(row1, text="סטטוס:", width=12, anchor="w").pack(side="left")
        self.lbl_status = tk.Label(row1, text="מוכן (בחר פעולה)")
        self.lbl_status.pack(side="left")

        row2 = tk.Frame(info); row2.pack(fill="x", padx=8, pady=4)
        tk.Label(row2, text="שם קובץ:", width=12, anchor="w").pack(side="left")
        self.lbl_name = tk.Label(row2, text="—")
        self.lbl_name.pack(side="left")

        row3 = tk.Frame(info); row3.pack(fill="x", padx=8, pady=4)
        tk.Label(row3, text="סוג:", width=12, anchor="w").pack(side="left")
        self.lbl_type = tk.Label(row3, text="—")
        self.lbl_type.pack(side="left")

        row4 = tk.Frame(info); row4.pack(fill="x", padx=8, pady=4)
        tk.Label(row4, text="גודל (bytes):", width=12, anchor="w").pack(side="left")
        self.lbl_size = tk.Label(row4, text="—")
        self.lbl_size.pack(side="left")

    def on_stop(self) -> None:
        self._busy = False  # allow next entry to write

    def handle_line(self, line: str) -> None:
        # Flash mode doesn't stream continuous data for 'write'; ignore for now
        pass

    def render(self) -> None:
        pass

    # ----- Actions -----

    def _do_write(self) -> None:
        if self._busy:
            return
        self._busy = True

        # 1) Tell controller: we choose WRITE
        self.controller.send_command('w')
        if self.lbl_status:
            self.lbl_status.config(text="נשלח: 'w' – בחר קובץ...")
        # small breath so the MCU switches flash_state/write_stage
        time.sleep(0.05)

        # 2) Pick a file
        path = filedialog.askopenfilename(
            title="בחר קובץ לכתיבה ל-Flash",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt;*.csv;*.json;*.xml;*.hex;*.ini;*.log"),
                ("Binaries / Executables", "*.bin;*.exe;*.elf;*.img")
            ]
        )
        if not path:
            if self.lbl_status:
                self.lbl_status.config(text="בוטל על ידי המשתמש")
            self._busy = False
            return

        # 3) Prepare metadata
        try:
            size = os.path.getsize(path)
            name10 = make_name_10_bytes(path)  # ≤10 bytes
            kind = detect_file_type(path)
            type_char = b"1" if kind == "text" else b"0"
        except Exception as e:
            if self.lbl_status:
                self.lbl_status.config(text=f"שגיאה בקריאת קובץ: {e}")
            self._busy = False
            return

        # Show metadata
        if self.lbl_name: self.lbl_name.config(text=os.path.basename(path))
        if self.lbl_type: self.lbl_type.config(text=kind)
        if self.lbl_size: self.lbl_size.config(text=str(size))
        if self.lbl_status: self.lbl_status.config(text="שולח מטה-דאטה...")

        # 4) Send Name\n → Type\n → Size\n
        self.controller.send_command(name10 + RX_EOF)
        self.controller.send_command(type_char + RX_EOF)
        self.controller.send_command(str(size).encode("ascii") + RX_EOF)

        # 5) Stream content in chunks, newline-terminated; final chunk ends with EOF_CHAR
        sent = 0
        try:
            with open(path, "rb") as f:
                while sent < size:
                    to_read = min(CHUNK_SIZE, size - sent)
                    chunk = f.read(to_read)
                    if not chunk:
                        break
                    sent += len(chunk)
                    # final chunk?
                    terminator = EOF_CHAR if sent >= size else RX_EOF
                    self.controller.send_command(chunk + terminator)

                    if self.lbl_status:
                        pct = int((sent / max(1, size)) * 100)
                        self.lbl_status.config(text=f"שולח תוכן... {pct}%")

            if self.lbl_status:
                self.lbl_status.config(text="העברה הושלמה")
        except Exception as e:
            if self.lbl_status:
                self.lbl_status.config(text=f"שגיאה בשליחה: {e}")
        finally:
            self._busy = False
