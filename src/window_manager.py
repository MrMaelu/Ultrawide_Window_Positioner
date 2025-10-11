"""Window management for Ultrawide Window Positioner."""
import logging
import time
from ast import literal_eval

import psutil
import win32con
import win32gui
import win32process

# Local imports
from utils import WindowInfo, clean_window_title

logger = logging.getLogger(__name__)

class WindowManager:
    """Handle application windows and states."""

    def __init__(self)->None:
        """Initialize variables."""
        self.managed_windows = []
        self.topmost_windows = set()
        self._window_states = {}
        self.ignored_windows = [
            "ultrawide window positioner",
            "program manager",
            "windows input experience",
            "microsoft text input application",
            "settings",
            "windows shell experience host",
        ]
        self.default_apply_order = ["titlebar",
                                    "pos",
                                    "size",
                                    "aot",
                                    ]

    def apply_window_config(self, config:dict, hwnd:int)->bool:
        """Apply a configuration to a specific window."""
        if self.is_valid_window(hwnd) and config:
            try:
                self.add_managed_window(hwnd)

                self.bring_to_front(hwnd)

                if isinstance(config, dict):
                    # Get configuration values
                    has_titlebar = config.get("has_titlebar", True)
                    if config.get("position"):
                        position = (
                            literal_eval(config["position"])
                            if isinstance(config["position"], str)
                            else config["position"]
                            )
                    if config.get("size"):
                        size = (
                            literal_eval(config["size"])
                            if isinstance(config["size"], str)
                            else config["size"]
                            )

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

            except win32gui.error:
                pass
            else:
                return True
        return False


# Apply window config helper functions

    def set_always_on_top(self, hwnd:int, enable:int)->None:
        """Set the AOT state for a window."""
        if self.is_valid_window(hwnd):
            try:
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

            except Exception:
                logger.exception("Failed to set always on top status.")


    def set_window_position(self, hwnd:int, x:int, y:int)->bool:
        """Set the position of the window."""
        if self.is_valid_window(hwnd):
            try:
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]

                win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                                    win32con.SWP_NOZORDER | win32con.SWP_NOSIZE)

            except Exception:
                logger.exception("Error setting window position for %s", hwnd)
            else:
                return True
        return False


    def set_window_size(self, hwnd:int, width:int, height:int)->bool:
        """Set the size of the window."""
        if self.is_valid_window(hwnd):
            try:
                rect = win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]

                win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                                    win32con.SWP_NOZORDER | win32con.SWP_NOMOVE)

            except Exception:
                logger.exception("Error setting window size for %s", hwnd)
            else:
                return True
        return False


    def enable_titlebar(self, hwnd:int, enable:int=1)->bool:
        """Enable or disable the titlebar for a window."""
        if enable:
            return self.restore_window_frame(hwnd)
        if self.is_valid_window(hwnd):
            try:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style &= ~(win32con.WS_CAPTION |
                           win32con.WS_BORDER |
                           win32con.WS_THICKFRAME)
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                                    win32con.SWP_FRAMECHANGED)

            except Exception:
                logger.exception("Error making window borderless for hwnd: %s", hwnd)
            else:
                return True
        return False


    def set_priority(self, hwnd:int, *, enable:bool)->None:
        """Set the process priority for a window."""
        if self.is_valid_window(hwnd) and enable:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                p = psutil.Process(pid)
                p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
            except Exception as e:
                logger.exception("Error setting process priority for hwnd: %s", hwnd)


    def add_managed_window(self, hwnd:int)->None:
        """Add a window to the managed windows list."""
        try:
            if hwnd not in self.managed_windows:
                self.managed_windows.append(hwnd)
                # Store initial window state
                self._window_states[hwnd] = self.get_window_metrics(hwnd)
        except Exception:
            logger.exception("Error adding managed window %s", hwnd)


    def remove_managed_window(self, hwnd:int)->None:
        """Remove a window from the managed windows list."""
        try:
            if hwnd in self.managed_windows:
                if hwnd in self._window_states:
                    original_state = self._window_states[hwnd]
                    self.set_window_position(hwnd,
                                          original_state["position"][0],
                                          original_state["position"][1])
                    self.set_window_size(hwnd,
                                       original_state["size"][0],
                                       original_state["size"][1])

                    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE,
                                         original_state["style"])
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                         original_state["exstyle"])

                    del self._window_states[hwnd]

                self.managed_windows.remove(hwnd)
                if hwnd in self.topmost_windows:
                    self.topmost_windows.remove(hwnd)

        except Exception:
            logger.exception("Error removing managed window %s", hwnd)


    def reset_all_windows(self)->None:
        """Reset all windows to the original state."""
        windows_to_reset = self.managed_windows.copy()
        for hwnd in windows_to_reset:
            self.set_always_on_top(hwnd, enable=False)
            self.restore_window_frame(hwnd)
            self.remove_managed_window(hwnd)




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


    def get_window_title(self, hwnd:int)->str:
        """"Get the title from a window."""
        try:
            return win32gui.GetWindowText(hwnd)
        except Exception:
            logger.exception("Error getting window title for %s", hwnd)
            return ""


    def get_window_metrics(self, hwnd:int)->dict:
        """Get the window metrics from the selected window."""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            return {
                "position": (rect[0], rect[1]),
                "size": (rect[2] - rect[0], rect[3] - rect[1]),
                "style": win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE),
                "exstyle": win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE),
            }
        except Exception:
            logger.exception("Error getting window metrics:")
            return None


    def restore_window_frame(self, hwnd:int)->bool:
        """Restore the titlebar and window frame for a window."""
        if self.is_valid_window(hwnd):
            try:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style |= (win32con.WS_CAPTION |
                          win32con.WS_BORDER |
                          win32con.WS_THICKFRAME)
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                                    win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW)

            except Exception:
                logger.exception("Error restoring window frame for hwnd: %s", hwnd)
            else:
                return True
        return False


    def find_matching_windows(self, config: dict) -> tuple[list[dict], list[str]]:
        """Check which windows in the config exist and which don't."""
        matching_windows = []
        missing_windows = []

        if not config or len(config.sections()) == 0:
            return matching_windows, missing_windows

        all_titles = self.get_all_window_titles()

        for section in config.sections():
            cleaned_section = clean_window_title(section, sanitize=True)
            hwnd = None

            for title in all_titles:
                if cleaned_section in clean_window_title(title, sanitize=True):
                    hwnd = win32gui.FindWindow(None, title)
                    break

            if hwnd:
                matching_windows.append({
                    "config_name": section,
                    "hwnd": hwnd,
                })
            else:
                missing_windows.append(section)

        return matching_windows, missing_windows


    def toggle_always_on_top(self, hwnd:int)->None:
        """Toggle AOT status for current config."""
        try:
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

        except Exception:
            logger.exception("Error toggling always-on-top:")


    def get_all_window_titles(self)->list:
        """Get the title from all existing windows."""
        try:
            def enum_window_callback(hwnd:int, windows:list)->bool:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title and title.lower() not in self.ignored_windows:
                        windows.append(title)
                return True

            windows = []
            win32gui.EnumWindows(enum_window_callback, windows)
            return sorted(windows)
        except Exception:
            logger.exception("Error getting window titles:")
        return []


    def is_valid_window(self, hwnd:int)->bool:
        """Check if a hwnd is a valid window."""
        try:
            return win32gui.IsWindow(hwnd) != 0
        except win32gui.error:
            return False


    def bring_to_front(self, hwnd:int)->None:
        """Set a window to the front, not AOT."""
        try:
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
        except Exception:
            logger.exception("Failed to bring window to front:")


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






