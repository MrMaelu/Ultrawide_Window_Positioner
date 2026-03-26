"""Window management for Ultrawide Window Positioner."""
import logging
import re
import threading
import time
from collections.abc import Callable
from configparser import ConfigParser
from dataclasses import dataclass

import win32gui
from win32con import (
    GWL_STYLE,
    HWND_NOTOPMOST,
    HWND_TOP,
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
    WS_THICKFRAME,
)

# Local imports
from uwp_utils import (
    WindowInfo,
    WindowMetrics,
    clean_window_title,
    config_to_metrics,
    get_window_info,
    match_titles,
    metrics_to_window_info,
    window_to_metrics,
)

logger = logging.getLogger(__name__)

MIN_W = 250
MIN_H = 250

@dataclass
class WindowCache:
    """TTL cache for windows."""

    def __init__(self, ttl: float = 1.0) -> None:
        """Initialize the cache."""
        self._data: dict | None = None
        self.timestamp: float = 0
        self.ttl = ttl
        self.lock = threading.Lock()

    def get(self, fetch_func: Callable[[], dict]) -> dict:
        """Get the cached data or fetch new data if cache is invalid."""
        with self.lock:
            if self._is_valid():
                return self._data
            self._data = fetch_func()
            self.timestamp = time.time()
            return self._data

    def invalidate(self) -> None:
        """Invalidate the cache to force a refresh."""
        with self.lock:
            self._data = None
            self.timestamp = 0

    def _is_valid(self) -> bool:
        """Check if the cache is still fresh."""
        return self._data is not None and (time.time() - self.timestamp) < self.ttl


class WindowManager:
    """Handle application windows and states."""

    def __init__(self)->None:
        """Initialize variables and state."""
        self.journal_update_in_progress = None
        self.managed_windows = []
        self.topmost_windows = set()
        self._window_states = {}
        self.default_apply_order = ["titlebar", "pos", "size", "aot"]
        self.window_cache = WindowCache(ttl=1.0)
        self.valid_titles_cache = WindowCache(ttl=1.0)
        self.all_windows = None
        self.ignored_windows = []


    def refresh_window_cache(self) -> None:
        """Manually invalidate caches and refresh window list."""
        self.window_cache = None
        self.valid_titles_cache = None
        self.update_window_list()


    def update_window_list(self) -> None:
        """Update the list of windows and remove invalid ones."""
        self.all_windows = self.get_all_window_titles()


    def apply_window_config(self, settings: WindowMetrics, hwnd: int) -> None:
        """Apply a configuration to a specific window."""
        if not self.is_valid_window(hwnd):
            return

        if settings.aot:
            self.topmost_windows.add(hwnd)

        # Apply settings
        apply_funcs = {
            "aot": (self.set_always_on_top, settings.aot),
            "titlebar": (self.set_window_frame, settings.border),
            "pos": (self.set_window_position, settings.x, settings.y),
            "size": (self.set_window_size, settings.w, settings.h),
        }

        apply_order = self.default_apply_order
        apply_order_str = settings.apply_order
        if apply_order_str:
            apply_order = apply_order_str.split(",")


        self.bring_to_front(hwnd)
        for raw_key in apply_order:
            key = raw_key.strip().lower()
            args = apply_funcs[key][1:]
            if args:
                apply_funcs[key][0](hwnd, *args)

        logger.info("Applied config to %s: %s", hwnd, settings)


