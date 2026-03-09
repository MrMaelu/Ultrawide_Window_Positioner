"""Callback handler for Ultrawide Window Positioner."""
import datetime
import logging
import os
import subprocess
import sys
import threading
from ctypes import WinError, get_last_error, windll
from pathlib import Path
from time import sleep

# Local imports
from constants import UIConstants
from utils import clean_window_title
from window_manager import WindowManager

logger = logging.getLogger(__name__)

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

        self.config_manager = config_manager
        self.window_manager = WindowManager()
        self.asset_manager = asset_manager

        self.base_path = config_manager.base_path
        self.assets_dir = self.asset_manager.assets_dir
        self.config_dir = self.config_manager.config_dir

        self.config = None
        self.applied_config = None
        self.compact = False

        self.apply_thread_running = False
        self.reapply_last_pause = False
        self.reapply_last_enabled = False
        self.reapply_last_matching_windows = []

        self.callbacks = {
            "apply_config": self.apply_settings,
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
            "auto_reapply": self.auto_reapply,
            "details": self._window_details,
            "detect_config": self.detect_config,
        }

# ************************************************* #
#               Callback functions                  #
# ************************************************* #

    # Applying configuration settings
    def _apply_settings_worker(self, *, reapply:bool=False) -> None:
        self.apply_thread_running = True
        sleep(0.5)

        self.window_manager.remove_invalid_windows()
        logger.info("Managed windows before applying config: %s",
                    self.window_manager.managed_windows)

        selected_config_shortname = None

        if not reapply:
            index = self.get_combo_value()
            selected_config_shortname = self.toggle_active_config(index)
            self.app.applied_config = selected_config_shortname

        if not self.applied_config:
            selected_config_shortname = None
        else:
            matching_windows, _ = (
                self.window_manager.find_matching_windows(self.applied_config)
                )

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
                    "process_priority": self.applied_config.getboolean(
                        section,
                        "process_priority",
                        fallback=False,
                        ),
                    "apply_order": self.applied_config.get(
                        section,
                        "apply_order",
                        fallback="",
                        ),
                }
                self.window_manager.apply_window_config(settings, hwnd)

        self.update_always_on_top_status()
        self.app.format_apply_reset_button(
            selected_config_shortname=selected_config_shortname,
            )

        self.apply_thread_running = False


    def apply_settings(self, *, reapply:bool=False)->None:
        """Apply window settings for selected config."""
        thread = threading.Thread(target=self._apply_settings_worker,
                                  kwargs={"reapply": reapply},
                                  daemon=True)
        thread.start()
        return thread



    # Open the configuration creation dialog
    def create_config(self)->None:
        """Open the window for config setup."""
        self.app.create_config_ui(self.app,
            self.window_manager.get_all_window_titles(self.get_own_hwnd()),
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
        self.app.reapply_paused = not self.app.reapply_paused


    # Load new config when selecting an item from the dropdown
    def on_config_select(self)->None:
        """Load new config when selecting an item from the dropdown."""
        missing = []
        selected_value = self.get_combo_value()
        if selected_value in self.config_names:
            idx = self.config_names.index(selected_value)
            selected_config = self.config_files[idx]
            loaded_config = self.config_manager.load_config(selected_config)
            self.config = self.config_manager.validate_and_repair_config(loaded_config)
            matching, missing = self.window_manager.find_matching_windows(self.config)

        screenshot_button_enabled = (
            (not self.applied_config or self.config == self.applied_config)
            and bool(matching)
            )
        self.app.screenshot_button.setEnabled(screenshot_button_enabled)

        if not self.app.compact_mode:
            self.update_window_layout(self.config, missing)
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
        current_name = self.get_combo_value()
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
        ignored = 0
        number_of_images = 0
        failed_downloads = 0
        for title, pairs in search_titles.items():
            filename = title.replace(" ", "_").replace(":", "")
            image_path = Path(self.assets_dir, f"{filename}.jpg")

            source_url = ""
            source = ""

            if not Path.exists(image_path):
                if self.app.info_label:
                    self.app.info_label.setText(f"Downloading image for {title}")

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
        number_of_images = failed_downloads = ignored = 0
        self.app.image_download_button.setEnabled(False)

        search_titles = self._get_search_titles()

        # Downloading screenshots for all titles
        ignored, number_of_images, failed_downloads = (
            self._get_screenshots(search_titles=search_titles)
            )

        _, missing_windows = self.window_manager.find_matching_windows(self.config)
        if not self.compact:
            self.update_window_layout(self.config, missing_windows)

            if self.app.info_label:
                self.app.info_label.setText(
                    f"Image download complete. {number_of_images} images downloaded. "
                    f"{ignored} ignored. {failed_downloads} failed.",
                    )

        self.app.image_download_button.setEnabled(True)

    def _download_screenshots_threaded(self)->None:
        threading.Thread(target=self.download_screenshots, daemon=True).start()


    def toggle_images(self)->None:
        """Toggle image/screenshot view. Only used for ctk."""
        if self.ui.ui_type == "ctk":
            self.save_settings()
            _, missing_windows = self.window_manager.find_matching_windows(self.config)
            self.update_window_layout(self.config, missing_windows)


    def _take_screenshot_worker(self)->None:
        """Take a screenshot of the windows in the currently selected config."""
        reapply = False
        if self.applied_config == self.config:
            reapply = True
        elif self.applied_config:
            return

        apply_thread = self.apply_settings(reapply=reapply)
        apply_thread.join()

        existing, missing = self.window_manager.find_matching_windows(self.config)
        if existing:
            for window in existing:
                hwnd = window["hwnd"]
                filename = window["config_name"].replace(" ", "_").replace(":", "")
                image_path = Path(self.assets_dir, f"{filename}.jpg")
                self.asset_manager.capture_window(hwnd=hwnd, save_path=image_path)

            self.window_manager.bring_to_front(hwnd=self.get_own_hwnd())
            self.update_window_layout(self.config, missing)
            self.app.info_label.setText("Screenshot taken for all detected windows.")



    def take_screenshot(self)->None:
        """Take a screenshot of the windows in the currently selected config."""
        if self.app.reapply:
            self.app.reapply_paused = True

        worker = threading.Thread(target=self._take_screenshot_worker, daemon=True)
        worker.start()

        self.app.reapply_paused = False




    def _check_reapply_conditions(self)->bool:
        """Check if conditions are met for auto-reapply to run."""
        conditions = [
            self.app.reapply,
            self.app.config_active,
            not self.apply_thread_running,
            not self.app.reapply_paused,
        ]

        return all(conditions)


    def auto_reapply(self)->None:
        """Update the window list and reapplies settings."""
        print("Auto-reapply check running...", datetime.datetime.now().strftime("%H:%M:%S"))  # noqa: DTZ005, E501
        if not self._check_reapply_conditions():
            return

        matching_windows, missing_windows = self.window_manager.find_matching_windows(
            self.applied_config,
            )

        self.update_window_layout(self.applied_config, missing_windows)

        if not matching_windows:
            return

        print(f"Matching windows found: {[w['config_name'] for w in matching_windows]} at {datetime.datetime.now().strftime('%H:%M:%S')}")  # noqa: DTZ005, E501

        verify_results = self._verify_window_data(
            self.applied_config, matching_windows)

        if not verify_results:
            print("Auto-reapply triggered", datetime.datetime.now().strftime("%H:%M:%S"))  # noqa: DTZ005, E501
            logger.info("Changes detected, reapplying settings...\n")
            # Sleep 500 ms before reapplying to avoid potential issues with windows
            # that are in the process of opening or closing
            self.apply_settings(reapply=True)


    def _verify_window_data(self, settings:object, matching_windows:list)->bool:
        compare_results = []
        for match in matching_windows:
            hwnd = match["hwnd"]
            section = match["config_name"]

            settings = self._get_window_settings_from_config(settings, section)
            metrics = self.window_manager.get_window_metrics(hwnd)

            if not metrics:
                continue

            compare_results.append(self.compare_window_data(settings, metrics))

        return all(compare_results)


    # Toggles window details text overlay
    def _window_details(self)->None:
        self.save_settings()
        self.on_config_select()


# ************************************************* #
#               Helper functions                    #
# ************************************************* #


    def toggle_active_config(self, index:str)->None:
        """Toggle the active config."""
        self.app.config_active = not self.app.config_active
        if self.app.config_active:
            selected_config = self.config_files[self.config_names.index(index)]
            selected_config_shortname = (
                selected_config.name.replace("config_", "").replace(".ini", "")
                )
            config = self.config_manager.load_config(selected_config)
            self.applied_config = config
            logger.info("Applied config: %s", selected_config_shortname)
            logger.info("Managed windows: %s\n",
                        self.window_manager.managed_windows)
            return selected_config_shortname

        self.applied_config = None
        self.window_manager.reset_all_windows()

        logger.info("Config cleared.")
        logger.info("Managed windows after reset: %s\n",
                    self.window_manager.managed_windows)

        return None

    # Will save the status of the toggles to settings file
    # (compact mode, use images, snap on startup position and show window details)
    def save_settings(self)->None:
        """Save GUI settings."""
        compact, images, snap, details, hotkey = self.get_save_values()
        self.config_manager.save_settings(
            compact_mode=compact,
            use_images=images,
            snap=snap,
            details=details,
            hotkey=hotkey,
            )


    def compare_window_data(self, settings:object, metrics:list)->bool:
        """Check if the metrics for a window match the config settings."""
        differences = []

        settings_pos = tuple(
            map(int, settings["position"].split(",")),
            ) if settings["position"] else (0, 0)

        if settings_pos != metrics["position"]:
            differences.append(
                f"Position mismatch: Settings = {settings_pos}, "
                f"Metrics = {metrics['position']}",
                )

        settings_size = tuple(
            map(int, settings["size"].split(",")),
            ) if settings["size"] else (0, 0)

        if settings_size != metrics["size"]:
            differences.append(
                f"Size mismatch: "
                f"Settings={settings_size}, Metrics={metrics['size']}",
                )

        settings_aot = settings["always_on_top"]
        metrics_aot = (metrics["exstyle"] & 0x00000008) != 0

        if settings_aot != metrics_aot:
            differences.append(
                f"Always on top mismatch: Settings = {settings_aot}, "
                f"Metrics = {metrics_aot}",
                )

        settings_titlebar = settings["has_titlebar"]
        metrics_titlebar = (metrics["style"] & 0x00C00000) != 0

        if settings_titlebar != metrics_titlebar:
            differences.append(f"Titlebar mismatch: Settings = {settings_titlebar}, "
                               f"Metrics = {metrics_titlebar}",
                               )
        if differences:
            logger.info("Differences found for window:")
            for diff in differences:
                logger.info("Difference: %s", diff)

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
            self.set_combo_values(self.config_names, config or self.config_names[0])
            self.on_config_select()
        else:
            self.set_combo_values(["No configs found"], "No configs found")
            self.on_config_select()


    def update_window_layout(self, config:object, missing_windows:list)->None:
        """Update the layout."""
        windows = self.window_manager.get_windows_for_layout(config, missing_windows)
        self.app.set_layout_frame(windows)


    def update_always_on_top_status(self)->None:
        """Change the status label text to reflect current number of AOT windows."""
        status = self.window_manager.get_always_on_top_status()
        self.app.aot_label.setText(status)


    def get_combo_value(self)->str:
        """Get the current combobox value."""
        return self.app.combo_box.currentText()


    def set_combo_values(self, values:list, current:str)->None:
        """Update the values for the combobox."""
        self.app.combo_box.clear()
        self.app.combo_box.addItems(values)
        if current:
            self.app.combo_box.setCurrentText(current)


    def get_save_values(self)->tuple[bool,bool,bool]:
        """Get the values to save in the settings file."""
        return (
            self.app.compact_mode,
            self.app.use_images,
            self.app.snap,
            self.app.details,
            self.app.hotkey,
            )


    def get_own_hwnd(self) -> int:
        """Get the HWND for the main GUI window."""
        return int(self.app.winId())




    def _get_window_settings_from_config(self, config:object, section:str)->dict:
        """Extract the relevant settings from the config for a given section."""
        pos = config.get(section, "position", fallback=None)
        size = config.get(section, "size", fallback=None)
        aot = config.getboolean(section, "always_on_top", fallback=False)
        titlebar = config.getboolean(section, "titlebar", fallback=True)

        return {
            "position": pos,
            "size": size,
            "always_on_top": aot,
            "has_titlebar": titlebar,
        }

