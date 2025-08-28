"""Configuration manager for the Ultrawide Window Positioner."""
import ast
import configparser
import json
import os
import re
from pathlib import Path

import pygetwindow as gw
import win32con
import win32gui

from constants import LayoutDefaults

# Local imports
from utils import clean_window_title


class ConfigManager:
    """Configuration manager."""

    section = "Layouts"

    def __init__(self, base_path:str|None)->None:
        """Initialize variables."""
        self.base_path = base_path

        self.config_dir = Path(self.base_path, "configs")
        self.settings_dir = Path(self.base_path, "settings")

        self.settings_file = Path(self.settings_dir, "settings.json")
        self.layout_config_file = Path(self.settings_dir, "layout_config.ini")

        # Create directories if they don't exist
        if not Path.exists(self.config_dir):
            Path.mkdir(self.config_dir, parents=True)
        if not Path.exists(self.settings_dir):
            Path.mkdir(self.settings_dir, parents=True)

    @staticmethod
    def serialize(layouts: dict) -> configparser.ConfigParser:
        """."""
        config = configparser.ConfigParser()
        config[ConfigManager.section] = {}

        for key, entries in layouts.items():
            config[ConfigManager.section][str(key)] = repr(entries)
        return config

    @staticmethod
    def deserialize(config: configparser.ConfigParser) -> dict:
        """."""
        layouts = {}
        if ConfigManager.section not in config:
            return LayoutDefaults.DEFAULT_LAYOUTS

        for key in config[ConfigManager.section]:
            layouts[int(key)] = ast.literal_eval(config[ConfigManager.section][key])
        return layouts

    @staticmethod
    def load_or_create_layouts(path:str, *, reset:bool=False) -> dict:
        """Create new config file with defaults."""
        if reset or not Path.exists(path):
            config = ConfigManager.serialize(LayoutDefaults.DEFAULT_LAYOUTS)
            with Path.open(path, "w") as f:
                config.write(f)
            return LayoutDefaults.DEFAULT_LAYOUTS

        # Load config file
        if Path.exists(path):
            config = configparser.ConfigParser()
            config.read(path)
            return ConfigManager.deserialize(config)
        return None


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
        defaults = 0, 0, 0, 0
        if Path.exists(self.settings_file):
            with Path.open(self.settings_file) as f:
                settings = json.load(f)
                compact = settings.get("compact", 0)
                use_images = settings.get("use_images", 0)
                snap  = settings.get("snap", 0)
                details = settings.get("details", 0)
                return compact, use_images, snap, details
        return defaults


    def save_settings(self, *,
                      compact_mode:bool,
                      use_images:bool,
                      snap:bool,
                      details:bool,
                      )->bool:
        """Save application settings."""
        with Path.open(self.settings_file, "w") as f:
            json.dump({
                "compact": compact_mode,
                "use_images": use_images,
                "snap": snap,
                "details": details,
                }, f)
        return True

    def detect_default_config(self)->list:
        """Detect and return the best default configuration."""
        config_files, config_names = self.list_config_files()
        highest_matching_windows = [None, 0]

        all_titles = gw.getAllTitles()
        cleaned_titles = [
            clean_window_title(title, sanitize=True) for title in all_titles
            ]

        for config_file in config_files:
            matching_windows = 0
            config = self.load_config(config_file)
            if not config:
                continue

            for section in config.sections():
                if config[section].getboolean("always_on_top", fallback=False):
                    cleaned_section = clean_window_title(section, sanitize=True)

                    for title in cleaned_titles:
                        if cleaned_section in title:
                            return config_names[config_files.index(config_file)]
                elif section in cleaned_titles:
                    matching_windows += 1

            if matching_windows > highest_matching_windows[1]:
                highest_matching_windows[0] = (
                    config_names[config_files.index(config_file)]
                    )
                highest_matching_windows[1] = matching_windows

        if highest_matching_windows[0]:
            return highest_matching_windows[0]

        return config_names[0] if config_names else None


    def save_window_config(self, config_name:str, window_data:list)->bool:
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
            }

        validated_config = self.validate_and_repair_config(config)

        if not Path.isdir(self.config_dir):
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
            if not section.strip() or section.upper() == "DEFAULT":
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
                elif value is not None and value.strip():
                    valid_items[key] = value.strip()

            if valid_items:
                repaired_config.add_section(section)
                for key, val in valid_items.items():
                    repaired_config.set(section, key, str(val))

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
