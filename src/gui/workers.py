"""Worker classes for threading operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Signal

from backend.common import config_to_metrics

if TYPE_CHECKING:
    from collections.abc import Callable
    from configparser import ConfigParser

import logging

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Defines the signals available from a running worker thread."""

    finished = Signal()
    result = Signal(object)


class GenericWorker(QRunnable):
    """Worker thread for running functions without blocking the UI."""

    def __init__(self, fn: Callable, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        """Initialize the worker."""
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        """Execute the function."""
        try:
            self.fn(*self.args, **self.kwargs)
        finally:
            self.signals.finished.emit()


class ApplyWorker(GenericWorker):
    """Worker for applying window configurations."""

    def __init__(self, win_man: object, config: ConfigParser) -> None:
        """Initialize the worker."""
        self.win_man = win_man
        self.config = config
        super().__init__(self.apply_settings)

    def apply_settings(self) -> None:
        """Apply window configurations."""
        self.win_man.validate_state()

        if self.config:
            matching_windows, _ = self.win_man.find_matching_windows(self.config, [])

            for window in matching_windows:
                win_id = window["win_id"]
                self.win_man.add_managed_window(win_id)

                settings = config_to_metrics(self.config, window["short_name"])
                if settings:
                    if settings.aot:
                        self.win_man.topmost_windows.add(win_id)
                    self.win_man.apply_window_config(settings, win_id)
                else:
                    logger.info("Failed to apply settings to %s", window)


class ReapplyWorker(GenericWorker):
    """Worker for reapplying window configurations."""

    def __init__(self, win_man: object, config: ConfigParser) -> None:
        """Initialize the worker."""
        self.win_man = win_man
        self.config = config
        super().__init__(self._reapply_settings_logic)

    def _reapply_settings_logic(self) -> None:
        """Logic for reapplying window configurations."""
        self.win_man.validate_state()
        matching, _ = self.win_man.find_matching_windows(self.config, [])
        if matching:
            win_match_config = self.win_man.verify_window_data(self.config, matching)
            for win in win_match_config:
                if not win["identical"]:
                    logger.info("Reapply triggered on %s", win["name"])

                    if win["win_id"] not in self.win_man.managed_windows:
                        self.win_man.add_managed_window(win["win_id"])

                    settings = config_to_metrics(self.config, win["short_name"])
                    if settings:
                        if settings.aot:
                            self.win_man.topmost_windows.add(win["win_id"])
                        self.win_man.apply_window_config(settings, win["win_id"])
                    else:
                        logger.info("Failed to apply settings to %s", win)


class ScreenshotWorker(GenericWorker):
    """Worker for taking screenshots."""

    def __init__(self, win_man: object, config: object, capture_window: Callable) -> None:
        """Initialize the worker."""
        self.win_man = win_man
        self.config = config
        self.capture_window = capture_window
        super().__init__(self._take_screenshot_start)

    def _take_screenshot_start(self) -> None:
        existing, _ = self.win_man.find_matching_windows(self.config, [])
        if existing:
            for window in existing:
                self.capture_window(window)

