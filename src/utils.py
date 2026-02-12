"""Collection of utilities."""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import roman
import win32api


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


def match_titles(section: str, title: str) -> bool:
    """Return True when a window title matches a section name."""
    if not section or not title:
        return False

    sc = clean_window_title(section, sanitize=True)
    tc = clean_window_title(title, sanitize=True)

    # Exact match
    if tc == sc:
        return True

    # Prefix match that ensures a word boundary or the end follows the section
    pattern = r"^" + re.escape(sc) + r"(\b|$)"
    return bool(re.match(pattern, tc))


def get_version() -> str:
    """Read the application version from version.txt file."""
    try:
        if hasattr(__import__("sys"), "_MEIPASS"):
            # Pyinstaller fix
            exe = Path(sys.executable)
            info = win32api.GetFileVersionInfo(str(exe), "\\")
            ms = info["FileVersionMS"]
            ls = info["FileVersionLS"]
            version = (win32api.HIWORD(ms), win32api.LOWORD(ms),
                    win32api.HIWORD(ls), win32api.LOWORD(ls))
            return f"{version[0]}.{version[1]}.{version[2]}.{version[3]}"

        version_file = Path(__file__).resolve().parent.parent / "version.txt"
        if version_file.exists():
            with Path.open(version_file, "r", encoding="utf-8") as f:
                content = f.read()
                # Extract filevers tuple: filevers=(1, 0, 3, 0)
                match = re.search(
                    r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", content,
                    )
                if match:
                    major, minor, patch, build = match.groups()
                    # Ignore the build number, format as X.Y.Z
                    return f"{major}.{minor}.{patch}.{build}"
    except (OSError, AttributeError):
        pass

    return None
