"""Configuration manager for the Ultrawide Window Positioner."""
import ast
from configparser import ConfigParser
import contextlib
import json
import logging
import os
import re
from pathlib import Path

from constants import AOT_HOTKEY, LayoutDefaults

# Local imports
from utils import clean_window_title, match_titles

logging.basicConfig(
    level=logging.INFO,
    filename="uwp_debug.log",
    format="%(asctime)s - %(levelname)s - %(message)s",
    )
logger = logging.getLogger(__name__)


def config_to_dict(config: ConfigParser) -> dict:
    config_dict = {s:dict(config.items(s)) for s in config.keys()}
    config_dict["DEFAULT"] = dict(config.defaults())
    return config_dict

def get_window_settings_from_config(config: ConfigParser, section:str)->dict:
    """Extract the relevant settings from the config for a given section."""
    return {
        "position": config.get(section, "position", fallback=None),
        "size": config.get(section, "size", fallback=None),
        "always_on_top": config.getboolean(section, "always_on_top", fallback=False),
        "has_titlebar": config.getboolean(section, "titlebar", fallback=True),
    }

def _get_aot_sections(config:ConfigParser)->list:
    """Get sections with always-on-top enabled."""
    aot_sections = []
    for section in config.sections():
        if config[section].getboolean("always_on_top", fallback=False):
            aot_sections.append(clean_window_title(section, sanitize=True))  # noqa: PERF401

    return aot_sections

def get_ignore_list(config: ConfigParser) -> list[str]:
    for title in config.sections():
        if config[title].get("ignore_list"):
            return config[title].get("ignore_list").split(",")
    return []


def validate_and_repair_config(config:ConfigParser)->ConfigParser:  # noqa: C901, PLR0912
    """Validate and repair a config file."""
    repaired_config = ConfigParser()
    repaired_config.optionxform = str

    for section in config.sections():
        if not section.strip():
            continue

        valid_items = {}
        for key, value in config.items(section):
            if key == "position":
                valid_items[key] = value if re.match(r"^-?\d+,-?\d+$", value) else "0,0"
            elif key == "size":
                valid_items[key] = value if re.match(r"^\d+,\d+$", value) else "800,600"
            elif key == "always_on_top":
                valid_items[key] = value.lower() if value.lower() in ("true", "false") else "false"
            elif key == "titlebar":
                valid_items[key] = value.lower() if value.lower() in ("true", "false") else "true"
            elif key == "process_priority":
                valid_items[key] = value.lower() if value.lower() in ("true", "false") else "false"
            elif value is not None and value.strip():
                valid_items[key] = value.strip()

        if valid_items:
            repaired_config.add_section(section)
            for key, val in valid_items.items():
                repaired_config.set(section, key, str(val))

    if config.has_option("DEFAULT", "apply_order"):
        repaired_config["DEFAULT"]["apply_order"] = config.get("DEFAULT", "apply_order")

    if config.has_option("DEFAULT", "ignore_list"):
        repaired_config["DEFAULT"]["ignore_list"] = config.get("DEFAULT", "ignore_list")

    return repaired_config


