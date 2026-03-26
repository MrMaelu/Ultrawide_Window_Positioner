"""Collection of utilities."""
import logging
import re
import subprocess
import sys
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

import psutil
import roman
import win32api
import win32con
import win32gui
import win32process

logger = logging.getLogger(__name__)

# noinspection SpellCheckingInspection
base_path = getattr(sys, "_MEIPASS", Path(Path(__file__).absolute().parent.parent))

@dataclass
class WindowMetrics:
    """Hold metrics data for a window or config."""

    x: int
    y: int
    w: int
    h: int
    aot: bool
    border: bool
    apply_order: str


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


@dataclass
class WindowsWindow:
    """Hold information about application windows."""

    hwnd: int
    pid: int
    title: str
    app_name: str
    app_path: str
    width: int
    height: int
    x: float
    y: float
    titlebar: bool
    aot: bool


def metrics_to_window_info(name: str, metrics: WindowMetrics, *, exists: bool)->WindowInfo:
    """Convert WindowMetrics to WindowInfo."""
    return WindowInfo(
        name,
        metrics.x,
        metrics.y,
        metrics.w,
        metrics.h,
        metrics.aot,
        exists,
        name,
    )



def window_to_metrics(window: WindowsWindow)->WindowMetrics | None:
    """Convert a WindowsWindow to WindowMetrics."""
    if not window:
        return None

    return WindowMetrics(
        int(float(window.x)),
        int(float(window.y)),
        int(float(window.width)),
        int(float(window.height)),
        window.aot,
        window.titlebar,
        "",
    )

def get_window_info(hwnd: int) -> WindowsWindow | None:
    """Get information about a window."""
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return None

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    rect = win32gui.GetWindowRect(hwnd)
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    # noinspection SpellCheckingInspection
    exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    x = rect[0]
    y = rect[1]
    aot = exstyle & win32con.WS_EX_TOPMOST != 0
    titlebar = style & win32con.WS_CAPTION != 0

    try:
        proc = psutil.Process(pid)
        app_name = proc.name()
        app_path = proc.exe()

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        app_name = ""
        app_path = ""

    return WindowsWindow(
        hwnd,
        pid,
        title[:60],
        app_name,
        app_path,
        width,
        height,
        x,
        y,
        titlebar,
        aot,
    )

def get_data_path(relative_path: str)->str:
    """Get the absolute path to a data file."""
    absolute_path = Path(base_path) / "data" / relative_path
    return absolute_path.as_posix()

def clean_window_title(title:str, exe:str="", *, titlecase:bool=True)->list:
    """Remove special characters from title."""
    if not title:
        return ["",""]

    parts = re.split(r" [-—–] ", title)  # noqa: RUF001
    title = parts[-1].strip()

    title = re.sub(r"\s+\d+%$", "", title)
    title = re.sub(r'[<>:"/\\|?*\[\]]', "", title)

    title = uppercase_roman_numerals(title.title()) if titlecase else uppercase_roman_numerals(title)
    if exe:
        return [title, exe.split(".")[0]]
    return  [title, title]


def run_clean_subprocess(command: list[str], *,
                         check_output: bool =False,
                         **kwargs: dict,
                         ) -> subprocess.CompletedProcess | bytes:
    """Run a subprocess."""
    if not check_output:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

    if check_output:
        return subprocess.check_output(command, **kwargs)  # noqa: S603
    return subprocess.run(command, check=False, **kwargs)  # noqa: S603


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


def match_titles(sections: list, titles: list, *, get_titles: bool = False) -> bool | dict:
    """Compare two lists for matching titles.

    Return True when a window title match a section name.
    If the variable get_titles is True, return a dict of section: title match.
    """
    if not sections or not titles:
        return {} if get_titles else False

    title_matches = {}
    for title in titles:
        if not title.strip():
            continue

        for section in sections:
            # Exact match
            if section == title:
                if get_titles:
                    title_matches[section] = title
                else:
                    return True

            # Prefix match that ensures a word boundary or the end follows the section
            pattern = r"^" + re.escape(section) + r"(\b|$)"
            if bool(re.match(pattern, title)):
                if get_titles:
                    title_matches[section] = title
                else:
                    return True

    if get_titles:
        return title_matches

    return False


def to_bool(*, val: str | bool) -> bool:
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


def parse_coords(value: str, default: tuple[int, int] = (0, 0)) -> tuple[int, int]:
    """Parse a string of the format 'x,y' into a tuple of integers."""
    try:
        parts = value.split(",")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return default


def format_coords(x: int, y: int) -> str:
    """Format coordinates as a string 'x,y'."""
    return f"{int(x)},{int(y)}"


def config_to_metrics(config: ConfigParser, section: str) -> WindowMetrics:
    """Convert a config section to WindowMetrics."""
    x, y = parse_coords(config.get(section, "position", fallback="0,0"))
    w, h = parse_coords(config.get(section, "size", fallback="0,0"))
    return WindowMetrics(x, y, w, h,
                         config.getboolean(section, "always_on_top", fallback=False),
                         config.getboolean(section, "titlebar", fallback=True),
                         config.get(section, "apply_order", fallback=""),
                         )


def get_version() -> str | None:
    """Read the application version from version.txt file."""
    try:
        # noinspection SpellCheckingInspection
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

