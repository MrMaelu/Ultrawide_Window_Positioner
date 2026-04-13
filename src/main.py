"""Entry point for the Ultrawide Window Positioner."""
import atexit
import logging
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Local imports
from backend import log_setup
from gui import PysideGuiManager

logger = logging.getLogger(__name__)

DEBUG = True

if sys.platform != "win32":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

def load_pyside_gui(path: Path)->None:
    """Load the PySide GUI."""
    app = QApplication(sys.argv)
    win = PysideGuiManager(base_path=path)

    win.update_config_list()

    # Reset window settings on exit
    atexit.register(win.win_man.reset_all_windows)

    win.show()

    exit_code = app.exec()
    sys.exit(exit_code)

if __name__ == "__main__":
    # Set base path appropriately for pyinstaller or script
    if getattr(sys, "frozen", False):
        base_path = Path(sys.executable).resolve().parent
    else:
        base_path = Path(__file__).resolve().parent


    if DEBUG:
        log_setup.setup_logging("debug")
    else:
        log_setup.setup_logging("info")

    load_pyside_gui(base_path)

