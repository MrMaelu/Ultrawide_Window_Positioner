"""Callback handler for Ultrawide Window Positioner."""
import os
import subprocess
import sys
import threading
from ctypes import WinError, get_last_error, windll
from pathlib import Path

# Local imports
from constants import UIConstants
from utils import clean_window_title
from window_manager import WindowManager


def messagebox(title:str, message:str, style:str)->str:
    """Show a Windows native messagebox."""
    result = windll.user32.MessageBoxW(None, message, title, style)
    if not result:
        raise WinError(get_last_error())
    return result

class CallbackManager:
    """Callback manager class."""

    def __init__(self, app:object, config_manager:object, asset_manager:object) -> None:
        """Set up variables."""
        self.app = app
        self.ui = UIAdapter(self.app)

        self.config_manager = config_manager
        self.window_manager = WindowManager()
        self.asset_manager = asset_manager

        self.base_path = config_manager.base_path
        self.assets_dir = self.asset_manager.assets_dir
        self.config_dir = self.config_manager.config_dir

        self.config = None
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
            "download_images": self._download_screenshots_threaded,
            "toggle_images": self.toggle_images,
            "screenshot": self.take_screenshot,
            "snap": self.save_settings,
            "auto_reapply": self.start_auto_reapply,
            "details": self._window_details,
            "detect_config": self.detect_config,
        }

