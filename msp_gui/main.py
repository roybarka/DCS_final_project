from __future__ import annotations

import logging
import os

from msp_gui.app import AppGUI
from msp_gui.msp_controller import MSPController

# Configure logging once at entry
logging.basicConfig(level=os.environ.get("MSP_GUI_LOGLEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s: %(message)s")

DEFAULT_PORT = "COM4"
DEFAULT_BAUD = 9600


def main() -> None:
    controller = MSPController(DEFAULT_PORT, DEFAULT_BAUD)
    app = AppGUI(controller)
    app.mainloop()


if __name__ == "__main__":
    main()
