# src/gui/layout_preview.py
"""Layout preview widget for screen visualization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel, QWidget

from uwp_constants import Colors
from uwp_utils import WindowInfo, convert_hex_to_rgb

if TYPE_CHECKING:
    from pathlib import Path

    from uwp_config import ApplicationSettings

logger = logging.getLogger(__name__)


class ScreenLayoutWidget(QWidget):
    """Layout preview widget."""

    def __init__(self,  # noqa: PLR0913
                 parent: QWidget,
                 screen_width: int,
                 screen_height: int,
                 windows: list[WindowInfo],
                 assets_dir: Path,
                 app_settings: ApplicationSettings,
                 ) -> None:
        """Set up base variables."""
        super().__init__(parent)
        self.last_y_offset = None
        self.last_x_offset = None
        self.last_scale = None
        self.active_labels = None
        self.parent = parent
        self.colors = self.parent.colors
        self.assets_dir = assets_dir

        self.windows = windows

        self.window_details = app_settings.details
        self.use_images = app_settings.use_images

        self.screen_width = screen_width
        self.screen_height = screen_height

        self.taskbar_height = 40
        self.line_height = 16  # Approximate for text

        self.status_labels = {}

    def _handle_status_label(self, win: WindowInfo, x: int, y: int, w: int, h: int) -> None:
        _y = y
        name = win.search_title or win.name

        if name not in self.status_labels:
            label = QLabel("Missing", self)
            label.setStyleSheet(f"color: {Colors.TEXT_ERROR}; font-weight: bold; background: transparent;")
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.status_labels[name] = label

        label = self.status_labels[name]

        if not win.exists:
            label.adjustSize()
            label_x = int(x + (w / 2) - (label.width() / 2))
            label_y = int(y + (h - 10) - (label.height() / 2))

            label.move(label_x, label_y)
            label.show()
            label.raise_()
        else:
            label.hide()

    def paintEvent(self, event: None) -> None:  # noqa: N802
        """Override for paintEvent."""
        _event = event
        painter = QPainter(self)
        self.draw_layout(painter, self.width(), self.height())

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Override for wheelEvent."""
        if hasattr(self.parent, "combo_box"):
            combo = self.parent.combo_box
            delta = event.angleDelta().y()
            current = combo.currentIndex()
            new_index = max(0, current - 1) if delta > 0 else min(combo.count() - 1, current + 1)
            combo.setCurrentIndex(new_index)

    def draw_layout(self, painter: QPainter, width: int, height: int) -> None:
        """Draw the layout preview."""
        self.active_labels = set()
        for win in self.windows:
            win_name = win.search_title or win.name
            self.active_labels.add(win_name)

        painter.fillRect(0, 0, width, height, QColor(self.colors.BACKGROUND))

        frame_width = 15
        padding = frame_width / 2

        drawable_height = height - frame_width * 2
        drawable_width = width - frame_width * 2

        screen_ratio = self.screen_width / self.screen_height
        canvas_ratio = drawable_width / drawable_height

        if canvas_ratio > screen_ratio:
            scale = drawable_height / self.screen_height
            scaled_width = scale * self.screen_width
            x_offset = (drawable_width - scaled_width) / 2 + frame_width
            y_offset = frame_width
        else:
            scale = drawable_width / self.screen_width
            scaled_height = scale * self.screen_height
            x_offset = frame_width
            y_offset = (drawable_height - scaled_height) / 2 + frame_width

        self.last_scale = scale
        self.last_x_offset = x_offset
        self.last_y_offset = y_offset

        frame_rect = QRect(
            int(x_offset - padding),
            int(y_offset - padding),
            int(scale * self.screen_width + padding * 2),
            int(scale * self.screen_height + padding * 2),
        )

        # Fill inner screen area
        painter.fillRect(frame_rect, QColor("#202020"))
        painter.setPen(QColor(Colors.WINDOW_BORDER))
        painter.drawRect(frame_rect)

        # Windows
        aot_windows = [w for w in self.windows if w.always_on_top]
        regular_windows = [w for w in self.windows if not w.always_on_top]

        for win in regular_windows:
            self.draw_window(painter, x_offset, y_offset, win, scale)

        # Taskbar
        taskbar_rect = QRect(
            int(frame_rect.left() + padding),
            int(frame_rect.bottom() - padding - self.taskbar_height * scale),
            int(frame_rect.width() - padding * 2),
            int(self.taskbar_height * scale),
        )
        painter.fillRect(taskbar_rect, QColor(Colors.TASKBAR))

        for win in aot_windows:
            self.draw_window(painter, x_offset, y_offset, win, scale)

        for title, label in list(self.status_labels.items()):
            if title not in self.active_labels:
                label.hide()

        # ---- Outer border drawn last ----
        r, g, b = convert_hex_to_rgb(Colors.WINDOW_FRAME)
        frame_color = QColor(r, g, b)
        pen = QPen(frame_color, frame_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        corner_radius = 10
        painter.drawRoundedRect(frame_rect, corner_radius, corner_radius)

    def draw_window(self,
                    painter: QPainter,
                    x_offset: int,
                    y_offset: int,
                    win: WindowInfo,
                    scale: float,
                    ) -> None:
        """Draw a window representation."""
        x = int(x_offset + win.pos_x * scale)
        y = int(y_offset + win.pos_y * scale)
        w = int(win.width * scale)
        h = int(win.height * scale)

        draw_params = {"painter": painter, "x": x, "y": y, "w": w, "h": h, "win": win}

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, on=False)

        # Fill color
        fill_color = QColor(Colors.WINDOW_ALWAYS_ON_TOP if win.always_on_top else Colors.WINDOW_NORMAL)
        fill_color.setAlpha(255)

        # Draw window with border
        pen = QPen(QColor(Colors.WINDOW_BORDER))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(int(x), int(y), int(w), int(h))

        # Draw images if enabled
        if self.use_images:
            self.draw_images(draw_params)

        self._handle_status_label(win, x, y, w, h)

        # Draw window text
        self.draw_text(draw_params)

    def draw_text(self, draw_params: dict) -> None:
        """Draw the window information text."""
        win = draw_params["win"]
        painter = draw_params["painter"]
        x = draw_params["x"]
        y = draw_params["y"]
        _w = draw_params["w"]
        h = draw_params["h"]
        aot_text = "Yes" if win.always_on_top else "No"
        title = win.search_title or win.name
        if not title:
            return

        info_lines = [
            f"{title} ",
            f"Pos: {win.pos_x}, {win.pos_y} " if self.window_details else "",
            f"Size: {win.width} x {win.height} " if self.window_details else "",
            f"AOT: {aot_text} " if self.window_details else "",
        ]
        padding_x = 4
        padding_y = 0

        y_cursor = y + padding_y
        for i, line in enumerate(info_lines):
            if not line:
                continue
            painter.setFont(QFont("Arial", 10 if i == 0 else 8))

            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(line)
            text_rect.moveTo(int(x + padding_x), int(y_cursor))

            # keep inside window vertically
            if text_rect.bottom() > y + h - padding_y:
                break

            # background box
            bg_rect = text_rect.adjusted(-3, -1, +3, +1)
            painter.setBrush(QColor(0, 0, 0, 160))  # semi-transparent black
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(bg_rect)

            # text
            if self.use_images:
                painter.setPen(QColor(Colors.TEXT_NORMAL if not win.always_on_top else Colors.TEXT_ALWAYS_ON_TOP))
            else:
                painter.setPen(QColor(Colors.TEXT_NORMAL))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)

            y_cursor += self.line_height

    def draw_images(self, draw_params: dict) -> None:
        """Draw screenshot images."""
        win = draw_params["win"]
        painter = draw_params["painter"]
        x, y, w, h = draw_params["x"], draw_params["y"], draw_params["w"], draw_params["h"]
        target_ratio = w / h
        base_name = win.search_title.replace(" ", "_").replace(":", "")

        ratios = {
            "32-9": 32/9,
            "21-9": 21/9,
            "16-9": 16/9,
            "4-3": 4/3,
            "square": 1,
            "3-4": 3/4,
            "9-16": 9/16,
            "9-21": 9/21,
            "9-32": 9/32,
        }

        best_path = None
        min_diff = float("inf")

        for img_path in self.assets_dir.glob(f"{base_name}_*.png"):
            suffix = img_path.stem.split("_")[-1]
            file_ratio = ratios.get(suffix, 1.0)

            diff = abs(target_ratio - file_ratio)
            if diff < min_diff:
                min_diff = diff
                best_path = img_path

        if best_path and best_path.exists():
            # stretch
            pixmap = QPixmap(str(best_path)).scaled(
                int(w), int(h),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(int(x), int(y), pixmap)
