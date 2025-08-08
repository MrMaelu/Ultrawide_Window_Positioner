import os
import sys
import threading
from ctypes import windll, WinError, get_last_error

# Local imports
from constants import UIConstants
from utils import WindowInfo, clean_window_title
from window_manager import WindowManager

def messagebox(title, message, style):
    result = windll.user32.MessageBoxW(None, message, title, style)
    if not result:
        raise WinError(get_last_error())
    return result

class CallbackManager:
    def __init__(self, app, config_manager, asset_manager):
        self.app = app
        self.config_manager = config_manager
        self.window_manager = WindowManager()
        self.asset_manager = asset_manager

        self.base_path = config_manager.base_path
        self.assets_dir = self.asset_manager.assets_dir
        self.config_dir = self.config_manager.config_dir

        self.applied_config = None
        self.compact = False
        
        self.callbacks = {
            "apply_config": self.apply_settings_threaded,
            "create_config": self.create_config,
            "open_config_folder": self.open_config_folder,
            "restart_as_admin": self.restart_as_admin,
            "toggle_AOT": self.toggle_always_on_top,
            "config_selected": self.on_config_select,
            "toggle_compact": self.toggle_compact_mode,
            "delete_config": self.delete_config,
            "image_folder": self.open_image_folder,
            "download_images": self.download_screenshots_threaded,
            "toggle_images": self.toggle_images,
            "screenshot": self.take_screenshot,
            "snap": self.save_settings,
            "auto_reapply": self.start_auto_reapply,
            "details": self.window_details
        }

    # Callback functions
    def apply_settings_threaded(self):
        threading.Thread(target=self.apply_settings, daemon=True).start()

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
        try:
            self.app.toggle_compact(startup)
            self.compact = self.app.compact_mode
            self.save_settings()
            if self.app.compact_mode:
                self.update_managed_windows_list(self.config)
            else:
                _, missing_windows = self.window_manager.find_matching_windows(self.config)
                self.compute_window_layout(self.config, missing_windows)
        except Exception as e:
            print(f"Toggle compact failed: {e}")

    def delete_config(self):
        current_name = self.app.combo_box.get().strip()
        if not current_name:
            messagebox(title="Error", message="No config selected to delete.", style=0)
            return

        confirm = messagebox(title="Confirm Delete", message=f"Delete config '{current_name}'?", style=4)
        if confirm == 6:
            deleted = self.config_manager.delete_config(current_name)
            if deleted:
                self.update_config_list()
            else:
                messagebox( title="Error", message=f"Failed to delete '{current_name}'.", style=0)

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
        self.save_settings()
        _, missing_windows = self.window_manager.find_matching_windows(self.config)
        self.compute_window_layout(self.config, missing_windows)

    def start_auto_reapply(self):
        if self.app.reapply.get():
            self.auto_reapply()
        self.app.after(500, self.start_auto_reapply)

    def window_details(self):
        self.save_settings()
        self.on_config_select(self.app.combo_box)


    # Helper functions
    def apply_settings(self, reapply=False):
        selected_config_shortname = None
        if not reapply:
            self.app.config_active = not self.app.config_active
            if self.app.config_active:
                selected_config = self.config_files[self.config_names.index(self.app.combo_box.get())]
                selected_config_shortname = selected_config.replace('config_', '').replace('.ini', '')
                config = self.config_manager.load_config(selected_config)
                self.applied_config = config
                self.app.format_apply_reset_button(selected_config_shortname)
                self.app.format_apply_reset_button(disable=1)

            elif not self.app.config_active:
                self.applied_config = None
                self.window_manager.reset_all_windows()
                self.app.format_apply_reset_button()

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
        self.app.applied_config = selected_config_shortname
        self.app.format_apply_reset_button(disable=0)

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

    # Download screenshots from IGDB
    def download_screenshots(self):
            number_of_images = 0
            failed_downloads = 0
            ignored = 0
            self.app.image_download_button.configure(state='disabled')
            search_titles = {}

            # Getting the titles from all config files
            config_files, _ = self.config_manager.list_config_files()
            for config_file in config_files:
                config = self.config_manager.load_config(config_file)
                if not config:
                    continue

                for section in config.sections():
                    title = config[section].get("search_title", fallback=section)
                    cleaned_title = clean_window_title(title, sanitize=True)
                    if cleaned_title not in search_titles:
                        search_titles[cleaned_title] = []
                    search_titles[cleaned_title].append((config_file, section))
            
            # Downloading screenshots for all titles
            for title, pairs in search_titles.items():
                filename = title.replace(' ', '_').replace(':', '')
                image_path = os.path.join(self.assets_dir, f"{filename}.jpg")

                source_url = ''
                source = ''
                if not os.path.exists(image_path):
                    if self.app.info_label.winfo_exists():
                        self.app.info_label.configure(text=f"Downloading image for {title}")
                    
                    # Trying to download the screenshot
                    result, source, source_url = self.asset_manager.search(title, save_dir=self.assets_dir)
                    if result == 'ignored':
                        ignored += 1
                        source_url = ''
                        source = ''
                    elif result:
                        number_of_images += 1
                    else:
                        failed_downloads += 1
                        source_url = ''
                        source = ''

                else:
                    for config_file, section in pairs:
                        config = self.config_manager.load_config(config_file)
                        if config and section in config.sections():
                            source = config[section].get('source', '')
                            source_url = config[section].get('source_url', source_url)
                            if source_url:
                                break

                # Update the config files with the source_url
                for config_file, section in pairs:
                    config = self.config_manager.load_config(config_file)
                    if config and section in config.sections():
                        config.set(section, 'source', source)
                        config.set(section, 'source_url', source_url)
                        self.config_manager.save_config(config, config_file)

            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            if not self.compact:
                self.compute_window_layout(self.config, missing_windows)
                if self.app.info_label.winfo_exists():
                    self.app.info_label.configure(text=f"Image download complete. {number_of_images} images downloaded. {ignored} ignored. {failed_downloads} failed.")

            self.app.image_download_button.configure(state='enabled')

    # Take a screenshot of any detected window for the currently loaded config
    def take_screenshot(self):
        existing_windows, missing_windows = self.window_manager.find_matching_windows(self.config)
        if existing_windows:
            for window in existing_windows:
                hwnd = window['hwnd']
                filename = window['config_name'].replace(' ', '_').replace(':', '')
                image_path = os.path.join(self.assets_dir, f"{filename}.jpg")
                self.asset_manager.capture_window(hwnd=hwnd, save_path=image_path)
        
            self.asset_manager.bring_to_front(hwnd=self.app.winfo_id())
            self.compute_window_layout(self.config, missing_windows)
            self.app.info_label.configure(text="Screenshot taken for all detected windows.")

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
                    positioned_windows.append(WindowInfo(section,
                                                         pos_x, pos_y,
                                                         size_w, size_h,
                                                         always_on_top=config[section].get("always_on_top", "false").lower() == "true",
                                                         exists=section not in missing_windows,
                                                         search_title=config[section].get("search_title") or section,
                                                         source_url=config[section].get("source_url", ''),
                                                         source=config[section].get("source", '')
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
        self.config_manager.save_settings(self.app.compact_mode, self.app.use_images.get(), self.app.snap.get(), self.app.details.get())

