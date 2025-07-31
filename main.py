import os
import sys
import importlib
import threading
import tkinter as tk
from ctypes import windll
import tkinter.messagebox as messagebox

# Local imports
from lib.layout_ctk import CtkGuiManager
from lib.constants import UIConstants, Colors
from lib.asset_manager import AssetManager
from lib.window_manager import WindowManager
from lib.config_manager import ConfigManager
from lib.utils import WindowInfo, clean_window_title

class ApplicationState:
    def __init__(self):
        # Initialize managers
        self.window_manager = None
        self.config_manager = None
        self.asset_manager = None

        # Assets
        self.assets_dir = None
        
        # Client ID / secret
        self.CLIENT_ID = None
        self.CLIENT_SECRET = None
        self.client_info_missing = True
        
        # UI state
        self.is_admin = False
        self.compact = False
        self.snap_side = 0
        self.use_images = False
        
        # Screen info
        self.screen_width = 1920
        self.screen_height = 1080
        
        # Config state
        self.config_files = []
        self.config_names = []
        self.config = None
        self.config_dir = None
        self.applied_config = None

######################
# Callback functions #
######################

    def apply_settings(self, reapply=False):
        if not reapply:
            for child in self.app.buttons_1_container.winfo_children():
                if child.cget("text") == "Apply config":
                    selected_config = self.config_files[self.config_names.index(self.app.combo_box.get())]
                    selected_config_shortname = selected_config.replace('config_', '').replace('.ini', '')
                    config = self.config_manager.load_config(selected_config)

                    self.applied_config = config

                    child.configure(text="Reset config", fg_color=Colors.BUTTON_ACTIVE, hover_color=Colors.BUTTON_ACTIVE_HOVER)
                    self.app.info_label.configure(text=f"Active config: {selected_config_shortname}")
                    self.app.aot_button.configure(state=tk.NORMAL)

                elif child.cget("text") == "Reset config" and not reapply:
                    self.applied_config = None
                    self.window_manager.reset_all_windows()
                    child.configure(text="Apply config", fg_color=Colors.BUTTON_NORMAL, hover_color=Colors.BUTTON_HOVER)
                    self.app.info_label.configure(text=f"")
                    self.app.aot_button.configure(state=tk.DISABLED)
                    self.app.reapply.set(0)

        if self.applied_config:
            matching_windows, _ = self.window_manager.find_matching_windows(self.applied_config)
            self.window_manager.reset_all_windows()
            
            # Apply configuration
            for match in matching_windows:
                try:
                    hwnd = match['hwnd']
                    section = match['config_name']
                    settings = {
                        'position': self.applied_config.get(section, 'position', fallback=None),
                        'size': self.applied_config.get(section, 'size', fallback=None),
                        'always_on_top': self.applied_config.getboolean(section, 'always_on_top', fallback=False),
                        'has_titlebar': self.applied_config.getboolean(section, 'titlebar', fallback=True)
                    }
                    
                    self.window_manager.apply_window_config(settings, hwnd, section)
                    
                except Exception as e:
                    print(f"Error applying settings to window {match['config_name']}: {e}")
                    continue
                
        self.update_always_on_top_status()

    def create_config(self):
        self.app.create_config_ui(self.app,
            self.window_manager.get_all_window_titles(),
            self.config_manager.save_window_config,
            self.config_manager.collect_window_settings,
            self.update_config_list
        )

    def open_config_folder(self):
        # Open the config folder in File Explorer
        try:
            if sys.platform == "win32":
                os.startfile(self.config_dir)
        except Exception as e:
            print(f"Can't open config folder: {e}")

    def restart_as_admin(self):
        # Restart the application with admin privileges
        if sys.platform == "win32":
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            print(f"Restarting with admin privileges: {params}")
            rc = windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            if rc > 32:
                os._exit(0)

    def toggle_always_on_top(self):
        for hwnd in self.window_manager.topmost_windows:
            self.window_manager.toggle_always_on_top(hwnd)
        self.update_always_on_top_status()
        self.app.reapply.set(0)
    
    def on_config_select(self, event):
        selected_value = event.get()
        if selected_value in self.config_names:
            idx = self.config_names.index(selected_value)
            selected_config = self.config_files[idx]
            loaded_config = self.config_manager.load_config(selected_config)
            self.config = self.config_manager.validate_and_repair_config(loaded_config)
            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            if not self.app.compact_mode:
                self.compute_window_layout(self.config, missing_windows)
            else:
                self.update_managed_windows_list(self.config)

    def toggle_compact_mode(self=None, startup=False):
        self.app.toggle_compact(startup)
        self.compact = self.app.compact_mode
        self.save_settings()
        if self.app.compact_mode:
            self.update_managed_windows_list(self.config)
        else:
            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            self.compute_window_layout(self.config, missing_windows)

    def delete_config(self):
        current_name = self.app.combo_box.get().strip()
        if not current_name:
            messagebox.showerror("Error", "No config selected to delete.")
            return

        confirm = messagebox.askyesno("Confirm Delete", f"Delete config '{current_name}'?")
        if confirm:
            deleted = self.config_manager.delete_config(current_name)
            if deleted:
                self.update_config_list()
            else:
                messagebox.showerror("Error", f"Failed to delete '{current_name}'.")

    def open_image_folder(self):
        # Open the image folder in File Explorer
        try:
            if sys.platform == "win32":
                os.startfile(self.assets_dir)
        except Exception as e:
            print(f"Can't open image folder: {e}")

    def download_screenshots_threaded(self):
        threading.Thread(target=self.download_screenshots, daemon=True).start()
                        
    def toggle_images(self):
        self.app.use_images = not self.app.use_images
        for child in self.app.buttons_2_container.winfo_children():
            if child.cget("text") == "Toggle images" and self.app.use_images:
                child.configure(text="Toggle images", fg_color=Colors.BUTTON_ACTIVE, hover_color=Colors.BUTTON_ACTIVE_HOVER)
            elif child.cget("text") == "Toggle images" and not self.app.use_images:
                child.configure(text="Toggle images", fg_color=Colors.BUTTON_NORMAL, hover_color=Colors.BUTTON_HOVER)

        self.save_settings()
        _, missing_windows = self.window_manager.find_matching_windows(self.config)
        self.compute_window_layout(self.config, missing_windows)

    def start_auto_reapply(self):
        if self.app.reapply.get():
            self.auto_reapply()
        self.app.after(500, self.start_auto_reapply)

