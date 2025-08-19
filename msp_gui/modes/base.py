from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Callable, Optional

from msp_gui.msp_controller import MSPController

logger = logging.getLogger(__name__)

UI_FPS_MS = 200  # ~5 FPS
DEFAULT_EXIT_CMD = "8"


class ModeBase(tk.Frame):
    """
    Base class for GUI 'modes' that:
      - Own a listener thread that reads serial lines
      - Periodically renders UI via Tk 'after'
      - Provide a top bar with title + "Back/Stop" button
    Subclasses must implement: on_start(), on_stop(), handle_line(line), render()
    """

    def __init__(self, master: tk.Misc, controller: MSPController, *,
                 title: str,
                 enter_command: Optional[str] = None,
                 exit_command: str = DEFAULT_EXIT_CMD):
        import tkinter.ttk as ttk
        super().__init__(master, bg="#f4f6fa")
        self.controller = controller
        self.enter_command = enter_command
        self.exit_command = exit_command

        self._stop_event = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None
        self._back_cb: Optional[Callable[[], None]] = None

        # UI: top bar + status bar + body container (ttk for modern look)
        top = ttk.Frame(self, style="TFrame")
        top.pack(fill="x", pady=(10, 5))

        # Title and back button row
        title_frame = ttk.Frame(top, style="TFrame")
        title_frame.pack(fill="x")
        
        ttk.Label(title_frame, text=title, style="Title.TLabel").pack(side="left", padx=10)
        ttk.Button(title_frame, text="🔙 Stop and Return to Menu", command=self._on_back_pressed, style="TButton").pack(side="right", padx=10)

        # Status row
        self.status_frame = ttk.Frame(self, style="TFrame")
        self.status_frame.pack(fill="x", pady=(5, 10))
        
        # Status indicators
        self.status_var = tk.StringVar(value="Initializing...")
        self.connection_var = tk.StringVar(value="🟢 Connected")
        
        ttk.Label(self.status_frame, text="Status:", style="Sub.TLabel").pack(side="left", padx=(10, 5))
        ttk.Label(self.status_frame, textvariable=self.status_var, style="TLabel").pack(side="left")
        ttk.Label(self.status_frame, textvariable=self.connection_var, style="Status.TLabel").pack(side="right", padx=10)

        self.body = ttk.Frame(self, style="TFrame")
        self.body.pack(fill="both", expand=True)

    # ----- Lifecycle -----

    def set_back_callback(self, cb: Callable[[], None]) -> None:
        self._back_cb = cb

    def start(self) -> None:
        """
        Start the mode: send enter command (if any), start listener thread,
        schedule periodic render, and let subclass build its UI.
        """
        logger.info("Starting mode: %s", self.__class__.__name__)
        self._stop_event.clear()

        if self.enter_command is not None:
            # Flush any stray lines from the previous mode before switching
            try:
                self.controller.flush_input()
                # Small delay to ensure buffer is cleared
                import time
                time.sleep(0.1)
            except Exception as e:
                logger.warning("Error flushing input buffer: %s", e)
            self.controller.send_command(self.enter_command)

        self.on_start()

        self._listener_thread = threading.Thread(
            target=self._listen_loop, name=f"{self.__class__.__name__}Listener", daemon=True
        )
        self._listener_thread.start()

        self.after(UI_FPS_MS, self._tick)

    def stop(self) -> None:
        """
        Stop the mode: send exit command, signal thread to stop, join, cleanup.
        """
        logger.info("Stopping mode: %s", self.__class__.__name__)
        
        # Send exit command first
        if self.exit_command:
            try:
                self.controller.send_command(self.exit_command)
                # Small delay to ensure command is sent
                import time
                time.sleep(0.1)
            except Exception as e:
                logger.warning("Error sending exit command: %s", e)

        # Signal stop and wait for thread
        self._stop_event.set()
        if self._listener_thread:
            self._listener_thread.join(timeout=2.0)
            if self._listener_thread.is_alive():
                logger.warning("Listener thread did not stop cleanly")
            self._listener_thread = None

        # Call subclass cleanup
        try:
            self.on_stop()
        except Exception as e:
            logger.warning("Error in on_stop: %s", e)
            
        # Final buffer flush to clear any remaining data
        try:
            self.controller.flush_input()
        except Exception as e:
            logger.warning("Error flushing on stop: %s", e)

    def _on_back_pressed(self) -> None:
        """
        Default "Back" behavior: stop self and call back to app shell.
        """
        self.stop()
        if self._back_cb:
            self._back_cb()

    # ----- Thread & render loop -----

    def _listen_loop(self) -> None:
        logger.debug(f"Starting listener thread for {self.__class__.__name__}")
        line_count = 0
        while not self._stop_event.is_set():
            line = self.controller.read_line()
            if not line:
                continue
            line_count += 1
            logger.debug(f"{self.__class__.__name__} received line #{line_count}: '{line}'")
            try:
                self.handle_line(line)
            except Exception as e:
                logger.warning("handle_line error in %s: %s", self.__class__.__name__, e)
        logger.debug(f"Listener thread for {self.__class__.__name__} stopping after {line_count} lines")

    def _tick(self) -> None:
        if not self.winfo_ismapped():
            return
        try:
            self.render()
        except Exception as e:
            logger.warning("render error: %s", e)
        self.after(UI_FPS_MS, self._tick)

    # ----- Hooks for subclasses -----

    def update_status(self, message: str) -> None:
        """Update the status message displayed in the status bar."""
        if hasattr(self, 'status_var'):
            self.status_var.set(message)

    def update_connection_status(self, connected: bool) -> None:
        """Update the connection status indicator."""
        if hasattr(self, 'connection_var'):
            status = "🟢 Connected" if connected else "🔴 Disconnected"
            self.connection_var.set(status)

    def on_start(self) -> None:
        """Build per-mode UI + initialize state (called on start)."""
        raise NotImplementedError

    def on_stop(self) -> None:
        """Tear down per-mode resources (called after stop)."""
        pass

    def handle_line(self, line: str) -> None:
        """Parse a single serial line and update internal state."""
        raise NotImplementedError

    def render(self) -> None:
        """Update the UI/plot from internal state."""
        raise NotImplementedError
