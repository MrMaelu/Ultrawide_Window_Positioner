"""Window management for Ultrawide Window Positioner."""
import logging
import time
from ast import literal_eval
from pathlib import Path

import mss
import psutil
import win32api
import win32con
import win32gui
import win32process
from PIL import Image

# Local imports
from utils import WindowInfo, clean_window_title, match_titles

logger = logging.getLogger(__name__)

MIN_W = 250
MIN_H = 250
IGNORED_WINDOWS = {
    "ultrawide window positioner",
    "program manager",
    "windows input experience",
    "microsoft text input application",
    "settings",
    "windows shell experience host",
}


def capture_window(hwnd:int, window_name:str, assets_dir:Path) -> None:
    """Take a screenshot of the window."""
    time.sleep(0.1)
    save_path = Path(assets_dir / f"{window_name}.png")
    compression = (2048, 2048)
    with mss.mss() as sct:
        rect = win32gui.GetWindowRect(hwnd)
        bbox = {"top": rect[1], "left": rect[0], "width": rect[2] - rect[0], "height": rect[3] - rect[1]}
        sct_img = sct.grab(bbox)
        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
        img.thumbnail(compression)
        img.save(save_path)

def get_all_window_titles(own_hwnd: int | None=None)->dict:
    """Get the title from all existing windows."""
    def enum_window_callback(hwnd:int, windows:list)->bool:
        if win32gui.IsWindowVisible(hwnd) and hwnd != own_hwnd:
            title = win32gui.GetWindowText(hwnd)
            if title and title.lower() not in IGNORED_WINDOWS:
                windows.append(title)
                hwnds.append(hwnd)
        return True

    window_titles = []
    hwnds = []
    win32gui.EnumWindows(enum_window_callback, window_titles)
    return dict(zip(window_titles, hwnds))

def is_valid_window(hwnd:int)->bool:
    """Check if a hwnd is a valid window."""
    return win32gui.IsWindow(hwnd) != 0

def bring_to_front(hwnd:int)->None:
    """Set a window to the front, not AOT."""
    if not win32gui.IsWindow(hwnd):
        return
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
    )
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_NOTOPMOST,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
    )

def get_windows_for_layout(
        config:dict,
        missing_windows:list,
        )->list[WindowInfo]:
    """Get the windows from the config to use for drawing the layout preview."""
    positioned_windows = []

    if config:
        for section in config:
            pos = config[section].get("position")
            size = config[section].get("size")
            aot=config[section].get("always_on_top", "false").lower() == "true"
            title=config[section].get("search_title") or section
            source_url=config[section].get("source_url", "")
            source=config[section].get("source", "")

            if pos and size:
                pos_x, pos_y = map(int, pos.split(","))
                size_w, size_h = map(int, size.split(","))
                positioned_windows.append(
                    WindowInfo(
                        name=section,
                        pos_x=pos_x,
                        pos_y=pos_y,
                        width=size_w,
                        height=size_h,
                        always_on_top=aot,
                        exists=section not in missing_windows,
                        search_title=title,
                        source_url=source_url,
                        source=source,
                    ),
                )
    else:
        # Create dummy window
        positioned_windows.append(
            WindowInfo(
                "",
                -1000, -1000,
                0, 0,
                always_on_top=False,
                exists=True,
                search_title="",
                source_url="",
                source="",
            ),
        )

    return positioned_windows


def find_matching_windows(sections: list, ignore: list) -> tuple[list[dict], list[str]]:
    """Check which windows in the config exist and which don't."""
    if not sections or len(sections) == 0:
        return [], []

    matching_windows = []

    all_titles = get_all_window_titles()

    valid_titles = {}
    for title in all_titles:
        tc = clean_window_title(title, sanitize=True)
        valid_titles[tc] = title

    if ignore:
        for _ in sections:
            titles = match_titles(ignore, list(valid_titles.keys()), get_titles=True)
            for item in titles:
                valid_titles.pop(item, None)

    titles_matches = match_titles(sections, list(valid_titles.values()), get_titles=True)
    missing_windows = list(set(sections) - set(titles_matches.keys()))

    if titles_matches:
        for title in titles_matches:
            hwnd = win32gui.FindWindow(None, titles_matches[title])
            if hwnd:
                matching_windows.append({
                    "config_name": title,
                    "hwnd": hwnd,
                })
            else:
                missing_windows.append(title)
    return matching_windows, missing_windows

def restore_window_frame(hwnd:int)->bool:
    """Restore the titlebar and window frame for a window."""
    if is_valid_window(hwnd):
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style |= (win32con.WS_CAPTION |
                    win32con.WS_BORDER |
                    win32con.WS_THICKFRAME)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                            win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW)
        return True

    return False

def get_hwnd_from_title(search_title:str)-> int | None:
    all_window_titles = get_all_window_titles()
    for title, hwnd in all_window_titles.items():
        if title == search_title:
            return hwnd
    return None

