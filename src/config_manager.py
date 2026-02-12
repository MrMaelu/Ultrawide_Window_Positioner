"""Configuration manager for the Ultrawide Window Positioner."""
import ast
import configparser
import contextlib
import json
import os
import re
from pathlib import Path

import pygetwindow as gw
import win32con
import win32gui

from constants import AOT_HOTKEY, LayoutDefaults

# Local imports
from utils import clean_window_title, match_titles


class ConfigManager:
    """Configuration manager."""

    def __init__(self, base_path:str|None)->None:
        """Initialize variables."""
        self.base_path = base_path

        self.config_dir = Path(self.base_path, "configs")
        self.settings_dir = Path(self.base_path, "settings")

        self.settings_file = Path(self.settings_dir, "settings.json")
        self.layout_config_file = Path(self.settings_dir, "layout_config.ini")

        self.default_layouts = {
            1: LayoutDefaults.ONE_WINDOW,
            2: LayoutDefaults.TWO_WINDOWS,
            3: LayoutDefaults.THREE_WINDOWS,
            4: LayoutDefaults.FOUR_WINDOWS,
            }

        self.layout_overrides = dict(LayoutDefaults.OVERRIDES)

        # Create directories if they don't exist
        if not Path.exists(self.config_dir):
            Path.mkdir(self.config_dir, parents=True)
        if not Path.exists(self.settings_dir):
            Path.mkdir(self.settings_dir, parents=True)


    def load_or_create_layouts(self, path:str, *, reset:bool=False)->tuple[dict,dict]:
        """Load layouts from config, or create new config with defaults."""
        path = Path(path)
        sections = ("Layouts", "Overrides")

        defaults = {
            sections[0]: {str(k): repr(v) for k, v in self.default_layouts.items()},
            sections[1]: {str(k): repr(v) for k, v in self.layout_overrides.items()},
        }

        config = configparser.ConfigParser()

        # Create/reset
        if reset or not path.exists():
            config.read_dict(defaults)
            with path.open("w") as f:
                f.write(LayoutDefaults.CONFIG_HEADER_TEXT)
                config.write(f)

        # Load existing file
        config.read(path)
        updated = False

        # Ensure required sections exist
        for section, values in defaults.items():
            if section not in config:
                config[section] = values
                updated = True

        if updated:
            with path.open("w") as f:
                config.write(f)

        # Parse values, ignoring invalid ones
        layouts, overrides = {}, {}

        for k, v in config[sections[0]].items():
            with contextlib.suppress(Exception):
                layouts[int(k)] = ast.literal_eval(v)

        for k, v in config[sections[1]].items():
            with contextlib.suppress(Exception):
                overrides[str(k)] = ast.literal_eval(v)

        return  layouts or self.default_layouts, overrides or self.layout_overrides


    def list_config_files(self)->tuple[list,list]:
        """List all configuration files and their names."""
        config_files = [
            f for f in self.config_dir.iterdir()
            if f.is_file() and f.name.startswith("config_") and f.name.endswith(".ini")
        ]

        config_files.sort()
        config_names = [
            f.name.replace("config_", "").replace(".ini","") for f in config_files
            ]
        return config_files, config_names


    def save_config(self, config:object, config_file:str)->None:
        """Save config file."""
        config_path = Path(self.config_dir, config_file)
        with Path.open(config_path, "w") as f:
            config.write(f)


    def load_config(self, config_path:str)->object:
        """Load a configuration file."""
        config = configparser.ConfigParser()
        full_path = Path(self.config_dir, config_path)
        if Path.exists(full_path):
            config.read(full_path)
            return config
        return None


    def load_settings(self)-> tuple[bool,bool,bool,bool]:
        """Load application settings."""
        defaults = 0, 0, 0, 0, AOT_HOTKEY
        if Path.exists(self.settings_file):
            with Path.open(self.settings_file) as f:
                settings = json.load(f)
                compact = settings.get("compact", 0)
                use_images = settings.get("use_images", 0)
                snap  = settings.get("snap", 0)
                details = settings.get("details", 0)
                hotkey = settings.get("hotkey", AOT_HOTKEY)
                return compact, use_images, snap, details, hotkey
        return defaults


    def save_settings(self, *,
                      compact_mode:bool,
                      use_images:bool,
                      snap:bool,
                      details:bool,
                      hotkey:str=AOT_HOTKEY,
                      )->bool:
        """Save application settings."""
        with Path.open(self.settings_file, "w") as f:
            json.dump({
                "compact": compact_mode,
                "use_images": use_images,
                "snap": snap,
                "details": details,
                "hotkey": hotkey,
                }, f)
        return True


    def detect_default_config(self)->list:
        """Detect and return the best default configuration."""
        c_files, c_names = self.list_config_files()
        highest_matching_windows = [None, 0]
        full_match = ""

        all_titles = gw.getAllTitles()

        for file in c_files:
            matching_windows = 0
            config = self.load_config(file)
            if not config:
                continue

            aot_sections = self._get_aot_sections(config)
            for section in aot_sections:
                for title in all_titles:
                    if match_titles(section, title):
                        full_match = c_names[c_files.index(file)]

            for section in config.sections():
                for title in all_titles:
                    if match_titles(section, title):
                        matching_windows += 1

            if matching_windows > highest_matching_windows[1]:
                highest_matching_windows[0] = (
                    c_names[c_files.index(file)]
                    )
                highest_matching_windows[1] = matching_windows

        if full_match:
            return full_match

        if highest_matching_windows[0]:
            return highest_matching_windows[0]

        return c_names[0] if c_names else None



    def _get_aot_sections(self, config:object)->list:
        """Get sections with always-on-top enabled."""
        aot_sections = []
        for section in config.sections():
            if config[section].getboolean("always_on_top", fallback=False):
                aot_sections.append(clean_window_title(section, sanitize=True))

        return aot_sections


    def save_window_config(self,
                           config_name:str,
                           window_data:list,
                           apply_order:list,
                           )->bool:
        """Save config."""
        if not config_name:
            return False

        config_name = clean_window_title(config_name, sanitize=True, titlecase=True)

        config = configparser.ConfigParser()
        config.optionxform = str

        # Prepare and sort entries by x-position
        entries = []
        for title, settings in window_data.items():
            if title and title.strip():
                if not settings.get("name"):
                    continue
                section_name = settings.get("name")
                section_name = clean_window_title(section_name, sanitize=True)
                position = str(settings.get("position") or "0,0")
                x = int(position.split(",")[0]) or 0
                entries.append((x, section_name, settings))

        entries.sort(key=lambda x: x[0])  # Left to right by x-position

        # Add sorted entries to config
        for _, section_name, settings in entries:
            config[section_name] = {
                "position": str(settings.get("position") or "0,0"),
                "size": str(settings.get("size") or "100,100"),
                "always_on_top": (str(settings.get("always_on_top")).lower()
                                    if "always_on_top" in settings else "false"),
                "titlebar": (str(settings.get("titlebar")).lower()
                                if "titlebar" in settings else "true"),
                "process_priority": (str(settings.get("process_priority")).lower()
                                if "process_priority" in settings else "false"),
            }

        # Store apply order in DEFAULT section (no new window section needed)
        if apply_order:
            config["DEFAULT"]["apply_order"] = ",".join(apply_order)

        validated_config = self.validate_and_repair_config(config)

        if not Path.is_dir(self.config_dir):
            return False

        config_path = Path(self.config_dir, f"config_{config_name}.ini")

        with Path.open(config_path, "w", encoding="utf-8") as config:
            validated_config.write(config)
            config.flush()
            os.fsync(config.fileno())

        return True


    def collect_window_settings(self, window_title:str)->dict|None:
        """Get settings for a window."""
        try:
            window = gw.getWindowsWithTitle(window_title)[0]
            # Get the current window state
            has_titlebar = bool(win32gui.GetWindowLong(window._hWnd, win32con.GWL_STYLE)  # noqa: SLF001
                          & win32con.WS_CAPTION)
            is_topmost = (window._hWnd == win32gui.GetForegroundWindow())  # noqa: SLF001
            return {
                "position": f"{max(-10, window.left)},{max(-10, window.top)}",
                "size": f"{max(250, window.width)},{max(250, window.height)}",
                "always_on_top": str(is_topmost).lower(),
                "titlebar": str(has_titlebar).lower(),
                "original_title": window_title,
                "name": clean_window_title(window_title, sanitize=True),
            }
        except (win32gui.error):
            return None


    def delete_config(self, name:str)->bool:
        """Delete a config file."""
        try:
            path = Path(self.config_dir, f"config_{name}.ini")
            if Path.exists(path):
                Path.unlink(path)
                return True
        except PermissionError:
            pass
        return False


    def validate_and_repair_config(self, config:str)->object:  # noqa: C901
        """Validate and repair a config file."""
        repaired_config = configparser.ConfigParser()
        repaired_config.optionxform = str

        for section in config.sections():
            if not section.strip():
                continue

            valid_items = {}
            for key, value in config.items(section):
                if key == "position":
                    valid_items[key] = (
                        value if re.match(r"^-?\d+,-?\d+$", value) else "0,0"
                        )
                elif key == "size":
                    valid_items[key] = (
                        value if re.match(r"^\d+,\d+$", value) else "100,100"
                        )
                elif key == "always_on_top":
                    valid_items[key] = (
                        value.lower()
                        if value.lower() in ("true", "false") else "false"
                        )
                elif key == "titlebar":
                    valid_items[key] = (
                        value.lower()
                        if value.lower() in ("true", "false") else "true")
                elif key == "process_priority":
                    valid_items[key] = (
                        value.lower()
                        if value.lower() in ("true", "false") else "false"
                        )
                elif value is not None and value.strip():
                    valid_items[key] = value.strip()

            if valid_items:
                repaired_config.add_section(section)
                for key, val in valid_items.items():
                    repaired_config.set(section, key, str(val))

        if config.has_option("DEFAULT", "apply_order"):
            repaired_config["DEFAULT"]["apply_order"] = (
                config.get("DEFAULT", "apply_order")
                )

        return repaired_config


    def update_rawg_url(self, title:str, rawg_url:str)->bool:
        """Update the RAWG URL for a title."""
        try:
            config = configparser.ConfigParser()
            config_files, config_names = self.list_config_files()
            for config_file in config_files:
                full_path = Path(self.config_dir, config_file)
                if not Path.exists(full_path):
                    continue
                config.read(full_path)
                if not config.has_section(title):
                    config.add_section(title)

                config.set(title, "rawg_url", rawg_url)

                with Path.open(config_file, "w") as f:
                    config.write(f)
                return True
        except (PermissionError, FileNotFoundError):
            return False


