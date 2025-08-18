from __future__ import annotations

import io
import os
import time
from typing import Optional, List
import math

import tkinter as tk
from tkinter import filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.translators.script_encoder import encode_script_text  # NEW


# ---- Protocol constants (keep EOF sentinel) ----
RX_EOF = b"\n"
EOF_CHAR = b"+"     # final-chunk terminator
CHUNK_SIZE = 60      # safe for RX_BUF_SIZE = 80 (allows delimiter + headroom)

# ---- Constants for telemetry sub-mode ----
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

def _to_ascii_hex(data: bytes) -> bytes:
    """Return uppercase ASCII-HEX representation (no spaces)."""
    return data.hex().upper().encode("ascii")


def detect_file_type(path: str, sample: bytes | None = None) -> str:
    """
    Return one of:
      - 'text'               → send raw text
      - 'executable-source'  → treat as high-level script SOURCE; compile to opcodes, then send
      - 'executable'         → generic binary
    Policy: *.exe / *.scr / *.script are treated as script *sources* to compile.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in {".exe", ".scr", ".script"}:
        return "executable-source"

    if sample is None:
        try:
            with open(path, "rb") as f:
                sample = f.read(4096)
        except Exception:
            sample = b""

    if b"\x00" in (sample or b""):
        return "executable"
    try:
        (sample or b"").decode("utf-8")
        return "text"
    except Exception:
        return "executable"


def make_name_10_bytes(path: str) -> bytes:
    """
    MCU stores up to 10 bytes for the name (no extension in this helper).
    Use the stem, ASCII only, truncated/padded by protocol on MCU side.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    name_bytes = stem.encode("ascii", "ignore") or b"file"
    return name_bytes[:10]  # MCU will copy up to 10 anyway


class Mode5FlashView(ModeBase):
    """
    Mode 5 – Flash / File Manager (Write implemented)
      - On start: send '5'
      - Write: 'w' → Name\n → Type('1' text / '0' script)\n → Size\n
                → Content in chunks: each chunk ends with '\n', the *final* chunk ends with EOF_CHAR ('+')
      - Execute: 'e' → enters execution mode, can receive '2' for telemetry sub-mode
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
        
        # Telemetry sub-mode state
        self._in_telemetry_mode = False
        self._current_angle: Optional[int] = None
        self._recent_cm: List[float] = []
        
        # Telemetry UI elements
        self.telemetry_frame: Optional[tk.Frame] = None
        self.lbl_angle_value: Optional[tk.Label] = None
        self.lbl_dist_value: Optional[tk.Label] = None
        self.figure: Optional[Figure] = None
        self.ax = None
        self.canvas: Optional[FigureCanvasTkAgg] = None

    # ----- Lifecycle -----

    def on_start(self) -> None:
        import tkinter.ttk as ttk
        
        # Header section
        header = ttk.Frame(self.body, style="TFrame")
        header.pack(fill="x", padx=15, pady=(15, 10))
        
        ttk.Label(header, text="💾 Flash Memory Management", 
                 style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Upload, download, and execute files on the MSP430 microcontroller", 
                 style="Sub.TLabel").pack(anchor="w", pady=(5, 0))

        # Action buttons with icons
        action_frame = ttk.LabelFrame(self.body, text="📋 Operations", padding=15)
        action_frame.pack(fill="x", padx=15, pady=10)

        button_frame = ttk.Frame(action_frame, style="TFrame")
        button_frame.pack(fill="x")

        ttk.Button(button_frame, text="📤 Upload File", command=self._do_write, 
                  style="TButton", width=20).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="📥 Download File", command=self._do_read, 
                  style="TButton", width=20).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="▶️ Execute File", command=self._do_execute, 
                  style="TButton", width=20).grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Configure grid weights
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        # File information panel with better styling
        info_frame = ttk.LabelFrame(self.body, text="📄 File Information", padding=15)
        info_frame.pack(fill="x", padx=15, pady=10)

        # Create a grid for better organization
        info_grid = ttk.Frame(info_frame, style="TFrame")
        info_grid.pack(fill="x")

        # Status row
        ttk.Label(info_grid, text="Status:", style="Sub.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.lbl_status = ttk.Label(info_grid, text="Ready", style="TLabel")
        self.lbl_status.grid(row=0, column=1, sticky="w")

        # File name row
        ttk.Label(info_grid, text="File Name:", style="Sub.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.lbl_name = ttk.Label(info_grid, text="—", style="TLabel")
        self.lbl_name.grid(row=1, column=1, sticky="w", pady=(5, 0))

        # File type row
        ttk.Label(info_grid, text="File Type:", style="Sub.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.lbl_type = ttk.Label(info_grid, text="—", style="TLabel")
        self.lbl_type.grid(row=2, column=1, sticky="w", pady=(5, 0))

        # File size row
        ttk.Label(info_grid, text="File Size:", style="Sub.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.lbl_size = ttk.Label(info_grid, text="—", style="TLabel")
        self.lbl_size.grid(row=3, column=1, sticky="w", pady=(5, 0))

        # Instructions panel
        instructions = ttk.LabelFrame(self.body, text="ℹ️ Instructions", padding=15)
        instructions.pack(fill="both", expand=True, padx=15, pady=10)

        instructions_text = """
