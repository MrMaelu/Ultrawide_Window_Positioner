"""Window management for Ultrawide Window Positioner."""
import logging
import threading
import time
from collections.abc import Callable
from configparser import ConfigParser
from dataclasses import asdict, dataclass

# Local imports
from backend import (
    bring_to_front,
    get_all_windows,
    get_window_info,
    is_valid_window,
    set_aot,
    set_position,
    set_size,
    set_window_frame,
)
from backend.common import (
    WindowInfo,
    WindowMetrics,
    config_to_metrics,
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

    def __init__(self) -> None:
        """Initialize variables and state."""
        self.journal_update_in_progress = None
        self.topmost_windows = set()
        self.managed_windows = {}
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

    def apply_window_config(self, settings: WindowMetrics, win_id: int | str) -> None:
        """Apply a configuration to a specific window."""
        if not is_valid_window(win_id):
            return

        # Apply settings
        apply_funcs = {
            "aot": (self.set_always_on_top, settings.aot),
            "titlebar": (set_window_frame, settings.border),
            "pos": (self.set_window_position, settings.x, settings.y),
            "size": (self.set_window_size, settings.w, settings.h),
        }

        apply_order = self.default_apply_order
        apply_order_str = settings.apply_order
        if apply_order_str:
            apply_order = apply_order_str.split(",")

        bring_to_front(win_id)
        for raw_key in apply_order:
            key = raw_key.strip().lower()
            args = apply_funcs[key][1:]
            if args:
                apply_funcs[key][0](win_id, *args)

        logger.info("Applied config to %s: %s", win_id, settings)

    # Apply window config helper functions
    def add_managed_window(self, win_id: int) -> bool:
        """Add a window to the managed windows list."""
        if win_id not in self.managed_windows:
            # Store initial window state
            metrics = self.get_window_metrics(win_id)
            if not metrics:
                logger.error("Failed to get metrics for %s", win_id)
                return False

            logger.info("Adding managed window: %s with initial metrics: %s", win_id, metrics)
            self.managed_windows[win_id] = metrics

            aot_status = self.managed_windows[win_id].aot

            titlebar_status = self.managed_windows[win_id].border

            logger.info("Added managed window: %s", win_id)
            logger.info("Initial state for %s: %s", win_id, self.managed_windows[win_id])
            logger.info("Initial AOT state %s: %s", win_id, "Yes" if aot_status else "No")
            logger.info("Initial titlebar state %s: %s\n", win_id, "Yes" if titlebar_status else "No")

            return True

        return False

    def remove_managed_window(self, win_id: int | str, *, skip_restore: bool = False) -> bool:
        """Remove a window from the managed windows list."""
        if win_id in self.managed_windows:
            original_state = self.managed_windows[win_id]
            del self.managed_windows[win_id]

            if original_state and not skip_restore:
                bring_to_front(win_id)
                pos_x = original_state.x
                pos_y = original_state.y
                size_w = original_state.w
                size_h = original_state.h

                self.set_window_position(win_id, pos_x, pos_y)
                logger.info("Restored position for %s: (%s, %s)", win_id, pos_x, pos_y)

                if size_w > MIN_W and size_h > MIN_H:
                    self.set_window_size(win_id, size_w, size_h)
                    logger.info("Restored size for %s: (%s, %s)", win_id, size_w, size_h)
                else:
                    logger.info("Original size for %s is below minimum,"
                                "skipping size restore: (%s, %s)", win_id, size_w, size_h)

                self.set_always_on_top(win_id, enable=original_state.aot)
                logger.info("Restored always on top state for %s: %s", win_id, original_state.aot)

                set_window_frame(win_id, enable=original_state.border)
                logger.info("Restored window border state for %s: %s\n", win_id, original_state.border)

            if win_id in self.topmost_windows:
                self.topmost_windows.remove(win_id)

            return True

        return False

    def reset_all_windows(self) -> None:
        """Reset all windows to the original state."""
        windows_to_reset = self.managed_windows.copy()
        for win_id in windows_to_reset:
            self.remove_managed_window(win_id)
            self.set_always_on_top(win_id, enable=False)
            set_window_frame(win_id, enable=True)

        self.managed_windows.clear()
        self.topmost_windows.clear()


        logger.info("All windows reset to original state.")
        logger.info("Current managed windows after reset: %s", self.managed_windows.keys())
        logger.info("Current topmost windows after reset: %s", self.topmost_windows)
        logger.info("Current window states after reset: %s\n", self.managed_windows)

    def validate_state(self) -> bool:
        """Verify internal consistency and auto-heal if possible."""
        issues_found = False

        # Check all topmost windows are managed
        invalid_topmost = self.topmost_windows - set(self.managed_windows.keys())
        if invalid_topmost:
            logger.error("Topmost set contains unmanaged windows: %s", invalid_topmost)
            self.topmost_windows -= invalid_topmost
            issues_found = True

        # Check all windows are still valid
        invalid_managed = [win_id for win_id in self.managed_windows if not is_valid_window(win_id)]
        if invalid_managed:
            logger.warning("Removing %s invalid managed window(s)", len(invalid_managed))
            for win_id in invalid_managed:
                self.remove_managed_window(win_id, skip_restore=True)

        return not issues_found

    # Other functions
    def find_matching_windows(self, config: ConfigParser, ignore: list) -> tuple[list[dict], list[str]]:
        """Check which windows in the config exist and which don't."""
        if not config:
            return [], []

        sections = config.sections()
        if not sections:
            return [], []

        def _get_valid_titles() -> dict:
            valid_titles_dict = {}
            self.update_window_list()
            for title in self.all_windows:
                valid_titles_dict[title] = self.all_windows[title].app_name
            return valid_titles_dict

        valid_titles = self.valid_titles_cache.get(_get_valid_titles)

        if ignore:
            titles = match_titles(ignore, list(valid_titles.keys()), get_titles=True)
            for item in titles:
                valid_titles.pop(item, None)

        title_matches = match_titles(sections, list(valid_titles.keys()), get_titles=True)
        missing_windows = list(set(sections) - set(title_matches.keys()))
        matching_windows = []

        for section, title in title_matches.items():
            window_info = self.all_windows.get(title)
            config_exe = config.get(section, "exe", fallback=None)
            if not config_exe or window_info.app_name.lower() == config_exe.lower():
                matching_windows.append({
                    "name": self.all_windows[title].title,
                    "short_name": title,
                    "win_id": self.all_windows[title].win_id,
                    "exe": self.all_windows[title].app_name,
                    "aot": config.getboolean(section, "always_on_top", fallback=False),
                })
            else:
                missing_windows.append(section)

        return matching_windows, missing_windows

    def collect_window_settings(self, title: str) -> dict | None:
        """Collect window settings from the title."""
        try:
            no_win_or_title_error = False
            if not self.all_windows:
                logger.warning("No windows available to collect settings for title: %s", title)
                no_win_or_title_error = True
            elif title not in self.all_windows:
                logger.warning("Title '%s' not found in available windows: %s", title, list(self.all_windows.keys()))
                no_win_or_title_error = True

            if no_win_or_title_error:
                return None

            win_id = self.all_windows[title].win_id

            if not is_valid_window(win_id):
                logger.warning("Invalid window found for title: %s", title)
                return None

            metric_error = False
            metrics = self.get_window_metrics(win_id)
            if not metrics:
                logger.warning("Failed to get metrics for window with title: %s", title)
                metric_error = True
            elif not self._validate_metrics(metrics):
                logger.warning("Invalid metrics for window with title: %s - %s", title, metrics)
                metric_error = True

            if metric_error:
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


    def verify_window_data(self, config: ConfigParser, matching_windows: list) -> list:
        """Compare the metrics of the windows in the config with the actual windows and return a list of results."""
        compare_results = []
        for match in matching_windows:
            results = {}
            metrics = self.get_window_metrics(match["win_id"])
            if not metrics or not config:
                continue

            section = match["short_name"]
            settings_metrics = config_to_metrics(config, section)

            win_met = {k: v for k, v in asdict(metrics).items() if k != "apply_order"}
            cfg_met = {k: v for k, v in asdict(settings_metrics).items() if k != "apply_order"}

            results["name"] = match["name"]
            results["win_id"] = match["win_id"]
            results["short_name"] = match["short_name"]
            results["identical"] = win_met == cfg_met
            compare_results.append(results)

        return compare_results


    @staticmethod
    def _validate_metrics(metrics: WindowMetrics) -> bool:
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

    def get_all_window_titles(self, own_win_id: int | None = None) -> dict:
        """Get the title from all existing windows."""
        return self.window_cache.get(lambda: get_all_windows(own_win_id, self.ignored_windows))

    def toggle_always_on_top(self, own_win_id: int | str) -> None:
        """Toggle AOT status for current config."""
        for win_id in self.topmost_windows:
            info = get_window_info(win_id)
            if info:
                logger.info("Toggling AOT for %s: currently %s", win_id, "Yes" if info.aot else "No")
                set_aot(win_id, not info.aot)

        bring_to_front(own_win_id, is_self=True)

    @staticmethod
    def get_windows_for_layout(config: ConfigParser, missing_windows: list) -> list[WindowInfo]:
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
    @staticmethod
    def set_always_on_top(win_id: int | str, enable: bool = True) -> None:  # noqa: FBT001, FBT002
        """Set the window to always on top and add it to the topmost windows set."""
        set_aot(win_id, enable)

    @staticmethod
    def get_window_metrics(win_id: int | str) -> WindowMetrics | bool:
        """Get the window metrics from the selected window."""
        metrics = window_to_metrics(get_window_info(win_id))
        if not metrics:
            return False
        return metrics

    @staticmethod
    def set_window_size(win_id: int | str, width: int, height: int) -> bool | None:
        """Set the size of the window."""
        win_info = get_window_info(win_id)
        if win_info:
            set_size(win_id, win_info, width, height)
            return True

        return False

    @staticmethod
    def set_window_position(win_id: int | str, x: int, y: int) -> bool | None:
        """Set the position of the window."""
        win_info = get_window_info(win_id)
        if win_info:
            set_position(win_id, win_info, x, y)
            return True

        return False
