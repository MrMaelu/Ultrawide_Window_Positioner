"""Configuration manager for the Ultrawide Window Positioner."""
from __future__ import annotations

import ast
import json
import logging
import os
import re
from configparser import ConfigParser
from pathlib import Path

from uwp_constants import AOT_HOTKEY, LayoutDefaults

# Local imports
from uwp_utils import clean_window_title, format_coords, match_titles, parse_coords

logger = logging.getLogger(__name__)

def get_ignore_list(config: ConfigParser) -> list[str]:
    """Get the ignore list from the config."""
    for title in config.sections():
        if config[title].get("ignore_list"):
            return config[title].get("ignore_list").split(",")
    return []


def safe_eval_layout_value(value: str) -> dict | list | tuple | None:
    """Parse the layout value from string to Python structure safely."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None

    # permit JSON-style or Python tuple/list syntax
    try:
        return json.loads(value)
    except ValueError:
        pass

    try:
        evaluated = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        logger.warning("Invalid layout value, skipping: %r (error: %s)", value, exc)
        return None

    if not isinstance(evaluated, (dict, list, tuple)):
        logger.warning("Unexpected layout type, skipping: %r", type(evaluated).__name__)
        return None

    return evaluated


def validate_and_repair_config(config: ConfigParser) -> ConfigParser:
    """Validate and repair a configuration file."""
    repaired_config = ConfigParser()
    repaired_config.optionxform = str

    for section in config.sections():
        if not section.strip():
            continue

        valid_items = {}
        for key, value in config.items(section):
            if key in ("position", "size"):
                d_val = (0, 0) if key == "position" else (800, 600)
                coords = parse_coords(value, default=d_val)
                valid_items[key] = format_coords(*coords)
            elif key in ("always_on_top", "titlebar", "process_priority"):
                valid_items[key] = str(value).lower() if str(value).lower() in ("true", "false") else "false"
            else:
                valid_items[key] = value.strip()

        if valid_items:
            repaired_config.add_section(section)
            for k, v in valid_items.items():
                repaired_config.set(section, k, v)

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

    def load_or_create_layouts(self)->tuple[dict,dict]:
        """Load layouts and overrides from settings.json."""
        # This method now delegates to load_settings for layouts and overrides
        _, _, _, _, _, layouts, overrides = self.load_settings()

        # Fall back to defaults if not found in settings
        if not layouts:
            layouts = self.default_layouts
        if not overrides:
            overrides = self.layout_overrides

        return layouts, overrides


    def list_config_files(self)->dict:
        """List all configuration files and their names."""
        config_files = [f for f in self.config_dir.iterdir()
                        if f.is_file() and f.name.startswith("config_") and f.name.endswith(".ini")]
        config_files.sort()
        config_names = [f.name.replace("config_", "").replace(".ini","") for f in config_files]
        return dict(zip(config_names, config_files, strict=False))


    def load_config(self, config_path:str)-> ConfigParser | None:
        """Load a configuration file."""
        config = ConfigParser()
        full_path = Path(self.config_dir, config_path)
        if Path.exists(full_path):
            config.read(full_path)
            return validate_and_repair_config(config)
        return None


    def load_settings(self)-> tuple[bool,bool,int,bool, str, dict, dict]:
        """Load application settings, layouts, and overrides."""
        defaults = False, False, 0, False, AOT_HOTKEY, self.default_layouts, self.layout_overrides
        if Path.exists(self.settings_file):
            with Path.open(self.settings_file) as f:
                try:
                    settings = json.load(f)
                    ui_settings = settings.get("ui", {})
                    compact = ui_settings.get("compact", False)
                    use_images = ui_settings.get("use_images", False)
                    snap = ui_settings.get("snap", 0)
                    details = ui_settings.get("details", False)
                    hotkey = ui_settings.get("hotkey", AOT_HOTKEY)

                    layouts = settings.get("layouts", self.default_layouts)
                    overrides = settings.get("overrides", self.layout_overrides)
                except (json.decoder.JSONDecodeError, AttributeError):
                    return defaults
                return compact, use_images, snap, details, hotkey, layouts, overrides
        return defaults


    def save_settings(self, *,  # noqa: PLR0913
                      compact_mode:bool,
                      use_images:bool,
                      snap:int,
                      details:bool,
                      hotkey:str=AOT_HOTKEY,
                      layouts:dict | None=None,
                      overrides:dict | None=None,
                      )->bool:
        """Save application settings, optionally including layouts and overrides."""
        settings = {
            "ui": {
                "compact": compact_mode,
                "use_images": use_images,
                "snap": snap,
                "details": details,
                "hotkey": hotkey,
            },
        }

        settings["layouts"] = layouts or self.default_layouts
        settings["overrides"] = overrides or self.layout_overrides

        with Path.open(self.settings_file, "w") as f:
            json.dump(settings, f, indent=4)

        # Reformatting the JSON to be more human readable
        with Path.open(self.settings_file, "r") as f:
            content = f.read()

        patterns = [
            (r"\[\s+", "["),
            (r",\s+", ","),
            (r"\s+\]", "]"),
            (r'\]\],\"', ']],\n\t\t"'),
            (r"\[\[\[\[", "[\n\t\t\t[[["),
            (r",\[\[\[", ",\n\t\t\t[[["),
            (r"\]\]\]\]", "]]]\n\t\t\t]"),
            (r'\],"', '],\n\t\t"'),
            (r'\},"', '},\n\t"'),
            (r",", ", "),
        ]

        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        with Path.open(self.settings_file, "w") as f:
            f.write(content)

        return True


    def detect_default_config(self, windows: list, files: dict | None = None)->str | None:
        """Detect and return the best default configuration."""
        config_files = files if isinstance(files, dict) else self.list_config_files()
        highest_matching_windows = ["", 0]
        aot_match = ""

        for name, file in config_files.items():
            config = self.load_config(file)
            if not config:
                continue

            aot_sections = []
            for section in config.sections():
                if config[section].getboolean("always_on_top", fallback=False):
                    aot_sections.append(section)  # noqa: PERF401

            if match_titles(aot_sections, windows):
                aot_match = name
                continue

            match_list = match_titles(config.sections(), windows, get_titles=True)
            if match_list:
                matching_windows = len(match_list)

                if matching_windows > highest_matching_windows[1]:
                    highest_matching_windows[0] = name
                    highest_matching_windows[1] = matching_windows

        if aot_match:
            return aot_match

        if highest_matching_windows[0]:
            return highest_matching_windows[0]

        return None


    def save_window_config(self,
                           config_name: str,
                           window_data: dict,
                           apply_order: list,
                           ignore_list: list | None = None,
                           ) -> bool:
        """Save config."""
        if not config_name:
            return False

        config = ConfigParser()
        config.optionxform = str

        # Prepare and sort entries by x-position
        entries = []
        for title, settings in window_data.items():
            s = settings if isinstance(settings, dict) else dict(settings)
            name = s.get("name")
            if not title.strip() or not name:
                continue
            pos_x = parse_coords(s.get("position", "0,0"))
            entries.append((pos_x, name, settings))

        # Sort left to right by x-position
        entries.sort(key=lambda x: x[0])

        # Add sorted entries to config
        for _, section, s in entries:
            config[section] = {
                "position": s.get("position"),
                "size": s.get("size"),
                "always_on_top": str(s.get("always_on_top", "false")).lower(),
                "titlebar": str(s.get("titlebar", "true")).lower(),
                "exe": str(s.get("exe")).lower(),
            }

        # Store apply order and ignore list in DEFAULT section
        config["DEFAULT"]["apply_order"] = ",".join(apply_order) or ""
        config["DEFAULT"]["ignore_list"] = ",".join(ignore_list) or ""

        validated_config = validate_and_repair_config(config)
        config_path = Path(self.config_dir) / f"config_{clean_window_title(config_name, titlecase=True)[0]}.ini"
        try:
            with Path.open(config_path, "w", encoding="utf-8") as f:
                validated_config.write(f)
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            return False

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

