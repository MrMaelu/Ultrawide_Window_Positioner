"""Entry point for the Ultrawide Window Positioner."""
import atexit
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Local imports
import uwp_logging
from gui import PysideGuiManager

logger = logging.getLogger(__name__)

DEBUG = True

def load_pyside_gui(path: Path)->None:
    """Load the PySide GUI."""
    app = QApplication(sys.argv)
    win = PysideGuiManager(base_path=path)

    win.update_config_list()

    atexit.register(win.win_man.reset_all_windows)
    win.show()

    exit_code = app.exec()
    sys.exit(exit_code)

if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        base_path = Path(sys.executable).resolve().parent
    else:
        base_path = Path(__file__).resolve().parent

    if DEBUG:
        uwp_logging.setup_logging()

    load_pyside_gui(base_path)