def get_window_metrics(hwnd:int)-> dict | None:
    """Get the window metrics from the selected window."""
    rect = win32gui.GetWindowRect(hwnd)
    metrics = {
        "position": (rect[0], rect[1]),
        "size": (rect[2] - rect[0], rect[3] - rect[1]),
        "style": win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE),
        "exstyle": win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE),
    }

    if metrics["size"][0] < MIN_W or metrics["size"][1] < MIN_H:
        logger.warning(
            "Window size for hwnd %s is below minimum: %s. "
            "Value considered unreliable, metrics ignored.",
            hwnd, metrics["size"],
            )
        return None

    return metrics

def collect_window_settings(title:str)-> dict | None:
    hwnd = get_hwnd_from_title(title)
    if hwnd is None:
        return None

    rect = win32gui.GetWindowRect(hwnd)
    has_titlebar = bool(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) & win32con.WS_CAPTION)
    is_topmost = hwnd == win32gui.GetForegroundWindow()

    return {
        "position": f"{max(-50, rect[0] + 50)},{max(-50, rect[1] + 50)}",
        "size": f"{max(250, rect[2] - rect[0])},{max(250, rect[3] - rect[1])}",
        "always_on_top": str(is_topmost).lower(),
        "titlebar": str(has_titlebar).lower(),
        "original_title": title,
        "name": clean_window_title(title, sanitize=True),
    }

def set_priority(hwnd:int, *, enable:bool)->bool:
    """Set the process priority for a window."""
    if is_valid_window(hwnd) and enable:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        p = psutil.Process(pid)
        p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        return True

    return False

def enable_titlebar(hwnd:int, enable:int=1)->bool:
    """Enable or disable the titlebar for a window."""
    if enable:
        return restore_window_frame(hwnd)
    if is_valid_window(hwnd):
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~(win32con.WS_CAPTION |
                    win32con.WS_BORDER |
                    win32con.WS_THICKFRAME)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                            win32con.SWP_FRAMECHANGED)
        return True

    return False

def set_window_size(hwnd:int, width:int, height:int)->bool:
    """Set the size of the window."""
    if is_valid_window(hwnd):
        rect = win32gui.GetWindowRect(hwnd)
        x, y = rect[0], rect[1]

        win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                            win32con.SWP_NOZORDER | win32con.SWP_NOMOVE)
        return True

    return False

def set_window_position(hwnd:int, x:int, y:int)->bool:
    """Set the position of the window."""
    if is_valid_window(hwnd):
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]

        win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                            win32con.SWP_NOZORDER | win32con.SWP_NOSIZE)
        return True

    return False