# ************************************************* #
#               Callback functions                  #
# ************************************************* #

    # Applying configuration settings
    def apply_settings(self, *, reapply:bool=False) -> None:
        """Apply window settings for selected config."""
        index = self.ui.get_combo_value()
        selected_config_shortname = None
        if not reapply:
            self.app.config_active = not self.app.config_active

            if self.app.config_active:
                selected_config = self.config_files[self.config_names.index(index)]
                selected_config_shortname = (
                    selected_config.name.replace("config_", "").replace(".ini", "")
                    )
                config = self.config_manager.load_config(selected_config)
                self.applied_config = config
                self.ui.format_apply_reset_button(
                    selected_config_shortname=selected_config,
                    )

            elif not self.app.config_active:
                self.applied_config = None
                self.window_manager.reset_all_windows()

        if self.applied_config:
            matching_windows, _ = (
                self.window_manager.find_matching_windows(self.applied_config)
                )
            self.window_manager.reset_all_windows()

            # Apply configuration
            for match in matching_windows:
                hwnd = match["hwnd"]
                section = match["config_name"]
                settings = {
                    "position":self.applied_config.get(
                        section,
                        "position",
                        fallback=None,
                        ),
                    "size": self.applied_config.get(
                        section,
                        "size",
                        fallback=None,
                        ),
                    "always_on_top": self.applied_config.getboolean(
                        section,
                        "always_on_top",
                        fallback=False,
                        ),
                    "has_titlebar": self.applied_config.getboolean(
                        section,
                        "titlebar",
                        fallback=True,
                        ),
                }

                self.window_manager.apply_window_config(settings, hwnd, section)

        self.update_always_on_top_status()
        self.app.applied_config = selected_config_shortname
        self.ui.format_apply_reset_button(
            selected_config_shortname=selected_config_shortname,
            )

    def apply_settings_threaded(self)->None:
        """Start a separate thread for applying config."""
        threading.Thread(target=self.apply_settings, daemon=True).start()


    # Open the configuration creation dialog
    def create_config(self)->None:
        """Open the window for config setup."""
        self.app.create_config_ui(self.app,
            self.window_manager.get_all_window_titles(),
            self.config_manager.save_window_config,
            self.config_manager.collect_window_settings,
            self.update_config_list,
        )


    def open_config_folder(self)->None:
        """Open the config folder in File Explorer."""
        if sys.platform == "win32":
            subprocess.Popen(["C:/windows/explorer", self.config_dir])  # noqa: S603


    def restart_as_admin(self)->None:
        """Restart the application with admin privileges."""
        rc_code = 32
        if sys.platform == "win32":
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            rc = windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1,
            )
            if rc > rc_code:
                os._exit(0)


    # Toggle always-on-top status for windows in the applied config
    def toggle_always_on_top(self)->None:
        """Toggle always-on-top status for windows in the applied config."""
        for hwnd in self.window_manager.topmost_windows:
            self.window_manager.toggle_always_on_top(hwnd)
        self.update_always_on_top_status()
        self.app.reapply = False


    # Load new config when selecting an item from the dropdown
    def on_config_select(self)->None:
        """Load new config when selecting an item from the dropdown."""
        missing_windows = []
        selected_value = self.ui.get_combo_value()
        if selected_value in self.config_names:
            idx = self.config_names.index(selected_value)
            selected_config = self.config_files[idx]
            loaded_config = self.config_manager.load_config(selected_config)
            self.config = self.config_manager.validate_and_repair_config(loaded_config)
            _, missing_windows = self.window_manager.find_matching_windows(self.config)

        if not self.app.compact_mode:
            self.update_window_layout(self.config, missing_windows)
        else:
            self.update_managed_windows_list(self.config)


    def detect_config(self)->None:
        """Detect the best matching config based on available windows."""
        default_config = self.config_manager.detect_default_config()
        self.update_config_list(default_config)


    def toggle_compact_mode(self=None, *, startup:bool=False)->None:
        """Toggle between compact and full GUI modes."""
        self.app.toggle_compact(startup)
        self.compact = self.app.compact_mode
        self.save_settings()
        if self.app.compact_mode:
            self.update_managed_windows_list(self.config)
        else:
            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            self.update_window_layout(self.config, missing_windows)


    def delete_config(self)->None:
        """Delete the currently selected config."""
        messagebox_ok = 6
        current_name = self.ui.get_combo_value()
        if not current_name:
            messagebox(title="Error", message="No config selected to delete.", style=0)
            return

        confirm = messagebox(
            title="Confirm Delete",
            message=f"Delete config '{current_name}'?",
            style=4,
            )

        if confirm == messagebox_ok:
            deleted = self.config_manager.delete_config(current_name)
            if deleted:
                self.update_config_list()
            else:
                messagebox(
                    title="Error",
                    message=f"Failed to delete '{current_name}'.",
                    style=0,
                    )


    # Opening the folder containing the image files
    def open_image_folder(self)->None:
        """Open the image folder in File Explorer."""
        if sys.platform == "win32":
            subprocess.Popen(["C:/windows/explorer", self.assets_dir])  # noqa: S603



    def _get_search_titles(self)->dict:
        """Get all search titles from config files."""
        search_titles = {}

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

        return search_titles


    def _get_screenshots(self, search_titles:dict)->tuple[int,int,int]:
        """Search for and download screenshots, update config URLs."""
        for title, pairs in search_titles.items():
            filename = title.replace(" ", "_").replace(":", "")
            image_path = Path.join(self.assets_dir, f"{filename}.jpg")

            ignored = 0
            number_of_images = 0
            failed_downloads = 0
            source_url = ""
            source = ""

            if not Path.exists(image_path):
                if self.app.info_label:
                    self.ui.update_label(
                        self.app.info_label,
                        f"Downloading image for {title}",
                        )

                # Trying to download the screenshot
                result, source, source_url = self.asset_manager.search(
                    title,
                    save_dir=self.assets_dir,
                    )
                if result == "ignored":
                    ignored += 1
                    source_url = ""
                    source = ""
                elif result:
                    number_of_images += 1
                else:
                    failed_downloads += 1
                    source_url = ""
                    source = ""

            else:
                for config_file, section in pairs:
                    config = self.config_manager.load_config(config_file)
                    if config and section in config.sections():
                        source = config[section].get("source", "")
                        source_url = config[section].get("source_url", source_url)
                        if source_url:
                            break

        self._update_source_url(pairs=pairs, source=source, source_url=source_url)
        return ignored, number_of_images, failed_downloads


    def _update_source_url(self, pairs:list, source:str, source_url:str)->None:
        """Update the config files with the source_url."""
        for config_file, section in pairs:
            config = self.config_manager.load_config(config_file)
            if config and section in config.sections():
                config.set(section, "source", source)
                config.set(section, "source_url", source_url)
                self.config_manager.save_config(config, config_file)


    def download_screenshots(self)->None:
        """Download screenshots from IGDB and RAWG."""
        number_of_images = 0
        failed_downloads = 0
        ignored = 0
        self.ui.set_widget_state(self.app.image_download_button, enabled=False)

        search_titles = self._get_search_titles()

        # Downloading screenshots for all titles
        self._get_screenshots(search_titles=search_titles)

        _, missing_windows = self.window_manager.find_matching_windows(self.config)
        if not self.compact:
            self.update_window_layout(self.config, missing_windows)

            if self.app.info_label:
                self.ui.update_label(
                    self.app.info_label,
                    f"Image download complete. {number_of_images} images downloaded. "
                    f"{ignored} ignored. {failed_downloads} failed.",
                    )

        self.ui.set_widget_state(self.app.image_download_button, enabled=True)

    def _download_screenshots_threaded(self)->None:
        threading.Thread(target=self.download_screenshots, daemon=True).start()


    def toggle_images(self)->None:
        """Toggle image/screenshot view. Only used for ctk."""
        if self.ui.ui_type == "ctk":
            self.save_settings()
            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            self.update_window_layout(self.config, missing_windows)



    def take_screenshot(self)->None:
        """Take a screenshot of the windows in the currently selected config."""
        reset_config = False
        if self.applied_config:
            if self.applied_config != self.config:
                self.apply_settings()
            else:
                reset_config = True
        else:
            self.apply_settings()

        existing, missing = self.window_manager.find_matching_windows(self.config)
        if existing:
            for window in existing:
                hwnd = window["hwnd"]
                filename = window["config_name"].replace(" ", "_").replace(":", "")
                image_path = Path(self.assets_dir, f"{filename}.jpg")
                self.asset_manager.capture_window(hwnd=hwnd, save_path=image_path)

            self.asset_manager.bring_to_front(hwnd=self.ui.get_own_hwnd())
            self.update_window_layout(self.config, missing)
            self.ui.update_label(
                self.app.info_label,
                "Screenshot taken for all detected windows.",
                )

        if not reset_config:
            self.apply_settings()


    def auto_reapply(self)->None:
        """Update the window list and reapplies settings."""
        if self.ui.get_reapply():
            matching_windows, _ = self.window_manager.find_matching_windows(
                self.applied_config,
                )
            compare_results = []
            for match in matching_windows:
                hwnd = match["hwnd"]
                section = match["config_name"]

                # Get window settings from config
                settings = {
                    "position": self.applied_config.get(
                        section,
                        "position",
                        fallback=None,
                        ),
                    "size": self.applied_config.get(
                        section,
                        "size",
                        fallback=None,
                        ),
                    "always_on_top": self.applied_config.getboolean(
                        section,
                        "always_on_top",
                        fallback=False,
                        ),
                    "has_titlebar": self.applied_config.getboolean(
                        section,
                        "titlebar",
                        fallback=True,
                        ),
                }

                metrics = self.window_manager.get_window_metrics(hwnd)
                compare_results.append(self.compare_window_data(settings, metrics))
            if not all(compare_results):
                self.apply_settings(reapply=True)


    # Toggles window details text overlay
    def _window_details(self)->None:
        self.save_settings()
        self.on_config_select(self.app.combo_box)




