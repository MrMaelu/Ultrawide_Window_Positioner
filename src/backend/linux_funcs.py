"""Collection of utilities for Ultrawide Window Positioner."""

import logging
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil

from backend.common import WindowsWindow, clean_window_title, get_binary_path

logger = logging.getLogger(__name__)

@dataclass
class KWinWindow:  # noqa: D101
    uuid: str
    caption: str
    resourceclass: str
    resourcename: str
    desktopfile: str
    width: int
    height: int
    x: float
    y: float
    noborder: bool
    keepabove: bool
    keepbelow: bool
    fullscreen: bool
    maximizehorizontal: int
    maximizevertical: int
    minimized: bool


def _kwin_windows_window(window: KWinWindow, pid: int) -> WindowsWindow:
    """Convert KWinWindow to WindowsWindow."""
    proc = psutil.Process(pid)
    app_name = proc.name()
    app_path = proc.exe()
    return WindowsWindow(
        window.uuid,
        pid,
        window.caption,
        app_name,
        app_path,
        window.width,
        window.height,
        window.x,
        window.y,
        not window.noborder,
        window.keepabove,
    )


def _run_kdotool(cmd: list, win_id: str = "", *args: str) -> str | bool:
    """Run a kdotool command."""
    kdotool_bin = get_binary_path("kdotool")
    command = [kdotool_bin, *cmd]
    output = ""
    if win_id:
        win_id = str(win_id).strip("{}")
        command += ["{" + win_id + "}"]
    if args:
        command += args
    retries = 5
    while retries > 0:
        try:
            return run_clean_subprocess(command, check_output=True).decode().strip()
        except FileNotFoundError as e:
            logger.info("kdotool not found: %s", e)
            return False
        except subprocess.CalledProcessError as e:
            logger.info("kdotool subprocess error: %s", e)
            time.sleep(0.2)
            retries -= 1

    return output


def _to_dataclass(b_data: bytes) -> KWinWindow | bool:
    """Convert KWin data to KWinWindow object."""
    d = _parse_kwin_data(b_data)
    if not d.get("caption", False):
        return False
    try:
        dc = KWinWindow(**{k: v for k, v in d.items() if k in KWinWindow.__annotations__})
    except TypeError as e:
        logger.info("TypeError when converting to KwinWindow: %s", e)
        return False
    return dc


def _parse_kwin_data(b_data: bytes) -> dict:
    """Parse KWin data into a dictionary."""
    lines = b_data.decode("utf-8").strip().split("\n")

    result = {}
    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.replace(".", "", 1).isdigit():
                value = float(value) if "." in value else int(value)
            else:
                value = value.lower()

            result[key.lower()] = value
    return result


def is_valid_window(win_id: str) -> bool:
    """Check if a win_id is a valid window."""
    title = _run_kdotool(["getwindowname"], win_id)
    return bool(title)


def _validate_win_id(func: Callable) -> Callable[..., bool]:
    """Validate a win_id."""
    def wrapper(win_id: str, *args: tuple, **kwargs: dict) -> bool:
        if not is_valid_window(win_id):
            logger.warning("Can't %s for invalid window: %s", func.__name__,win_id)
            return False
        return func(win_id, *args, **kwargs)
    return wrapper


def run_clean_subprocess(command: list[str],
                         *,
                         check_output: bool = False,
                         **kwargs: str | bool,
                         ) -> subprocess.CompletedProcess | bytes:
    """Run subprocess with local env."""
    env = dict(os.environ)
    for key in ["LD_LIBRARY_PATH", "LIBGL_DRIVERS_PATH", "QT_PLUGIN_PATH"]:
        env.pop(key, None)

        if not check_output:
            kwargs.setdefault("stdout", subprocess.DEVNULL)
            kwargs.setdefault("stderr", subprocess.DEVNULL)

        if check_output:
            return subprocess.check_output(command, env=env, **kwargs)  # noqa: S603
    return subprocess.run(command, env=env, **kwargs)  # noqa: S603


@_validate_win_id
def get_screenshot(win_id: str, path: Path) -> None:
    """Take a screenshot of the window."""
    _run_kdotool(["windowactivate"], win_id)
    try:
        run_clean_subprocess(["spectacle", "-w", "-a", "-b", "-n", "-o", path])

    except subprocess.CalledProcessError as e:
        logger.info("Spectacle failed: %s", e)


def get_aot_toggle(*args)->None:
    """Not used on Linux, placeholder for compatibility."""
    return


def get_app_window_title()->str:  # noqa: D103
    return "Ultrawide Window Positioner"


@_validate_win_id
def get_window_info(win_id: str) -> WindowsWindow | None:
    """Get information about a window."""
    clean_uuid = win_id.strip("{}").lower()
    info_cmd = ["qdbus-qt6", "org.kde.KWin", "/KWin", "org.kde.KWin.getWindowInfo", clean_uuid]
    win_info = run_clean_subprocess(info_cmd, check_output=True)
    win_info_dataclass = _to_dataclass(win_info)
    if win_info_dataclass:
        pid = _run_kdotool(["getwindowpid", win_id])
        if pid:
            return _kwin_windows_window(win_info_dataclass, int(pid))

    return None


def get_all_windows(own_win_id: str | None = None, ignored_windows: list | None = None) -> dict:
    """Get the title from all existing windows."""
    win_ids = _run_kdotool(["search", "."])
    if not win_ids:
        return {}

    win_ids = win_ids.split("\n")

    window_titles = []
    info = []
    max_length = 100
    for win_id in win_ids:
        if win_id != own_win_id:
            win_info = get_window_info(win_id)
            if not win_info:
                continue

            title = clean_window_title(win_info.title, titlecase=True)[0]
            x = re.search(r"(.+)v\d+", title, re.IGNORECASE)
            if x:
                title = x.group(1).strip()

            if title.lower() not in ignored_windows:
                title = win_info.app_name.split(".")[0] if len(win_info.title) > max_length else title

                window_titles.append(clean_window_title(title)[0])
                info.append(win_info)

    return dict(zip(window_titles, info, strict=False))


@_validate_win_id
def set_aot(win_id: str, enable: bool = True) -> None:  # noqa: D103, FBT001, FBT002
    mode = "--add" if enable else "--remove"
    _run_kdotool(["windowstate", mode, "ABOVE"], win_id)


@_validate_win_id
def set_window_frame(win_id: str, enable: bool = True) -> str | bool:  # noqa: FBT001, FBT002
    """Restore the titlebar and window frame for a window."""
    mode = "--remove" if enable else "--add"
    return _run_kdotool(["windowstate", mode, "NO_BORDER"], win_id)


@_validate_win_id
def set_size(win_id: str, win_info: WindowsWindow, width: int, height: int) -> None:  # noqa: D103
    _run_kdotool(["windowsize"], win_id, str(width), str(height))


@_validate_win_id
def set_position(win_id: str, win_info: WindowsWindow, x: int, y: int) -> None:  # noqa: D103
    _run_kdotool(["windowmove"], win_id, str(x), str(y))


def bring_to_front(win_id: str, is_self: bool = False) -> None:
    """Set a window to the front, not AOT."""
    if is_self:
        pid = os.getpid()
        cmd = ["search", "--pid", str(pid), "--all"]
        win_id = _run_kdotool(cmd)
    if is_valid_window(win_id):
        _run_kdotool(["windowraise"], win_id)
    else:
        logger.warning("Can't %s for invalid window: %s", "bring_to_front", win_id)
