"""Platform specific backend for Ultrawide Window Positioner."""
import sys

if sys.platform == "win32":
    from backend.win32_funcs import (
        bring_to_front,
        get_all_windows,
        get_aot_toggle,
        get_app_window_title,
        get_screenshot,
        get_window_info,
        is_valid_window,
        run_clean_subprocess,
        set_aot,
        set_position,
        set_size,
        set_window_frame,
    )
else:
    from backend.linux_funcs import (
        bring_to_front,
        get_all_windows,
        get_aot_toggle,
        get_app_window_title,
        get_screenshot,
        get_window_info,
        is_valid_window,
        run_clean_subprocess,
        set_aot,
        set_position,
        set_size,
        set_window_frame,
    )

from backend.common import (
    WindowInfo,
    WindowMetrics,
    WindowsWindow,
    clean_window_title,
    config_to_metrics,
    convert_hex_to_rgb,
    format_coords,
    get_binary_path,
    get_data_path,
    invert_hex_color,
    match_titles,
    metrics_to_window_info,
    parse_coords,
    to_bool,
    validate_int_pair,
    window_to_metrics,
)
from backend.config import ConfigManager, get_ignore_list
from backend.window import WindowManager

__all__ = [
    "ConfigManager",
    "WindowInfo",
    "WindowManager",
    "WindowMetrics",
    "WindowsWindow",
    "bring_to_front",
    "clean_window_title",
    "config_to_metrics",
    "convert_hex_to_rgb",
    "format_coords",
    "get_all_windows",
    "get_aot_toggle",
    "get_app_window_title",
    "get_binary_path",
    "get_data_path",
    "get_ignore_list",
    "get_screenshot",
    "get_window_info",
    "invert_hex_color",
    "is_valid_window",
    "match_titles",
    "metrics_to_window_info",
    "parse_coords",
    "run_clean_subprocess",
    "set_aot",
    "set_position",
    "set_size",
    "set_window_frame",
    "set_window_frame",
    "to_bool",
    "validate_int_pair",
    "window_to_metrics",
]

