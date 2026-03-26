# src/gui/workers.py
"""Worker classes for threading operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Signal

if TYPE_CHECKING:
    from collections.abc import Callable


class WorkerSignals(QObject):
    """Defines the signals available from a running worker thread."""

    finished = Signal()
    # Optional: if you need to pass data back to the UI
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
