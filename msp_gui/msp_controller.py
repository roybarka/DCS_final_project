from __future__ import annotations

import logging
import time
from typing import Optional

import serial

DEFAULT_BAUDRATE = 9600
SERIAL_TIMEOUT_S = 1.0  # seconds

logger = logging.getLogger(__name__)


class MSPController:
    """
    Minimal wrapper around a serial port: open, read line, write command, close.
    """

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE):
        self.ser = serial.Serial(port, baudrate, timeout=SERIAL_TIMEOUT_S)
        # Many boards reset when the port opens; give them a moment.
        time.sleep(2.0)
        logger.info("Connected to %s @ %d baud.", port, baudrate)

    def read_line(self) -> Optional[str]:
        """
        Read one '\n'-terminated line; returns None on timeout/empty or error.
        """
        try:
            raw = self.ser.readline()
            if not raw:
                return None
            return raw.decode(errors="ignore").strip()
        except Exception as e:
            logger.warning("Serial read error: %s", e)
            return None

    def send_command(self, command: str | bytes) -> None:
        """
        Send a command (str or bytes) to the device.
        """
        try:
            if not isinstance(command, (bytes, bytearray)):
                command = str(command).encode()
            self.ser.write(command)
            logger.debug("Sent command: %r", command)
        except Exception as e:
            logger.warning("Serial write error: %s", e)

    def close(self) -> None:
        try:
            self.ser.close()
            logger.info("Serial closed.")
        except Exception as e:
            logger.warning("Serial close error: %s", e)