# Apply window config helper functions
    def add_managed_window(self, hwnd:int)->bool:
        """Add a window to the managed windows list."""
        if hwnd not in self.managed_windows:
            self.managed_windows.append(hwnd)
            # Store initial window state
            metrics = self.get_window_metrics(hwnd)
            if not metrics:
                logger.info("Failed to get metrics for %s", hwnd)
                return False

            self._window_states[hwnd] = metrics

            aot_status = self._window_states[hwnd].aot
            titlebar_status = self._window_states[hwnd].border

            logger.info("Added managed window: %s", hwnd)
            logger.info("Initial state for %s: %s", hwnd, self._window_states[hwnd])
            logger.info("Initial AOT state %s: %s", hwnd, "Yes" if aot_status else "No")
            logger.info("Initial titlebar state %s: %s\n", hwnd, "Yes" if titlebar_status else "No")

            return True

        return False


    def remove_managed_window(self, hwnd:int)->bool:
        """Remove a window from the managed windows list."""
        for win in self.managed_windows:
            if hwnd == win and hwnd in self._window_states:
                original_state = self._window_states[hwnd]
                if original_state:
                    self.bring_to_front(hwnd)
                    pos_x = original_state.x
                    pos_y = original_state.y
                    size_w = original_state.w
                    size_h = original_state.h

                    self.set_window_position(hwnd, pos_x, pos_y)
                    logger.info("Restored position for %s: (%s, %s)", hwnd, pos_x, pos_y)

                    if size_w > MIN_W and size_h > MIN_H:
                        self.set_window_size(hwnd,size_w, size_h)
                        logger.info("Restored size for %s: (%s, %s)", hwnd, size_w, size_h)
                    else:
                        logger.info("Original size for %s is below minimum,"
                            "skipping size restore: (%s, %s)", hwnd, size_w, size_h)

                    self.set_always_on_top(hwnd, enable=original_state.aot)
                    logger.info("Restored always on top state for %s: %s", hwnd, original_state.aot)

                    self.set_window_frame(hwnd, enable=original_state.border)
                    logger.info("Restored window border state for %s: %s\n", hwnd, original_state.border)

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
            self.set_window_frame(hwnd, enable=True)

        self._window_states.clear()

        logger.info("All windows reset to original state.")
        logger.info("Current managed windows after reset: %s", self.managed_windows)
        logger.info("Current topmost windows after reset: %s", self.topmost_windows)
        logger.info("Current window states after reset: %s\n", self._window_states)



    def remove_invalid_windows(self)->None:
        """Remove windows that no longer exist from the managed windows list."""
        if not self.managed_windows:
            return

        valid_hwnds = {hwnd: self.is_valid_window(hwnd) for hwnd in self.managed_windows}
        invalid_hwnds = [hwnd for hwnd, is_valid in valid_hwnds.items() if not is_valid]

        for hwnd in invalid_hwnds:
            if not self.is_valid_window(hwnd):
                self.managed_windows.remove(hwnd)
                logger.info("Removed invalid window: %s", hwnd)
                logger.info("Current managed windows: %s", self.managed_windows)
                if hwnd in self.topmost_windows:
                    self.topmost_windows.remove(hwnd)

        if not self.validate_state():
            logger.warning("State issues found during invalid window removal.")


    def validate_state(self) -> bool:
        """Verify internal consistency and auto-heal if possible."""
        issues_found = False

        # Check all managed windows have state
        for hwnd in self.managed_windows:
            if hwnd not in self._window_states:
                logger.error("Managed window %s has no state!", hwnd)
                issues_found = True

        # Check all topmost windows are managed
        invalid_topmost = self.topmost_windows - set(self.managed_windows)
        if invalid_topmost:
            logger.error("Topmost set contains unmanaged windows: %s", invalid_topmost)
            self.topmost_windows -= invalid_topmost  # Auto-heal
            issues_found = True

        # Check all windows are still valid
        invalid_managed = []
        for hwnd in self.managed_windows:
            if not self.is_valid_window(hwnd):
                invalid_managed.append(hwnd)
                issues_found = True

        if invalid_managed:
            logger.warning("Removing %s invalid managed windows", len(invalid_managed))
            for hwnd in invalid_managed:
                self.managed_windows.remove(hwnd)
                self._window_states.pop(hwnd, None)
                self.topmost_windows.discard(hwnd)

        return not issues_found