######################

    # Check if the current window layout matches the applied config
    def compare_window_data(self, settings, metrics):
        differences = []
        
        settings_pos = tuple(map(int, settings['position'].split(','))) if settings['position'] else (0, 0)
        if settings_pos != metrics['position']:
            differences.append(f"Position mismatch: Settings={settings_pos}, Metrics={metrics['position']}")
        
        settings_size = tuple(map(int, settings['size'].split(','))) if settings['size'] else (0, 0)
        if settings_size != metrics['size']:
            differences.append(f"Size mismatch: Settings={settings_size}, Metrics={metrics['size']}")
        
        settings_aot = settings['always_on_top'] == True
        metrics_aot = (metrics['exstyle'] & 0x00000008) != 0
        if settings_aot != metrics_aot:
            differences.append(f"Always on top mismatch: Settings={settings_aot}, Metrics={metrics_aot}")
        
        settings_titlebar = settings['has_titlebar'] == True
        metrics_titlebar = (metrics['style'] & 0x00C00000) != 0
        if settings_titlebar != metrics_titlebar:
            differences.append(f"Titlebar mismatch: Settings={settings_titlebar}, Metrics={metrics_titlebar}")
        
        if not differences:
            return True
        
        return False

    # Automatically reapply the settings from config when a change is detected
    def auto_reapply(self):
        if self.app.reapply.get():
            matching_windows, _ = self.window_manager.find_matching_windows(self.applied_config)
            compare_results = []
            for match in matching_windows:
                hwnd = match['hwnd']
                section = match['config_name']
                
                # Get window settings from config
                settings = {
                    'position': self.applied_config.get(section, 'position', fallback=None),
                    'size': self.applied_config.get(section, 'size', fallback=None),
                    'always_on_top': self.applied_config.getboolean(section, 'always_on_top', fallback=False),
                    'has_titlebar': self.applied_config.getboolean(section, 'titlebar', fallback=True)
                }

                metrics = self.window_manager.get_window_metrics(hwnd)
                compare_results.append(self.compare_window_data(settings, metrics))
            if not all(compare_results):
                self.apply_settings(reapply=True)

    # Check if IGDB secrets are added
    def check_igdb_client_info(self):
        for module_name in ("lib.client_secrets", "client_secrets"):
            try:
                secrets = importlib.import_module(module_name)
                self.CLIENT_ID = secrets.CLIENT_ID
                self.CLIENT_SECRET = secrets.CLIENT_SECRET
                if self.CLIENT_ID.strip() != '' and self.CLIENT_SECRET.strip() != '':
                    self.client_info_missing = False
                break
            except ModuleNotFoundError:
                continue

    # Download screenshots from IGDB
    def download_screenshots(self):
            self.app.image_download_button.configure(state='disabled')
            search_titles = set()

            # Getting the titles from all config files
            config_files, _ = self.config_manager.list_config_files()
            for config_file in config_files:
                config = self.config_manager.load_config(config_file)
                if not config:
                    continue

                for section in config.sections():
                    title = config[section].get("search_title", fallback=section)
                    cleaned_title = clean_window_title(title, sanitize=True)
                    search_titles.add(cleaned_title)
            
            # Downloading screenshots for all titles
            for title in search_titles:
                filename = title.replace(' ', '_').replace(':', '')
                image_path = os.path.join(self.assets_dir, f"{filename}.jpg")

                if not os.path.exists(image_path):
                    self.asset_manager.search(title, save_dir=self.assets_dir)
                    if self.app.info_label.winfo_exists():
                        self.app.info_label.configure(text=f"Downloading image for {title}")

            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            if not self.compact:
                self.compute_window_layout(self.config, missing_windows)
                if self.app.info_label.winfo_exists():
                    self.app.info_label.configure(text=f"Image download complete")

            self.app.image_download_button.configure(state='enabled')

    # Take a screenshot of any detected window for the currently loaded config
    def take_screenshot(self):
        existing_windows, _ = self.window_manager.find_matching_windows(self.config)
        if existing_windows:
            for window in existing_windows:
                hwnd = window['hwnd']
                filename = window['config_name'].replace(' ', '_').replace(':', '')
                image_path = os.path.join(self.assets_dir, f"{filename}.jpg")
                self.asset_manager.capture_window(hwnd=hwnd, save_path=image_path)
        
            self.asset_manager.bring_to_front(hwnd=self.app.winfo_id())

    def update_always_on_top_status(self):
        try:
            status = self.window_manager.get_always_on_top_status()
            self.app.aot_label['text'] = status
        except Exception as e:
            print(f"Error updating always-on-top status: {e}")

    def update_managed_windows_list(self, config):
        if not hasattr(self.app, 'managed_text'):
            self.app.setup_managed_text()

        lines = []
        aot_lines = []
        if config:
            for section in config.sections():
                is_aot = config.getboolean(section, "always_on_top", fallback=False)
                title = f"* {section} *" if is_aot else section
                if len(title) > UIConstants.WINDOW_TITLE_MAX_LENGTH:
                    title = title[:UIConstants.WINDOW_TITLE_MAX_LENGTH] + "..."
                lines.append(title)
                aot_lines.append(is_aot)

        self.app.update_managed_text(lines, aot_lines)

    def compute_window_layout(self, config, missing_windows):
        positioned_windows = []

        if config:
            for section in config.sections():
                pos = config[section].get("position")
                size = config[section].get("size")
                
                if pos and size:
                    pos_x, pos_y = map(int, pos.split(','))
                    size_w, size_h = map(int, size.split(','))
                    always_on_top = config[section].get("always_on_top", "false").lower() == "true"
                    window_exists = section not in missing_windows
                    search_title = config[section].get("search_title") or section
                    positioned_windows.append(WindowInfo(section,
                                                         pos_x, pos_y,
                                                         size_w, size_h,
                                                         always_on_top,
                                                         window_exists,
                                                         search_title
                                                         ))

            self.app.set_layout_frame(positioned_windows)

    def update_config_list(self, config=None):
        self.config_files, self.config_names = self.config_manager.list_config_files()
        if self.config_files and self.config_names:
            self.app.combo_box.configure(values=self.config_names)
            self.app.combo_box.set(config or self.config_names[0])
            self.on_config_select(self.app.combo_box)
        else:
            self.app.combo_box.configure(values=[])
            self.app.combo_box.set('')
            if self.app.layout_frame:
                self.app.layout_frame.destroy()

    def save_settings(self):
        self.config_manager.save_settings(self.compact, self.app.use_images, self.app.snap.get())

    def load_managers(self):
        # Checking if the IGDB client info is added
        state.check_igdb_client_info()
        state.window_manager = WindowManager()
        state.asset_manager = AssetManager(client_id=self.CLIENT_ID, client_secret=self.CLIENT_SECRET, client_info_missing=self.client_info_missing)