📤 Upload File: Select a file from your computer to upload to the MSP430 flash memory
📥 Download File: Retrieve a file from the MSP430 flash memory to your computer  
▶️ Execute File: Run a script or program stored in the MSP430 flash memory

Supported file types:
• Text files (.txt, .log) - Stored as plain text
• Script files (.exe, .scr, .script) - Compiled to opcodes before upload
• Binary files - Stored as executable binary data

Note: The MSP430 has limited flash memory. Large files may not fit.
        """
        
        ttk.Label(instructions, text=instructions_text.strip(), 
                 style="TLabel", justify="left").pack(anchor="w")

    def on_stop(self) -> None:
        self._busy = False  # allow next entry to write
        
        # Clean up telemetry mode if active
        if self._in_telemetry_mode:
            self._cleanup_telemetry_ui()
            self._in_telemetry_mode = False
            self._recent_cm.clear()
            self._current_angle = None

    def handle_line(self, line: str) -> None:
        # Check if we're receiving "2" to enter telemetry sub-mode
        if line.strip() == "2" and not self._in_telemetry_mode:
            self._enter_telemetry_mode()
            return
            
        # If in telemetry mode, handle angle:distance data
        if self._in_telemetry_mode:
            self._handle_telemetry_line(line)
        # Flash mode doesn't stream continuous data for 'write'; ignore for now

    def render(self) -> None:
        if self._in_telemetry_mode:
            self._render_telemetry()
        # Otherwise, no continuous rendering needed for flash mode

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
                ("Script/Text files", "*.txt;*.scr;*.script"),
                ("Executables (script source)", "*.exe;*.scr;*.script"),
                ("Binaries / Executables", "*.bin;*.elf;*.img;*.hex")
            ]
        )
        if not path:
            if self.lbl_status:
                self.lbl_status.config(text="בוטל על ידי המשתמש")
            self._busy = False
            return

        # 3) Read file & decide payload/type
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            if self.lbl_status:
                self.lbl_status.config(text=f"שגיאה בקריאת קובץ: {e}")
            self._busy = False
            return

        kind = detect_file_type(path, sample=raw[:4096])
        try:
            if kind == "executable-source":
                # Treat as script text → encode to opcode BYTES, then send as ASCII-HEX
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="ignore")

                compiled_bytes = encode_script_text(text)  # e.g. b'\x01\x0A\x04\x1E...'
                payload = _to_ascii_hex(compiled_bytes)  # b'010A041E0214050623011407143C08'
                type_char = b"0"  # store as executable/script
                shown_type = "executable (compiled HEX)"

            elif kind == "text":
                payload = raw
                type_char = b"1"
                shown_type = "text"
            else:
                # generic binary; keep existing behavior (store as '0')
                payload = raw
                type_char = b"0"
                shown_type = "executable"
        except Exception as e:
            if self.lbl_status:
                self.lbl_status.config(text=f"שגיאת תרגום: {e}")
            self._busy = False
            return

        size = len(payload)

        # 4) Show metadata
        if self.lbl_name: self.lbl_name.config(text=os.path.basename(path))
        if self.lbl_type: self.lbl_type.config(text=shown_type)
        if self.lbl_size: self.lbl_size.config(text=str(size))
        if self.lbl_status: self.lbl_status.config(text="שולח מטה-דאטה...")

        # 5) Send Name\n → Type\n → Size\n
        name10 = make_name_10_bytes(path)  # ≤10 bytes
        self.controller.send_command(name10 + RX_EOF)
        self.controller.send_command(type_char + RX_EOF)
        self.controller.send_command(str(size).encode("ascii") + RX_EOF)

        # 6) Stream content in chunks, newline-terminated; final chunk ends with EOF_CHAR
        sent = 0
        try:
            bio = io.BytesIO(payload)
            while sent < size:
                chunk = bio.read(min(CHUNK_SIZE, size - sent))
                if not chunk:
                    break
                sent += len(chunk)
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

    def _do_read(self) -> None:
        if self._busy:
            return
        self._busy = True

        # 1) Tell controller: we choose READ
        self.controller.send_command('r')

    def _do_execute(self) -> None:
        if self._busy:
            return
        self._busy = True

        # 1) Tell controller: we choose Execute
        self.controller.send_command('e')
        
        # Update status
        if self.lbl_status:
            self.lbl_status.config(text="Execute mode - waiting for script commands...")
        
        self._busy = False

    # ----- Telemetry Sub-Mode Methods -----
    
    def _enter_telemetry_mode(self) -> None:
        """Enter telemetry sub-mode when '2' is received during execute mode."""
        self._in_telemetry_mode = True
        self._recent_cm.clear()
        self._current_angle = None
        
        # Hide the main flash UI and show telemetry UI
        self._hide_main_ui()
        self._create_telemetry_ui()
        
        if self.lbl_status:
            self.lbl_status.config(text="Telemetry Mode - receiving angle:distance data")
    
    def _exit_telemetry_mode(self) -> None:
        """Exit telemetry sub-mode and return to execute mode."""
        self._in_telemetry_mode = False
        self._recent_cm.clear()
        self._current_angle = None
        
        # Clean up telemetry UI
        self._cleanup_telemetry_ui()
        
        # Restore main UI
        self._show_main_ui()
        
        # Send '8' to controller to exit telemetry mode
        self.controller.send_command('8')
        
        if self.lbl_status:
            self.lbl_status.config(text="Returned to Execute mode")
    
    def _handle_telemetry_line(self, line: str) -> None:
        """Handle incoming telemetry data in format 'angle:micros'."""
        try:
            a_s, us_s = line.split(":")
            angle = int(a_s)
            micros = int(us_s)
            cm = micros * US_TO_CM
            if cm <= 0:
                return
        except ValueError:
            return

        self._current_angle = angle
        self._recent_cm.append(cm)
        if len(self._recent_cm) > MAX_SAMPLES:
            del self._recent_cm[:-MAX_SAMPLES]
    
    def _create_telemetry_ui(self) -> None:
        """Create the telemetry mode UI similar to Mode 2."""
        import tkinter.ttk as ttk
        
        # Create telemetry frame that covers the main UI
        self.telemetry_frame = ttk.Frame(self.body, style="TFrame")
        self.telemetry_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Header
        header = ttk.Frame(self.telemetry_frame, style="TFrame")
        header.pack(fill="x", pady=(0, 10))
        
        ttk.Label(header, text="📡 Telemetry Mode (Script Execute)", 
                 style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Receiving real-time angle and distance data from script execution", 
                 style="Sub.TLabel").pack(anchor="w", pady=(5, 0))
        
        # Exit button
        exit_frame = ttk.Frame(header, style="TFrame")
        exit_frame.pack(anchor="e", pady=(10, 0))
        ttk.Button(exit_frame, text="🚪 Exit Telemetry Mode", 
                  command=self._exit_telemetry_mode, 
                  style="TButton").pack()
        
        # Live readout
        info = ttk.LabelFrame(self.telemetry_frame, text="📊 Live Data", padding=10)
        info.pack(fill="x", pady=10)
        
        info_grid = ttk.Frame(info, style="TFrame")
        info_grid.pack(fill="x")
        
        ttk.Label(info_grid, text="Current Angle:", style="Sub.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.lbl_angle_value = ttk.Label(info_grid, text="—", style="TLabel")
        self.lbl_angle_value.grid(row=0, column=1, sticky="w")
        
        ttk.Label(info_grid, text="Distance:", style="Sub.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.lbl_dist_value = ttk.Label(info_grid, text="— cm", style="TLabel")
        self.lbl_dist_value.grid(row=1, column=1, sticky="w", pady=(5, 0))
        
        # Plot
        self.figure = Figure(figsize=(8, 6), facecolor='white')
        self.ax = self.figure.add_subplot(111, polar=True)
        self._configure_telemetry_axes()
        
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.telemetry_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=10)
        self.canvas.draw()
    
    def _configure_telemetry_axes(self) -> None:
        """Configure the polar plot axes for telemetry display."""
        if not self.ax:
            return
        self.ax.clear()
        self.ax.set_ylim(0, PLOT_R_MAX_CM)
        self.ax.set_theta_zero_location('N')
        self.ax.set_theta_direction(-1)
        self.ax.set_title("Real-time Distance Measurement", pad=20)
        self.ax.set_rlabel_position(45)
        self.ax.grid(True, alpha=0.3)
    
    def _render_telemetry(self) -> None:
        """Update telemetry display with current data."""
        if not self._in_telemetry_mode:
            return
            
        # Update labels
        if self._current_angle is None:
            if self.lbl_angle_value:
                self.lbl_angle_value.config(text="—")
            if self.lbl_dist_value:
                self.lbl_dist_value.config(text="— cm")
        else:
            if self.lbl_angle_value:
                self.lbl_angle_value.config(text=f"{self._current_angle}°")
            cm = robust_mean(self._recent_cm)
            if self.lbl_dist_value:
                self.lbl_dist_value.config(text=f"{cm:.1f} cm" if cm is not None else "— cm")
        
        # Update plot
        if not (self.ax and self.canvas):
            return
        self._configure_telemetry_axes()
        
        if self._current_angle is not None and self._recent_cm:
            cm = robust_mean(self._recent_cm)
            if cm is not None and cm <= PLOT_R_MAX_CM:
                theta = deg_to_rad(self._current_angle)
                self.ax.plot([theta, theta], [0, cm], 'b-', linewidth=3, alpha=0.8)
                self.ax.scatter([theta], [cm], c='red', s=50, zorder=5)
        
        self.canvas.draw()
    
    def _hide_main_ui(self) -> None:
        """Hide the main flash UI elements."""
        for widget in self.body.winfo_children():
            if widget != self.telemetry_frame:
                widget.pack_forget()
    
    def _show_main_ui(self) -> None:
        """Restore the main flash UI elements."""
        # This will be called when exiting telemetry mode
        # We need to recreate the main UI since we packed_forget everything
        self.on_start()
    
    def _cleanup_telemetry_ui(self) -> None:
        """Clean up telemetry UI elements."""
        if self.telemetry_frame:
            self.telemetry_frame.destroy()
            self.telemetry_frame = None
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        self.figure = None
        self.ax = None
        self.canvas = None
        self.lbl_angle_value = None
        self.lbl_dist_value = None