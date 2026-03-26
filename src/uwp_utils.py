"""Collection of utilities."""
import os
import re
import sys
from ctypes import windll

import roman
import win32api

from pathlib import Path
from dataclasses import dataclass

@dataclass
class WindowInfo:
    """Hold information about application windows."""

    name: str
    pos_x: int
    pos_y: int
    width: int
    height: int
    always_on_top: bool
    exists: bool
    search_title: str
    source_url: str
    source: str

def clean_window_title(title:str, *, sanitize:bool=False, titlecase:bool=True)->str:
    """Remove special characters from title."""
    if not title:
        return ""

    # Basic cleaning
    title = re.sub(r"[^\x20-\x7E]", "", title)
    title = re.sub(r"\s+", " ", title)
    title = title.strip().lower()

    if sanitize:
        # Additional cleaning for config files
        parts = re.split(r" [-—–] ", title)  # noqa: RUF001
        title = parts[-1].strip()
        title = re.sub(r"\s+\d+%$", "", title)
        title = re.sub(r'[<>:"/\\|?*\[\]]', "", title)

    if titlecase:
        return uppercase_roman_numerals(title.title())

    return uppercase_roman_numerals(title)


def invert_hex_color(hex_color:str)->str:
    """Calculate the inverse of the given color."""
    r, g, b = convert_hex_to_rgb(hex_color)
    # Invert each component
    r_inv = 255 - r
    g_inv = 255 - g
    b_inv = 255 - b

    # Format back to hex
    return f"#{r_inv:02X}{g_inv:02X}{b_inv:02X}"


def convert_hex_to_rgb(hex_color:str)->tuple[int, int, int]:
    """Convert hex string to rgb int."""
    hex_length = 6
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == hex_length:
        # Split into RGB parts
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        return r, g, b
    return 0, 0, 0


def uppercase_roman_numerals(text:str)->str:
    """Convert lowercase roman numerals to uppercase in the given text."""
    sections = text.split()
    for i, section in enumerate(sections):
        try:
            roman.fromRoman(section)
            sections[i] = section.upper()
        except roman.InvalidRomanNumeralError:
            pass
    return " ".join(sections)


def match_titles(
        sections: list, titles: list,
        *, get_titles: bool = False,
        ) -> bool | dict:
    """Compare two lists for matching titles.

    Return True when a window title match a section name.
    If the variable get_titles is True, return a dict of section: title match.
    """
    if not sections or not titles:
        return False

    title_matches = {}
    for title in titles:
        for section in sections:
            sc = clean_window_title(section, sanitize=True)
            tc = clean_window_title(title, sanitize=True)

            # Exact match
            if sc == tc:
                if get_titles:
                    title_matches[section] = title
                else:
                    return True

            # Prefix match that ensures a word boundary or the end follows the section
            pattern = r"^" + re.escape(sc) + r"(\b|$)"
            if bool(re.match(pattern, tc)):
                if get_titles:
                    title_matches[section] = title
                else:
                    return True

    if get_titles:
        return title_matches

    return False

def get_version() -> str | None:
    """Read the application version from version.txt file."""
    try:
        if hasattr(__import__("sys"), "_MEIPASS"):
            # Pyinstaller fix
            exe = Path(sys.executable)
            info = win32api.GetFileVersionInfo(str(exe), "\\")
            ms = info["FileVersionMS"]
            ls = info["FileVersionLS"]
            version = (win32api.HIWORD(ms), win32api.LOWORD(ms), win32api.HIWORD(ls), win32api.LOWORD(ls))
            return f"{version[0]}.{version[1]}.{version[2]}.{version[3]}"

        version_file = Path(__file__).resolve().parent.parent / "version.txt"
        if version_file.exists():
            with Path.open(version_file, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", content)
                if match:
                    major, minor, patch, build = match.groups()
                    return f"{major}.{minor}.{patch}.{build}"
    except (OSError, AttributeError):
        pass

    return None

def to_bool(val: str | bool) -> bool:
    """Convert a string value to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return bool(val)


def validate_int_pair(value: str, default: tuple[int, int] = (0, 0)) -> tuple[int, int]:
    """Check if int pair is valid."""
    try:
        x, y = map(int, value.split(","))
    except ValueError:
        return default
    else:
        return x, y

def restart_as_admin()->None:
    """Restart the application with admin privileges."""
    rc_code = 32
    if sys.platform == "win32":
        params = " ".join([f'"{arg}"' for arg in sys.argv])
        rc = windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        if rc > rc_code:
            os._exit(0)
