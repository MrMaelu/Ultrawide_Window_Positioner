"""Window management for Ultrawide Window Positioner."""
import logging
import time
from ast import literal_eval

import psutil
import win32api
import win32con
import win32gui
import win32process

# Local imports
from utils import WindowInfo, clean_window_title, match_titles

logger = logging.getLogger(__name__)

MIN_W = 250
MIN_H = 250

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

        self.default_apply_order = ["titlebar",
                                    "pos",
                                    "size",
                                    "aot",
                                    ]

    def apply_window_config(self, config:dict, hwnd:int)-> bool:
        """Apply a configuration to a specific window."""
        if self.is_valid_window(hwnd) and config:
            self.add_managed_window(hwnd)
            self.bring_to_front(hwnd)

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
                "titlebar": (self.enable_titlebar, has_titlebar),
                "pos": (self.set_window_position, position[0], position[1]),
                "size": (self.set_window_size, size[0], size[1]),
            }

            apply_order_str = config.get("apply_order") or ""

            apply_order = (
                apply_order_str.split(",")
                if apply_order_str else self.default_apply_order
                )

            for raw_key in apply_order:
                key = raw_key.strip().lower()
                args = apply_funcs[key][1:]
                if args:
                    apply_funcs[key][0](hwnd, *args)
                time.sleep(0.1)
                self.set_priority(hwnd, enable=process_priority)

            return True

        return False


