from __future__ import annotations

import io
import os
import time
from typing import Optional, List

import tkinter as tk
from tkinter import filedialog, messagebox

from msp_gui.modes.base import ModeBase
from msp_gui.msp_controller import MSPController
from msp_gui.translators.script_encoder import encode_script_text

# Import Mode1View and Mode2View for GUI integration
from msp_gui.modes.sonar import Mode1View
from msp_gui.modes.angle import Mode2View


# ---- Protocol constants (keep EOF sentinel) ----
RX_EOF = b"\n"
EOF_CHAR = b"+"     # final-chunk terminator
CHUNK_SIZE = 60      # safe for RX_BUF_SIZE = 80 (allows delimiter + headroom)

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
        self._sub_mode_active = False  # Track if a sub-mode (Mode 1/2) is currently active

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

    def handle_line(self, line: str) -> None:
        # Add debugging to see what we're receiving
        print(f"Flash mode received line: '{line}' (stripped: '{line.strip()}')")
        
        # Check if we're receiving "1" to open sonar mode
        if line.strip() == "1":
            print("Received '1' - opening sonar mode!")
            self._open_sonar_mode()
            return
        
        # Check if we're receiving "2" to open angle/telemetry mode
        if line.strip() == "2":
            print("Received '2' - opening angle mode!")
            self._open_angle_mode()
            return
        
        # Flash mode doesn't stream continuous data for 'write'; ignore other lines
        print(f"Flash mode ignoring line: {line}")

    def render(self) -> None:
        # No continuous rendering needed for flash mode
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
            print("Execute button pressed but already busy")
            return
        self._busy = True
        print("Execute mode started - sending 'e' command")

        # 1) Tell controller: we choose Execute
        self.controller.send_command('e')
        
        # Update status
        if self.lbl_status:
            self.lbl_status.config(text="Execute mode - listening for telemetry commands...")
        
        print("Execute mode listening for '2' command...")
        # Don't set _busy = False here - keep listening for commands
        # The busy state will be cleared when execution completes

    # ----- Mode Integration -----
    
    def _open_sonar_mode(self) -> None:
        """Open the sonar mode (Mode 1) when '1' is received during script execution."""
        print("_open_sonar_mode called!")
        
        # Get reference to the main app window
        app = self.master
        while app and not hasattr(app, 'navigate_to_menu'):
            app = app.master
        
        if app and hasattr(app, 'navigate_to_menu'):
            print("Found main app, creating and mounting Mode 1 (Sonar)...")
            try:
                # Create a new sonar mode view with special handling for flash integration
                sonar_view = Mode1View(app, self.controller, flash_integration=True)
                
                # Create a special callback that will handle both user stop and firmware '8'
                def sonar_back_callback():
                    print("Sonar mode back callback called")
                    self._return_from_sub_mode(app)
                
                sonar_view.set_back_callback(sonar_back_callback)
                
                # Mount the sonar view using the app's _mount_view method
                if hasattr(app, '_mount_view'):
                    app._mount_view(sonar_view)
                    sonar_view.start()
                    print("Successfully opened sonar mode!")
                else:
                    print("App doesn't have _mount_view method")
                    if self.lbl_status:
                        self.lbl_status.config(text="Error: Cannot switch to sonar mode")
                        
            except Exception as e:
                print(f"Error opening sonar mode: {e}")
                if self.lbl_status:
                    self.lbl_status.config(text=f"Error opening sonar mode: {e}")
        else:
            print("Could not find main app reference to open sonar mode")
            # Fallback: show a message to user
            if self.lbl_status:
                self.lbl_status.config(text="Script requesting sonar mode - please manually open Mode 1")

    def _open_angle_mode(self) -> None:
        """Open the angle/telemetry mode (Mode 2) when '2' is received during script execution."""
        print("_open_angle_mode called!")
        
        # Get reference to the main app window
        app = self.master
        while app and not hasattr(app, 'navigate_to_menu'):
            app = app.master
        
        if app and hasattr(app, 'navigate_to_menu'):
            print("Found main app, creating and mounting Mode 2 (Angle)...")
            try:
                # Create a new angle mode view in script mode with special handling for flash integration
                angle_view = Mode2View(app, self.controller, script_mode=True)
                
                # Create a special callback that will handle both user stop and firmware '8'
                def angle_back_callback():
                    print("Angle mode back callback called")
                    self._return_from_sub_mode(app)
                
                angle_view.set_back_callback(angle_back_callback)
                
                # Mount the angle view using the app's _mount_view method
                if hasattr(app, '_mount_view'):
                    app._mount_view(angle_view)
                    angle_view.start()
                    print("Successfully opened angle mode!")
                else:
                    print("App doesn't have _mount_view method")
                    if self.lbl_status:
                        self.lbl_status.config(text="Error: Cannot switch to angle mode")
                        
            except Exception as e:
                print(f"Error opening angle mode: {e}")
                if self.lbl_status:
                    self.lbl_status.config(text=f"Error opening angle mode: {e}")
        else:
            print("Could not find main app reference to open angle mode")
            # Fallback: show a message to user
            if self.lbl_status:
                self.lbl_status.config(text="Script requesting angle mode - please manually open Mode 2")

    def _return_from_sub_mode(self, app) -> None:
        """Helper method to return to flash mode from a sub-mode (when user presses stop or firmware sends '8')."""
        print("_return_from_sub_mode called")
        try:
            # Create a new flash view to ensure clean state
            flash_view = self.__class__(app, self.controller)
            flash_view.set_back_callback(app.navigate_to_menu)
            app._mount_view(flash_view)
            flash_view.start()
            print("Successfully returned to flash mode with new instance")
                
        except Exception as e:
            print(f"Error returning from sub-mode: {e}")
            app.navigate_to_menu()

    def _close_current_mode(self) -> None:
        """Close current mode (sonar/angle) and return to flash mode when '8' is received."""
        print("_close_current_mode called!")
        
        # Get reference to the main app window
        app = self.master
        while app and not hasattr(app, 'navigate_to_menu'):
            app = app.master
        
        if app and hasattr(app, '_mount_view'):
            print("Found main app, returning to flash mode...")
            self._return_from_sub_mode(app)
        else:
            print("Could not find main app reference, returning to menu")
            if app and hasattr(app, 'navigate_to_menu'):
                app.navigate_to_menu()

    def _return_to_flash_mode(self, app) -> None:
        """Helper method to return to flash mode from a sub-mode."""
        try:
            # Check if we stored a previous flash view
            if hasattr(app, '_previous_flash_view') and app._previous_flash_view:
                print("Restoring previous flash view...")
                # Restore the previous flash view
                flash_view = app._previous_flash_view
                app._mount_view(flash_view)
                flash_view.start()
                # Clear the stored reference
                app._previous_flash_view = None
            else:
                print("Creating new flash view...")
                # Create a new flash view if no previous one stored
                flash_view = self.__class__(app, self.controller)
                flash_view.set_back_callback(app.navigate_to_menu)
                app._mount_view(flash_view)
                flash_view.start()
            
            print("Successfully returned to flash mode!")
            
        except Exception as e:
            print(f"Error returning to flash mode: {e}")
            # Fallback to menu
            app.navigate_to_menu()