# Other functions
    def toggle_always_on_top(self, own_hwnd: int)->None:
        """Toggle AOT status for current config."""
        for hwnd in self.topmost_windows:
            info = get_window_info(hwnd)
            if info:
                flag = HWND_TOPMOST if not info.aot else HWND_NOTOPMOST
                win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

        self.bring_to_front(own_hwnd)


    def find_matching_windows(self, config: ConfigParser, ignore: list) -> tuple[list[dict], list[str]]:
        """Check which windows in the config exist and which don't."""
        sections = config.sections()
        if not sections:
            return [], []

        matching_windows = []
        if not self.valid_titles_cache or not self.valid_titles_cache._is_valid():  # noqa: SLF001
            valid_titles_dict = {}
            self.update_window_list()
            for title in self.all_windows:
                valid_titles_dict[title] = self.all_windows[title].app_name
            self.valid_titles_cache = WindowCache(ttl=1.0)

        valid_titles = self.valid_titles_cache.get(lambda: valid_titles_dict)

        if ignore:
            titles = match_titles(ignore, list(valid_titles.keys()), get_titles=True)
            for item in titles:
                valid_titles.pop(item, None)

        title_matches = match_titles(sections, list(valid_titles.keys()), get_titles=True)
        missing_windows = list(set(sections) - set(title_matches.keys()))

        for section, title in title_matches.items():
            window_info = self.all_windows.get(title)
            config_exe = config.get(section, "exe", fallback=None)
            if not config_exe or window_info.app_name.lower() == config_exe.lower():
                matching_windows.append({
                    "name": self.all_windows[title].title,
                    "short_name": title,
                    "hwnd": self.all_windows[title].hwnd,
                    "exe": self.all_windows[title].app_name,
                })
            else:
                missing_windows.append(section)

        return matching_windows, missing_windows


    def collect_window_settings(self, title: str) -> dict | None:  # noqa: PLR0911
        """Collect window settings from the title."""
        try:
            if not self.all_windows:
                logger.warning("No windows available to collect settings for title: %s", title)
                return None

            if title not in self.all_windows:
                logger.warning("Title '%s' not found in available windows: %s", title, list(self.all_windows.keys()))
                return None

            hwnd = self.all_windows[title].hwnd

            if not self.is_valid_window(hwnd):
                logger.warning("Invalid window found for title: %s", title)
                return None

            metrics = self.get_window_metrics(hwnd)
            if not metrics:
                logger.warning("Failed to get metrics for window with title: %s", title)
                return None

            if not self._validate_metrics(metrics):
                logger.warning("Invalid metrics for window with title: %s - %s", title, metrics)
                return None

            return {
                "position": f"{max(-50, metrics.x + 50)},{max(-50, metrics.y + 50)}",
                "size": f"{max(250, metrics.w)},{max(250, metrics.h)}",
                "always_on_top": metrics.aot,
                "titlebar": metrics.border,
                "original_title": title,
                "name": title,
                "exe": self.all_windows[title].app_name,
            }

        except KeyError:
            logger.warning("KeyError while collecting settings for title: %s", title)
            return None


    def _validate_metrics(self, metrics: WindowMetrics) -> bool:
        """Validate window metrics."""
        if not metrics:
            return False

        min_x = -1000
        max_x = 10000
        min_y = -1000
        max_y = 10000
        return (isinstance(metrics.w, int) and isinstance(metrics.h, int) and
                metrics.w > MIN_W and metrics.h > MIN_H and
                min_x <= metrics.x <= max_x and
                min_y <= metrics.y <= max_y)


    def get_all_window_titles(self, own_hwnd: int | None = None) -> dict:
        """Get the title from all existing windows."""
        def _fetch_windows() -> dict:
            max_length = 50
            def enum_window_callback(hwnd: int, windows: list) -> bool:
                if win32gui.IsWindowVisible(hwnd) and hwnd != own_hwnd:
                    win_info = get_window_info(hwnd)
                    if not win_info:
                        return True

                    title = win_info.title
                    x = re.search(r"(.+)v\d+", title, re.IGNORECASE)
                    if x:
                        title = x.group(1).strip()

                    if title.lower() not in self.ignored_windows:
                        title = win_info.app_name.split(".")[0] if len(win_info.title) > max_length else title

                        windows.append(clean_window_title(title)[0])
                        info.append(win_info)
                return True

            window_titles = []
            # noinspection SpellCheckingInspection
            info = []
            win32gui.EnumWindows(enum_window_callback, window_titles)
            return dict(zip(window_titles, info, strict=False))

        return self.window_cache.get(_fetch_windows)


    def _validate_hwnd(func: Callable) -> bool:  # noqa: N805
        """Validate a hwnd."""
        def wrapper(self, hwnd: int, *args: tuple, **kwargs: dict) -> bool:  # noqa: ANN001
            if not self.is_valid_window(hwnd):
                logger.warning("Can't %s for invalid window: %s", func.__name__,hwnd)
                return False
            return func(self, hwnd, *args, **kwargs)
        return wrapper


    def is_valid_window(self,hwnd: int) -> bool:
        """Check if a hwnd is a valid window."""
        return win32gui.IsWindow(hwnd) != 0


    def get_windows_for_layout(self, config: ConfigParser, missing_windows: list) -> list[WindowInfo]:
        """Get the windows from the config to use for drawing the layout preview."""
        positioned_windows = []
        if not config:
            return []

        for section in config.sections():
            metrics = config_to_metrics(config, section)
            if not metrics:
                continue

            exists = section not in missing_windows
            window_info = metrics_to_window_info(section, metrics, exists=exists)
            positioned_windows.append(window_info)

        return positioned_windows


# Set functions
    @_validate_hwnd
    def set_always_on_top(self, hwnd: int, enable: bool = True) -> None:  # noqa: FBT001, FBT002
        """Set the window to always on top and add it to the topmost windows set."""
        flag = HWND_TOPMOST if enable else HWND_NOTOPMOST
        win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

        if enable and hwnd not in self.topmost_windows:
            self.topmost_windows.add(hwnd)
        elif not enable and hwnd in self.topmost_windows:
            self.topmost_windows.remove(hwnd)


    @_validate_hwnd
    def get_window_metrics(self, hwnd: int) -> WindowMetrics | bool:
        """Get the window metrics from the selected window."""
        metrics = window_to_metrics(get_window_info(hwnd))
        if not metrics:
            return False
        return metrics


    @_validate_hwnd
    def set_window_frame(self, hwnd: int, enable: bool = True) -> bool:  # noqa: FBT001, FBT002
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
    def set_window_size(self, hwnd: int, width: int, height: int) -> bool | None:
        """Set the size of the window."""
        win_info = get_window_info(hwnd)
        if win_info:
            x, y = int(win_info.x), int(win_info.y)
            win32gui.SetWindowPos(hwnd, 0, x, y, width, height, SWP_NOZORDER | SWP_NOMOVE)
            return True

        return False


    @_validate_hwnd
    def set_window_position(self, hwnd: int, x: int, y: int) -> bool | None:
        """Set the position of the window."""
        win_info = get_window_info(hwnd)
        if win_info:
            width, height = win_info.width, win_info.height
            win32gui.SetWindowPos(hwnd, 0, x, y, width, height, SWP_NOZORDER | SWP_NOSIZE)
            return True

        return False


    @_validate_hwnd
    def bring_to_front(self, hwnd: int) -> None:
        """Set a window to the front, not AOT."""
        win32gui.ShowWindow(hwnd, SW_RESTORE)
        win32gui.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