# ************************************************* #
#               Helper functions                    #
# ************************************************* #

    # Will save the status of the toggles to settings file
    # (compact mode, use images, snap on startup position and show window details)
    def save_settings(self)->None:
        """Save GUI settings."""
        compact, images, snap, details = self.ui.get_save_values()
        self.config_manager.save_settings(
            compact_mode=compact,
            use_images=images,
            snap=snap,
            details=details,
            )


    def start_auto_reapply(self)->None:
        """Handle the auto reapply timer and loop."""
        if self.ui.get_reapply():
            self.auto_reapply()


    def compare_window_data(self, settings:object, metrics:list)->bool:
        """Check if the metrics for a window match the config settings."""
        differences = []

        settings_pos = tuple(
            map(int, settings["position"].split(",")),
            ) if settings["position"] else (0, 0)
        if settings_pos != metrics["position"]:
            differences.append(
                f"Position mismatch: Settings={settings_pos}, "
                f"Metrics={metrics['position']}",
                )

        settings_size = tuple(
            map(int, settings["size"].split(",")),
            ) if settings["size"] else (0, 0)
        if settings_size != metrics["size"]:
            differences.append(
                f"Size mismatch: Settings={settings_size}, Metrics={metrics['size']}",
                )

        settings_aot = settings["always_on_top"]
        metrics_aot = (metrics["exstyle"] & 0x00000008) != 0
        if settings_aot != metrics_aot:
            differences.append(
                f"Always on top mismatch: Settings={settings_aot}, "
                f"Metrics={metrics_aot}",
                )

        settings_titlebar = settings["has_titlebar"]
        metrics_titlebar = (metrics["style"] & 0x00C00000) != 0
        if settings_titlebar != metrics_titlebar:
            differences.append(f"Titlebar mismatch: Settings={settings_titlebar}, "
                               f"Metrics={metrics_titlebar}",
                               )

        return bool(not differences)


    def update_managed_windows_list(self, config:object)->None:
        """Update the elements in the managed windows list used in compact mode."""
        if not hasattr(self.app, "managed_text"):
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


    def update_config_list(self, config:object=None)->None:
        """Get new config list from disk."""
        self.config_files, self.config_names = self.config_manager.list_config_files()
        if self.config_files and self.config_names:
            self.ui.set_combo_values(self.config_names, config or self.config_names[0])
            self.on_config_select()
        else:
            self.ui.set_combo_values(["No configs found"], "No configs found")
            self.on_config_select()


    def update_window_layout(self, config:object, missing_windows:list)->None:
        """Update the layout."""
        windows = self.window_manager.get_windows_for_layout(config, missing_windows)
        self.app.set_layout_frame(windows)


    def update_always_on_top_status(self)->None:
        """Change the status label text to reflect current number of AOT windows."""
        status = self.window_manager.get_always_on_top_status()
        self.ui.update_label(self.app.aot_label, status)