class ConfigManager:
    """Configuration manager."""

    def __init__(self, base_path:Path|None)->None:
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

    def get_search_titles(self) -> dict:
        """Get all search titles from config files."""
        search_titles = {}
        config_files, _ = self.list_config_files()

        for config_file in config_files:
            config = self.load_config(config_file)

            if not config:
                continue

            for section in config.sections():
                title = config[section].get("search_title", fallback=section)
                cleaned_title = clean_window_title(title, sanitize=True)
                if cleaned_title not in search_titles:
                    search_titles[cleaned_title] = []
                search_titles[cleaned_title].append((config_file, section))

        return search_titles


    def load_or_create_layouts(self, path:str | None=None, *, reset:bool=False)->tuple[dict,dict]:
        """Load layouts from config, or create new config with defaults."""
        if path:
            path = Path(path)
        else:
            path = self.layout_config_file

        sections = ("Layouts", "Overrides")

        defaults = {
            sections[0]: {str(k): repr(v) for k, v in self.default_layouts.items()},
            sections[1]: {str(k): repr(v) for k, v in self.layout_overrides.items()},
        }

        config = ConfigParser()

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

        if not layouts:
            layouts = self.default_layouts

        for k, v in config[sections[1]].items():
            with contextlib.suppress(Exception):
                overrides[str(k)] = ast.literal_eval(v)

        if not overrides:
            overrides = self.layout_overrides

        return  layouts, overrides


    def list_config_files(self)->tuple[list,list]:
        """List all configuration files and their names."""
        config_files = [
            f for f in self.config_dir.iterdir()
            if f.is_file() and f.name.startswith("config_") and f.name.endswith(".ini")
        ]

        config_files.sort()
        config_names = [
            f.name.replace("config_", "").replace(".ini","")
            for f in config_files
        ]

        return config_files, config_names


    def save_config(self, config:object, config_file:str)->None:
        """Save config file."""
        config_path = Path(self.config_dir, config_file)
        with Path.open(config_path, "w") as f:
            config.write(f)


    def load_config(self, config_path:str)-> ConfigParser | None:
        """Load a configuration file."""
        config = ConfigParser()
        full_path = Path(self.config_dir, config_path)
        if Path.exists(full_path):
            config.read(full_path)
            valid_config = validate_and_repair_config(config)
            return valid_config
        return None


    def load_settings(self)-> tuple[bool,bool,bool,bool, str]:
        """Load application settings."""
        if Path.exists(self.settings_file):
            with Path.open(self.settings_file) as f:
                settings = json.load(f)
                compact = settings.get("compact", 0)
                use_images = settings.get("use_images", 0)
                snap  = settings.get("snap", 0)
                details = settings.get("details", 0)
                hotkey = settings.get("hotkey", AOT_HOTKEY)
                return compact, use_images, snap, details, hotkey

        return False, False, False, False, AOT_HOTKEY


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


    def detect_default_config(self, windows: list)->str:
        """Detect and return the best default configuration."""
        c_files, c_names = self.list_config_files()
        highest_matching_windows = ["", 0]
        aot_match = ""

        for file in c_files:
            config = self.load_config(file)
            if not config:
                continue

            aot_sections = _get_aot_sections(config)
            if match_titles(aot_sections, windows):
                aot_match = c_names[c_files.index(file)]

            match_list = match_titles(config.sections(), windows, get_titles=True)
            matching_windows = len(match_list)

            if matching_windows > highest_matching_windows[1]:
                highest_matching_windows[0] = c_names[c_files.index(file)]
                highest_matching_windows[1] = matching_windows

        if aot_match:
            return aot_match

        if highest_matching_windows[0]:
            return highest_matching_windows[0]

        return c_names[0] if c_names else None

    def save_window_config(self,
                           config_name:str,
                           window_data:dict,
                           apply_order:list,
                           ignore_list:list | None =None,
                           )->bool:
        """Save config."""
        if not config_name:
            return False

        config_name = clean_window_title(config_name, sanitize=True, titlecase=True)

        config = ConfigParser()
        config.optionxform = str

        # Prepare and sort entries by x-position
        entries = []
        for title, settings in window_data.items():
            if title and title.strip():
                if not settings.get("name"):
                    continue
                section_name = clean_window_title(settings.get("name"), sanitize=True)
                position = str(settings.get("position") or "0,0")
                pos_x = int(position.split(",")[0]) or 0
                entries.append((pos_x, section_name, settings))

        entries.sort(key=lambda x: x[0])  # Left to right by x-position

        # Add sorted entries to config
        for _, section_name, settings in entries:
            config[section_name] = {
                "position": str(settings.get("position") or "0,0"),
                "size": str(settings.get("size") or "100,100"),
                "always_on_top": str(settings.get("always_on_top")).lower() if "always_on_top" in settings else "false",
                "titlebar": str(settings.get("titlebar")).lower() if "titlebar" in settings else "true",
                "process_priority": (
                    str(settings.get("process_priority")).lower() if "process_priority" in settings else "false"
                ),
            }

        # Store apply order and ignore list in DEFAULT section
        if apply_order:
            config["DEFAULT"]["apply_order"] = ",".join(apply_order)

        if ignore_list:
            config["DEFAULT"]["ignore_list"] = ",".join(ignore_list)

        validated_config = validate_and_repair_config(config)

        if not Path.is_dir(self.config_dir):
            return False

        config_path = Path(self.config_dir, f"config_{config_name}.ini")

        with Path.open(config_path, "w", encoding="utf-8") as config:
            validated_config.write(config)
            config.flush()
            os.fsync(config.fileno())

        return True


    def delete_config(self, name:str)->bool:
        """Delete a config file."""
        path = Path(self.config_dir, f"config_{name}.ini")
        if Path.exists(path):
            try:
                Path.unlink(path)
            except PermissionError as e:
                logger.info("Failed to delete config: %s", e)
                return False
            return True
        return False

