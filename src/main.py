"""Main entry point for Ultrawide Window Positioner with PySide GUI."""
import sys
from ctypes import windll
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Local imports
import log_handler
from asset_manager import AssetManager
from config_manager import ConfigManager
from layout_pyside import PysideGuiManager


def load_pyside_gui()->None:
    """Load the QT GUI manager."""
    app = QApplication(sys.argv)

    # Main window
    win = PysideGuiManager(
        initial_states=initial_states,
        is_admin=is_admin,
        config_manager=config_manager,
        asset_manager=asset_manager,
    )

    # Set default config
    win.callback_manager.detect_config()

    # Run
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        # Running from a bundled exe (PyInstaller)
        base_path = Path(sys.executable).resolve().parent
    else:
        base_path = Path(__file__).resolve().parent

    log_handler.setup_logging()

    # Set up managers
    config_manager = ConfigManager(base_path)
    asset_manager = AssetManager(base_path)

    # Check for admin rights
    is_admin = windll.shell32.IsUserAnAdmin() != 0

    # Load config
    compact, use_images, snap_side , details, hotkey = config_manager.load_settings()
    initial_states = {
        "compact": compact,
        "use_images": use_images,
        "snap_side": snap_side,
        "details": details,
        "hotkey": hotkey,
        }

    load_pyside_gui()
