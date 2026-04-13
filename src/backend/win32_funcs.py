"""Platform specific backend for Ultrawide Window Positioner on Windows."""
import logging
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import global_hotkeys
import hdrcapture
import psutil
import win32api
import win32gui
import win32process
from win32con import (
    GWL_EXSTYLE,
    GWL_STYLE,
    HWND_NOTOPMOST,
    HWND_TOPMOST,
    SW_RESTORE,
    SWP_FRAMECHANGED,
    SWP_NOMOVE,
    SWP_NOOWNERZORDER,
    SWP_NOSIZE,
    SWP_NOZORDER,
    SWP_SHOWWINDOW,
    WS_BORDER,
    WS_CAPTION,
    WS_EX_TOPMOST,
    WS_THICKFRAME,
)

from backend.common import WindowsWindow, clean_window_title

logger = logging.getLogger(__name__)

def is_valid_window(hwnd: int) -> bool:
    """Check if a hwnd is a valid window."""
    return win32gui.IsWindow(hwnd) != 0


def _get_version() -> str | None:
    """Read the application version from version.txt file."""
    try:
        # noinspection SpellCheckingInspection
        if hasattr(__import__("sys"), "_MEIPASS"):
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


def _validate_hwnd(func: Callable) -> Callable[..., bool]:
    """Validate a hwnd."""
    def wrapper(hwnd: int, *args: tuple, **kwargs: dict) -> bool:
        if not is_valid_window(hwnd):
            logger.warning("Can't %s for invalid window: %s", func.__name__,hwnd)
            return False
        return func(hwnd, *args, **kwargs)
    return wrapper


def run_clean_subprocess(
        command: list[str], *,
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


@_validate_hwnd
def get_screenshot(hwnd: int, path: Path) -> None:
    """Take a screenshot of the window using hdrcapture."""
    with hdrcapture.capture.window(hwnd=hwnd) as cap:
        frame = cap.capture()
        frame.save(str(path))


def get_aot_toggle(hotkey: str, toggle_func: Callable) -> None:  # noqa: D103
    global_hotkeys.register_hotkey(hotkey, toggle_func, None)
    global_hotkeys.start_checking_hotkeys()


def get_app_window_title() -> str:
    """Get the window title, add version if available."""
    version = _get_version()
    if version:
        return f"Ultrawide Window Positioner v{version}"
    return "Ultrawide Window Positioner"


@_validate_hwnd
def get_window_info(hwnd: int) -> WindowsWindow | None:
    """Get information about a window."""
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return None

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    rect = win32gui.GetWindowRect(hwnd)
    style = win32gui.GetWindowLong(hwnd, GWL_STYLE)
    # noinspection SpellCheckingInspection
    exstyle = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)

    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    x = rect[0]
    y = rect[1]
    aot = exstyle & WS_EX_TOPMOST != 0
    titlebar = style & WS_CAPTION != 0

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


def get_all_windows(own_hwnd: int | None = None, ignored_windows: list | None = None) -> dict:
    """Get the title from all existing windows."""
    max_length = 50
    def enum_window_callback(hwnd: int, windows: list) -> bool:
        if win32gui.IsWindowVisible(hwnd) and hwnd != own_hwnd:
            win_info = get_window_info(hwnd)
            if not win_info:
                return True

            title = clean_window_title(win_info.title, titlecase=True)[0]
            x = re.search(r"(.+)v\d+", title, re.IGNORECASE)
            if x:
                title = x.group(1).strip()

            if title.lower() not in ignored_windows:
                title = win_info.app_name.split(".")[0] if len(win_info.title) > max_length else title

                windows.append(clean_window_title(title)[0])
                info.append(win_info)
        return True

    window_titles = []
    # noinspection SpellCheckingInspection
    info = []
    win32gui.EnumWindows(enum_window_callback, window_titles)
    return dict(zip(window_titles, info, strict=False))


@_validate_hwnd
def set_aot(hwnd: int, enable: bool = True) -> None:  # noqa: FBT001, FBT002
    """Set the window to always on top and add it to the topmost windows set."""
    flag = HWND_TOPMOST if enable else HWND_NOTOPMOST
    win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


@_validate_hwnd
def set_window_frame(hwnd: int, enable: bool = True) -> bool:  # noqa: FBT001, FBT002
    """Restore the titlebar and window frame for a window."""
    style = win32gui.GetWindowLong(hwnd, GWL_STYLE)
    style_changes = (WS_CAPTION | WS_BORDER | WS_THICKFRAME)
    if enable:
        style |= style_changes
    else:
        style &= ~style_changes

    win32gui.SetWindowLong(hwnd, GWL_STYLE, style)
    win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE |
                            SWP_FRAMECHANGED | SWP_SHOWWINDOW | SWP_NOOWNERZORDER)
    return True


@_validate_hwnd
def set_size(hwnd: int, win_info: WindowsWindow, width: int, height: int) -> None:  # noqa: D103
    x, y = int(win_info.x), int(win_info.y)
    win32gui.SetWindowPos(hwnd, 0, x, y, width, height, SWP_NOZORDER | SWP_NOMOVE)


@_validate_hwnd
def set_position(hwnd: int, win_info: WindowsWindow, x: int, y: int) -> None:  # noqa: D103
    width, height = win_info.width, win_info.height
    win32gui.SetWindowPos(hwnd, 0, x, y, width, height, SWP_NOZORDER | SWP_NOSIZE)


@_validate_hwnd
def bring_to_front(hwnd: int, is_self: bool = False) -> None:
    """Set a window to the front, not AOT."""
    win32gui.ShowWindow(hwnd, SW_RESTORE)
    win32gui.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    win32gui.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