class UIAdapter:
    """Helper class to translate between the different GUI frameworks."""

    def __init__(self, app:object)->None:
        """Set up variables."""
        self.app = app
        self.ui_type = app.ui_code

    def get_combo_value(self)->str:
        """Get the current combobox value."""
        if self.ui_type == "pyside":
            return self.app.combo_box.currentText()
        if self.ui_type == "ctk":
            return self.app.combo_box.get()
        return None

    def set_combo_values(self, values:list, current:str)->None:
        """Update the values for the combobox."""
        if self.ui_type == "pyside":
            self.app.combo_box.clear()
            self.app.combo_box.addItems(values)
            if current:
                self.app.combo_box.setCurrentText(current)
        elif self.ui_type == "ctk":
            self.app.combo_box.configure(values=values)
            if current:
                self.app.combo_box.set(current)

    def get_reapply(self)->bool:
        """Get the status of the reapply checkbox."""
        return self.app.reapply if self.ui_type == "pyside" else self.app.reapply.get()

    def get_save_values(self)->tuple[bool,bool,bool]:
        """Get the values to save in the settings file."""
        if self.ui_type == "pyside":
            return (
                self.app.compact_mode,
                self.app.use_images,
                self.app.snap,
                self.app.details,
                )

        if self.ui_type == "ctk":
            return (
                self.app.compact_mode,
                self.app.use_images.get(),
                self.app.snap.get(),
                self.app.details.get(),
                )

        return False, False, False, False

    def update_label(self, label:object, text:str)->None:
        """Update the text on a label."""
        if self.ui_type == "pyside":
            label.setText(text)
        elif self.ui_type == "ctk":
            label.configure(text=text)

    def set_widget_state(self, widget:object, *, enabled:bool)->None:
        """Set a widget to enabled or disabled."""
        if self.ui_type == "pyside":
            widget.setEnabled(enabled)
        elif self.ui_type == "ctk":
            if enabled:
                widget.configure(state="enabled")
            else:
                widget.configure(state="disabled")

    def format_apply_reset_button(self, *,
                                  selected_config_shortname:str="",
                                  disable:bool=False,
                                  )->None:
        """Set the correct format for the apply/reset button."""
        self.app.format_apply_reset_button(
            selected_config_shortname=selected_config_shortname,
            disable=disable if disable else None,
            )

    def set_timed_loop(self, delay:int)->None:
        """Start the auto-reapply loop timer."""
        if self.ui_type == "pyside":
            return
        if self.ui_type == "ctk":
            self.app.after(delay, self.parent.start_auto_reapply)

    def get_own_hwnd(self) -> int:
        """Get the HWND for the main GUI window."""
        if self.ui_type == "pyside":
            return int(self.app.winId())
        if self.ui_type == "ctk":
            return self.app.winfo_id()
        return None