def load_GUI():
    callbacks = {
        "apply_config": state.apply_settings,
        "create_config": state.create_config,
        "open_config_folder": state.open_config_folder,
        "restart_as_admin": state.restart_as_admin,
        "toggle_AOT": state.toggle_always_on_top,
        "config_selected": state.on_config_select,
        "toggle_compact": state.toggle_compact_mode,
        "delete_config": state.delete_config,
        "image_folder": state.open_image_folder,
        "download_images": state.download_screenshots_threaded,
        "toggle_images": state.toggle_images,
        "screenshot": state.take_screenshot,
        "snap": state.save_settings,
        "auto_reapply": state.start_auto_reapply,
    }

    app = CtkGuiManager(callbacks=callbacks, compact=state.compact, is_admin=state.is_admin, use_images=state.use_images, snap=state.snap_side, client_info_missing=state.client_info_missing)
    state.app = app
    state.app.assets_dir = state.assets_dir

    # Set default config
    if state.compact: state.toggle_compact_mode(startup=True)
    default_config = state.config_manager.detect_default_config()
    state.update_config_list(default_config)

    # Start main GUI
    state.app.mainloop()

if __name__ == "__main__":
    # Get application base path
    # Needed to make the application work the same when running as script as well as .exe
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    # Set up managers
    state = ApplicationState()
    state.config_manager = ConfigManager(base_path)
    threading.Thread(target=state.load_managers, daemon=True).start()
    
    # Set config and asset folders
    state.config_dir = os.path.join(base_path, "configs")
    if not os.path.exists(state.config_dir): os.makedirs(state.config_dir)

    state.assets_dir = os.path.join(base_path, "assets")
    if not os.path.exists(state.assets_dir): os.makedirs(state.assets_dir)

    # Check for admin rights
    try:
        state.is_admin = windll.shell32.IsUserAnAdmin()
    except:
        state.is_admin = False
    
    # Load config
    state.compact, state.use_images, state.snap_side = state.config_manager.load_settings()

    load_GUI()
