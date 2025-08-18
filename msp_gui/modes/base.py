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

        # UI: top bar + body container (ttk for modern look)
        top = ttk.Frame(self, style="TFrame")
        top.pack(fill="x", pady=(10, 8))

        ttk.Label(top, text=title, style="Title.TLabel").pack(side="left", padx=10)
        ttk.Button(top, text="עצור וחזור לתפריט", command=self._on_back_pressed, style="TButton").pack(side="right", padx=10)

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
            except Exception:
                pass
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
        if self.exit_command:
            self.controller.send_command(self.exit_command)

        self._stop_event.set()
        if self._listener_thread:
            self._listener_thread.join(timeout=2.0)
            self._listener_thread = None

        self.on_stop()

    def _on_back_pressed(self) -> None:
        """
        Default "Back" behavior: stop self and call back to app shell.
        """
        self.stop()
        if self._back_cb:
            self._back_cb()

    # ----- Thread & render loop -----

    def _listen_loop(self) -> None:
        while not self._stop_event.is_set():
            line = self.controller.read_line()
            if not line:
                continue
            try:
                self.handle_line(line)
            except Exception as e:
                logger.warning("handle_line error: %s", e)

    def _tick(self) -> None:
        if not self.winfo_ismapped():
            return
        try:
            self.render()
        except Exception as e:
            logger.warning("render error: %s", e)
        self.after(UI_FPS_MS, self._tick)

    # ----- Hooks for subclasses -----

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