# Apply window config helper functions

    def set_always_on_top(self, hwnd:int, enable:int)->None:
        """Set the AOT state for a window."""
        if self.is_valid_window(hwnd):
            flag = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
            win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE |
                                    win32con.SWP_NOSIZE |
                                    win32con.SWP_NOOWNERZORDER,
                                    )

            if enable and hwnd not in self.topmost_windows:
                self.topmost_windows.add(hwnd)
            elif not enable and hwnd in self.topmost_windows:
                self.topmost_windows.remove(hwnd)
            return True

        return False


    def set_window_position(self, hwnd:int, x:int, y:int)->bool:
        """Set the position of the window."""
        if self.is_valid_window(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                                win32con.SWP_NOZORDER | win32con.SWP_NOSIZE)
            return True

        return False


    def set_window_size(self, hwnd:int, width:int, height:int)->bool:
        """Set the size of the window."""
        if self.is_valid_window(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0], rect[1]

            win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                                win32con.SWP_NOZORDER | win32con.SWP_NOMOVE)
            return True

        return False


    def enable_titlebar(self, hwnd:int, enable:int=1)->bool:
        """Enable or disable the titlebar for a window."""
        if enable:
            return self.restore_window_frame(hwnd)
        if self.is_valid_window(hwnd):
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


    def set_priority(self, hwnd:int, *, enable:bool)->bool:
        """Set the process priority for a window."""
        if self.is_valid_window(hwnd) and enable:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            p = psutil.Process(pid)
            p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
            return True

        return False


    def add_managed_window(self, hwnd:int)->bool:
        """Add a window to the managed windows list."""
        if hwnd not in self.managed_windows:
            self.managed_windows.append(hwnd)
            # Store initial window state
            self._window_states[hwnd] = self.get_window_metrics(hwnd)
            aot_status = self._window_states[hwnd]["exstyle"] \
                & win32con.WS_EX_TOPMOST
            titlebar_status = self._window_states[hwnd]["style"] \
                & win32con.WS_CAPTION
            logger.info("Added managed window: %s", hwnd)
            logger.info(
                "Initial state for hwnd %s: %s", hwnd, self._window_states[hwnd],
                )
            logger.info(
                "Initial AOT state hwnd %s: %s", hwnd,
                "Yes" if aot_status else "No",
                )
            logger.info(
                "Initial titlebar state hwnd %s: %s\n", hwnd,
                "Yes" if titlebar_status else "No",
                )
            return True

        return False


    def remove_managed_window(self, hwnd:int)->bool:
        """Remove a window from the managed windows list."""
        if hwnd in self.managed_windows:
            if hwnd in self._window_states:
                original_state = self._window_states[hwnd]
                pos_x, pos_y = original_state["position"]
                size_w, size_h = original_state["size"]

                self.set_window_position(hwnd, pos_x, pos_y)
                logger.info(
                    "Restored position for hwnd %s: (%s, %s)", hwnd, pos_x, pos_y,
                    )

                if size_w > MIN_W and size_h > MIN_H:
                    self.set_window_size(hwnd,size_w, size_h)
                    logger.info(
                        "Restored size for hwnd %s: (%s, %s)", hwnd, size_w, size_h,
                        )
                else:
                    logger.info(
                        "Original size for hwnd %s is below minimum,"
                        "skipping size restore: (%s, %s)",
                        hwnd, size_w, size_h,
                        )

                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE,
                                        original_state["style"])
                logger.info(
                    "Restored style for hwnd %s: %s", hwnd, original_state["style"],
                    )

                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                        original_state["exstyle"])
                logger.info(
                    "Restored exstyle for hwnd %s: %s\n", hwnd,
                    original_state["exstyle"],
                    )

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
            self.restore_window_frame(hwnd)

        logger.info("All windows reset to original state.")
        logger.info("Current managed windows after reset: %s", self.managed_windows)
        logger.info("Current topmost windows after reset: %s", self.topmost_windows)
        logger.info("Current window states after reset: %s\n", self._window_states)


    def remove_invalid_windows(self)->None:
        """Remove windows that no longer exist from the managed windows list."""
        for hwnd in self.managed_windows.copy():
            if not self.is_valid_window(hwnd):
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


    def get_window_metrics(self, hwnd:int)->dict:
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


    def restore_window_frame(self, hwnd:int)->bool:
        """Restore the titlebar and window frame for a window."""
        if self.is_valid_window(hwnd):
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


    def remove_ignored_windows(self, config: dict, all_titles:list)->bool:
        """Check if a title is in the ignore list."""
        clenaned_titles = {}
        for title in all_titles:
            tc = clean_window_title(title, sanitize=True)
            clenaned_titles[tc] = title

        config_titles = config.sections()
        for title in config_titles:
            if config[title].get("ignore_list"):
                ignore_list = config[title].get("ignore_list").split(",")
                for item in match_titles(
                    ignore_list,
                    clenaned_titles.keys(),
                    get_titles=True,
                    ):
                    clenaned_titles.pop(item, None)

        return list(clenaned_titles.values())


    def find_matching_windows(self, config: dict) -> tuple[list[dict], list[str]]:
        """Check which windows in the config exist and which don't."""
        matching_windows = []
        missing_windows = []

        if not config or len(config.sections()) == 0:
            return matching_windows, missing_windows

        all_titles = self.get_all_window_titles()
        valid_titles = self.remove_ignored_windows(config, all_titles)

        titles_matches = match_titles(config.sections(), valid_titles, get_titles=True)
        missing_windows = list(set(config.sections()) - set(titles_matches.keys()))

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


    def toggle_always_on_top(self, hwnd:int)->None:
        """Toggle AOT status for current config."""
        if hwnd in self.topmost_windows:
            is_topmost = (
                win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                & win32con.WS_EX_TOPMOST
                ) != 0
            flag = (
                win32con.HWND_TOPMOST
                if not is_topmost
                else win32con.HWND_NOTOPMOST
                )
            win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE |
                                    win32con.SWP_NOSIZE |
                                    win32con.SWP_NOOWNERZORDER)


    def get_all_window_titles(self, own_hwnd:int | None=None)->list:
        """Get the title from all existing windows."""
        def enum_window_callback(hwnd:int, windows:list)->bool:
            if win32gui.IsWindowVisible(hwnd) and hwnd != own_hwnd:
                title = win32gui.GetWindowText(hwnd)
                if title and title.lower() not in self.ignored_windows:
                    windows.append(title)
            return True

        windows = []
        win32gui.EnumWindows(enum_window_callback, windows)
        return sorted(windows)


    def is_valid_window(self, hwnd:int)->bool:
        """Check if a hwnd is a valid window."""
        return win32gui.IsWindow(hwnd) != 0


    def bring_to_front(self, hwnd:int)->None:
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
            self,
            config:dict,
            missing_windows:list,
            )->list[WindowInfo]:
        """Get the windows from the config to use for drawing the layout preview."""
        positioned_windows = []

        if config:
            for section in config.sections():
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

