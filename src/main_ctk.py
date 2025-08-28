import os
import sys
from ctypes import windll

# Local imports
from config_manager import ConfigManager
from asset_manager import AssetManager
from layout_ctk import CtkGuiManager

def load_ctk_gui():
    # Load the GUI manager
    app = CtkGuiManager(
        compact=compact,
        is_admin=is_admin,
        use_images=use_images,
        snap=snap_side,
        details=details,
        config_manager=config_manager,
        asset_manager=asset_manager
        )

    set_default_config(app)
    
    # Start main GUI
    app.mainloop()

def set_default_config(app):
    callback_manager = app.callback_manager
    if compact:
        callback_manager.toggle_compact_mode(startup=True)

    default_config = config_manager.detect_default_config()
    callback_manager.update_config_list(default_config)


if __name__ == "__main__":
    # Resolve base path for script vs frozen executable
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    # Set up managers
    config_manager = ConfigManager(base_path)
    asset_manager = AssetManager(base_path)

    # Check for admin rights
    try:
        is_admin = windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False
    
    # Load config
    compact, use_images, snap_side , details = config_manager.load_settings()

    load_ctk_gui()
