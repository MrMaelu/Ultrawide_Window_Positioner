"""Main entry point for Ultrawide Window Positioner with PySide GUI."""
import sys
from ctypes import windll
from pathlib import Path

from PySide6.QtWidgets import QApplication

from asset_manager import AssetManager

# Local imports
from config_manager import ConfigManager
from layout_pyside import PysideGuiManager


def load_pyside_gui()->None:
    """Load the QT GUI manager."""
    app = QApplication(sys.argv)

    # Main window
    win = PysideGuiManager(
        compact=compact,
        is_admin=is_admin,
        use_images=use_images,
        snap=snap_side,
        details=details,
        config_manager=config_manager,
        asset_manager=asset_manager,
    )

    set_default_config(win)

    # Run
    win.show()
    sys.exit(app.exec())


def set_default_config(app:object)->None:
    """Set the default config at startup."""
    callback_manager = app.callback_manager
    callback_manager.detect_config()


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        # Running from a bundled exe (PyInstaller, cx_Freeze, etc.)
        base_path = Path(sys.executable).resolve().parent
    else:
        try:
            base_path = Path(__file__).resolve().parent
        except NameError:
            # __file__ not defined (interactive session)
            base_path = Path.cwd()


    # Set up managers
    config_manager = ConfigManager(base_path)
    asset_manager = AssetManager(base_path)

    # Check for admin rights
    try:
        is_admin = windll.shell32.IsUserAnAdmin()
    except:  # noqa: E722
        is_admin = False

    # Load config
    compact, use_images, snap_side , details = config_manager.load_settings()

    load_pyside_gui()