class WindowManager:
    """Handle application windows and states."""

    def __init__(self)->None:
        """Initialize variables and state."""
        self.managed_windows = []
        self.topmost_windows = set()
        self._window_states = {}
        self.ignored_windows = {
            "ultrawide window positioner",
            "program manager",
            "windows input experience",
            "microsoft text input application",
            "settings",
            "windows shell experience host",
        }

        self.default_apply_order = ["titlebar", "pos", "size", "aot"]

    def apply_window_config(self, config:dict, hwnd:int)-> bool:
        """Apply a configuration to a specific window."""
        if is_valid_window(hwnd) and config:
            self.add_managed_window(hwnd)
            bring_to_front(hwnd)

            # Get configuration values
            has_titlebar = config.get("has_titlebar", True)

            size = (
                literal_eval(config["size"])
                if isinstance(config["size"], str)
                else config["size"]
                ) or (100, 100)

            position = (
                literal_eval(config["position"])
                if isinstance(config["position"], str)
                else config["position"]
                )

            if not position:
                scr_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                scr_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                position = ((scr_w - size[0]) // 2, (scr_h - size[1]) // 2)

            always_on_top = config.get("always_on_top", False)
            process_priority = config.get("process_priority", False)

            # Apply settings
            apply_funcs = {
                "aot": (self.set_always_on_top, always_on_top),
                "titlebar": (enable_titlebar, has_titlebar),
                "pos": (set_window_position, position[0], position[1]),
                "size": (set_window_size, size[0], size[1]),
            }

            apply_order_str = config.get("apply_order") or self.default_apply_order
            if apply_order_str:
                apply_order =  apply_order_str.split(",")

                for raw_key in apply_order:
                    key = raw_key.strip().lower()
                    args = apply_funcs[key][1:]
                    if args:
                        apply_funcs[key][0](hwnd, *args)
                    time.sleep(0.1)
                    set_priority(hwnd, enable=process_priority)
            else:
                self.set_win32gui_params(hwnd, always_on_top, has_titlebar, position, size)

            return True

        return False


# Apply window config helper functions

    def set_win32gui_params(self, hwnd: int, aot: bool, titlebar: bool, pos: tuple, size: tuple)-> None:
        if is_valid_window(hwnd):
            flag = win32con.HWND_TOPMOST if aot else win32con.HWND_NOTOPMOST
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

            if titlebar:
                style &= ~(win32con.WS_CAPTION | win32con.WS_BORDER | win32con.WS_THICKFRAME)

            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
            win32gui.SetWindowPos(hwnd, flag, pos[0], pos[1], size[0], size[1], win32con.SWP_FRAMECHANGED)

            if aot and hwnd not in self.topmost_windows:
                self.topmost_windows.add(hwnd)
            elif not aot and hwnd in self.topmost_windows:
                self.topmost_windows.remove(hwnd)

    def set_always_on_top(self, hwnd:int, enable:int)->bool:
        """Set the AOT state for a window."""
        if is_valid_window(hwnd):
            flag = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
            win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOOWNERZORDER)

            if enable and hwnd not in self.topmost_windows:
                self.topmost_windows.add(hwnd)
            elif not enable and hwnd in self.topmost_windows:
                self.topmost_windows.remove(hwnd)
            return True

        return False

    def add_managed_window(self, hwnd:int)->bool:
        """Add a window to the managed windows list."""
        if hwnd not in self.managed_windows:
            self.managed_windows.append(hwnd)

            # Store initial window state
            self._window_states[hwnd] = get_window_metrics(hwnd)

            aot_status = self._window_states[hwnd]["exstyle"] & win32con.WS_EX_TOPMOST
            titlebar_status = self._window_states[hwnd]["style"] & win32con.WS_CAPTION

            logger.info("Added managed window: %s", hwnd)
            logger.info("Initial state for hwnd %s: %s", hwnd, self._window_states[hwnd])
            logger.info("Initial AOT state hwnd %s: %s", hwnd, "Yes" if aot_status else "No")
            logger.info("Initial titlebar state hwnd %s: %s\n", hwnd, "Yes" if titlebar_status else "No")

            return True

        return False

    def remove_managed_window(self, hwnd:int)->bool:
        """Remove a window from the managed windows list."""
        if hwnd in self.managed_windows:
            if hwnd in self._window_states:
                original_state = self._window_states[hwnd]
                pos_x, pos_y = original_state["position"]
                size_w, size_h = original_state["size"]

                set_window_position(hwnd, pos_x, pos_y)
                logger.info("Restored position for hwnd %s: (%s, %s)", hwnd, pos_x, pos_y)

                if size_w > MIN_W and size_h > MIN_H:
                    set_window_size(hwnd,size_w, size_h)
                    logger.info("Restored size for hwnd %s: (%s, %s)", hwnd, size_w, size_h)
                else:
                    logger.info("Original size for hwnd %s is below minimum,"
                        "skipping size restore: (%s, %s)", hwnd, size_w, size_h)

                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, original_state["style"])
                logger.info("Restored style for hwnd %s: %s", hwnd, original_state["style"])

                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, original_state["exstyle"])
                logger.info("Restored exstyle for hwnd %s: %s\n", hwnd, original_state["exstyle"])

                del self._window_states[hwnd]

            self.managed_windows.remove(hwnd)
            if hwnd in self.topmost_windows:
                self.topmost_windows.remove(hwnd)

            return True

        return False

    def reset_all_windows(self)->None:
        """Reset all windows to the original state."""
        windows_to_reset = self.managed_windows.copy()
        for hwnd in windows_to_reset:
            self.remove_managed_window(hwnd)
            self.set_always_on_top(hwnd, enable=False)
            restore_window_frame(hwnd)

        logger.info("All windows reset to original state.")
        logger.info("Current managed windows after reset: %s", self.managed_windows)
        logger.info("Current topmost windows after reset: %s", self.topmost_windows)
        logger.info("Current window states after reset: %s\n", self._window_states)

    def remove_invalid_windows(self)->None:
        """Remove windows that no longer exist from the managed windows list."""
        for hwnd in self.managed_windows.copy():
            if not is_valid_window(hwnd):
                self.managed_windows.remove(hwnd)
                logger.info("Removed invalid window: %s", hwnd)
                logger.info("Current managed windows: %s", self.managed_windows)
                if hwnd in self.topmost_windows:
                    self.topmost_windows.remove(hwnd)

# Other functions

    def get_always_on_top_status(self)->str:
        """Get the current amount of windows with AOT active."""
        count = 0
        if len(self.topmost_windows) == 0:
            return "AOT: None"
        for hwnd in self.topmost_windows:
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if (ex_style & win32con.WS_EX_TOPMOST) != 0:
                count += 1

        return f"AOT: {count} window{'s' if count > 1 else ''}"

    def toggle_always_on_top(self, hwnd:int)->None:
        """Toggle AOT status for current config."""
        if hwnd in self.topmost_windows:
            is_topmost = (win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST) != 0
            flag = win32con.HWND_TOPMOST if not is_topmost else win32con.HWND_NOTOPMOST
            win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOOWNERZORDER)

