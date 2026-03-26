# src/gui/config_dialog.py
"""Dialog for creating and configuring window layouts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.layout_preview import ScreenLayoutWidget
from uwp_config import ConfigManager
from uwp_constants import Colors, UIConstants
from uwp_utils import WindowInfo, clean_window_title, to_bool, validate_int_pair

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WindowSettings:
    """Settings for a window in the config dialog."""

    name: str
    position: str
    size: str
    always_on_top: bool
    titlebar: bool
    process_priority: bool = False
    exe: str = ""


class ConfigDialog(QDialog):
    """Dialog for creating and configuring window layouts."""

    def __init__(  # noqa: PLR0913
        self,
        parent: QWidget,
        window_titles: list[str],
        save_callback: Callable,
        settings_callback: Callable,
        refresh_callback: Callable,
        screen_width: int,
        screen_height: int,
        y_offset: int,
        assets_dir: Path,
        max_windows: int = 4,
        config_name: str = "",
        *,
        edit_mode: bool = False,
    ) -> None:
        """Initialize the dialog with window selection and settings callbacks."""
        super().__init__(parent)
        self.hide()
        self.err_msg = QMessageBox(self)
        self.lower_switch = None
        self.upper_switch = None
        self.save_area = QWidget()
        self.settings_area = QWidget()
        self.preset_label_text = None
        self.config_name_edit = None
        self.layout_container_layout = None
        self.layout_container = None
        self.ratio_label = None
        self.ignore_edit = None
        self.row_to_title = None
        self.settings_rows = None
        self.rows_layout = None
        self.sorted_window = None
        self.setWindowTitle("Create Config")

        self.colors = parent.colors
        self.use_images = True
        self.cfg_man = ConfigManager(parent.base_path)
        self.win_man = parent.win_man
        self.config_name = config_name
        self.auto_align_offsets = None

        self.window_titles = window_titles
        self.save_callback = save_callback
        self.settings_callback = settings_callback
        self.refresh_callback = refresh_callback
        self.screen_width = screen_width
        self.screen_height_org = screen_height
        self.screen_height = self.screen_height_org
        self.y_offset_org = y_offset
        self.y_offset = 0
        self.assets_dir = assets_dir
        self.max_windows = max_windows

        self.layout_number = 0
        self.layout_preview = None

        self.main_layout = QVBoxLayout(self)

        self.edit_mode = edit_mode
        self.apply_order = self._get_apply_order() if edit_mode else None

        self.setMinimumWidth(250)

        if self.edit_mode:
            QTimer.singleShot(0, lambda: self.show_config_settings(self.window_titles))
            return

        QTimer.singleShot(0, self._open_selection_menu)

    def _get_apply_order(self) -> list[str]:
        """Retrieve and validate the current apply order from config."""
        settings = self.settings_callback("DEFAULT")

        valid_labels = self.win_man.default_apply_order
        valid_labels = [label.title() for label in valid_labels if label]

        apply_order = settings.get("apply_order", "").split(",")
        apply_order = [label.title() for label in apply_order if label]

        if not apply_order:
            return valid_labels

        # Remove duplicates and keep order
        apply_order = list(dict.fromkeys(apply_order))
        valid_set = set(valid_labels)
        apply_order = [label for label in apply_order if label in valid_set]

        # Add missing labels to the end
        for label in valid_labels:
            if label not in apply_order:
                apply_order.append(label)

        return apply_order

    def confirm_selection(self) -> None:
        """Validate selected windows and move to settings stage."""
        selected = [t for t, cb in self.switches.items() if cb.isChecked()]

        if not selected:
            self.err_msg.setText("ERROR:\nNo windows selected!")
            self.err_msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            self.err_msg.show()
            return
        if len(selected) > self.max_windows:
            QMessageBox.critical(
                self, "Error", f"Select up to {self.max_windows} windows only",
            )
            return

        self.selection_area.hide()

        sorted_windows = sorted(selected, key=lambda title: int(
            (self.settings_callback(title) or {}).get("position", "0,0").split(",")[0]),
        )

        self.show_config_settings(sorted_windows)


    def _create_apply_order_list(self, order: list[str] | None = None) -> QWidget:
        # noinspection SpellCheckingInspection
        listw = QListWidget()
        listw.setFlow(QListView.Flow.LeftToRight)
        listw.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        listw.setDefaultDropAction(Qt.DropAction.MoveAction)
        listw.setWrapping(False)
        listw.setSpacing(5)
        listw.setFixedHeight(40)

        order = order or self.win_man.default_apply_order

        for label in order:
            item = QListWidgetItem(label.capitalize())
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setSizeHint(QSize(110, 20))
            listw.addItem(item)

        listw.setStyleSheet(f"""
        QListWidget::item {{
            background: {Colors.BUTTON_NORMAL};
            border-radius: 6px;
            border: 2px solid {Colors.BORDER_COLOR};
        }}
        QListWidget::item:selected {{
            background: {Colors.BUTTON_HOVER};
        }}
        QListWidget::item:focus {{
            outline: none;
        }}
        """)

        # Wrapper widget with border
        container = QWidget()
        container.setObjectName("apply_order_container")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(2, 2, 2, 2)
        description = QLabel("Drag to reorder apply priority:")
        description.setContentsMargins(10, 0, 10, 0)
        container_layout.addWidget(description)
        container_layout.addWidget(listw)

        container.setStyleSheet(f"""
        QWidget#apply_order_container {{
            border: 0px solid {Colors.BORDER_COLOR};
            border-radius: 6px;
        }}
        """)

        return container

    def _open_selection_menu(self) -> None:
        if hasattr(self, "selection_area"):
            self.selection_area.hide()
            self.selection_area.deleteLater()

        self.selection_area = QWidget()
        sel_layout = QVBoxLayout(self.selection_area)

        self.switches = {}
        for title in self.window_titles:
            cb = QCheckBox(title)
            cb.setMinimumHeight(25)
            self.switches[title] = cb
            sel_layout.addWidget(cb)

        confirm_btn = QPushButton("Confirm Selection")
        confirm_btn.clicked.connect(self.confirm_selection)
        sel_layout.addWidget(confirm_btn)

        self.main_layout.addWidget(self.selection_area)

        self.ensurePolished()
        new_size = self.sizeHint()
        self.resize(new_size.expandedTo(QSize(200, 100)))

        if self.parent():
            p_geo = self.parent().geometry()
            self.move(
                p_geo.center().x() - (self.width() // 2),
                p_geo.center().y() - (self.height() * 2),
            )

        self.show()

    def _on_lower_toggle(self) -> None:
        if self.lower_switch.isChecked():
            self.upper_switch.setChecked(False)
            self.y_offset = self.y_offset_org
        else:
            self.y_offset = 0

    def _on_upper_toggle(self) -> None:
        if self.upper_switch.isChecked():
            self.lower_switch.setChecked(False)
            self.y_offset = 0
            self.screen_height = self.screen_height_org // 2
        else:
            self.screen_height = self.screen_height_org

    def show_config_settings(self, sorted_window: list[str]) -> None:  # noqa: PLR0915
        """Display settings rows, controls, and layout preview for selected windows."""
        self.sorted_window = sorted_window
        settings_layout = QVBoxLayout(self.settings_area)
        apply_order = self._create_apply_order_list(self.apply_order)
        settings_layout.addWidget(apply_order)

        # Rows container
        rows_container = QWidget()
        self.rows_layout = QVBoxLayout(rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)

        self.settings_rows = {}
        self.row_to_title = {}

        for title in self.sorted_window:
            values = self.settings_callback(title) or {}
            row = WindowSettingsRow(title, values)
            self.add_move_buttons(row)
            self.rows_layout.addWidget(row)
            self.settings_rows[title] = row
            self.row_to_title[row] = title

        settings_layout.addWidget(rows_container, stretch=0)
        ignore_list = self.settings_callback("DEFAULT").get("ignore_list", "") if self.edit_mode else ""
        ignore_label = QLabel("List of titles to not match (comma separated):")

        self.ignore_edit = QLineEdit(ignore_list)

        settings_layout.addWidget(ignore_label)
        settings_layout.addWidget(self.ignore_edit)

        # Controls
        controls = QHBoxLayout()
        controls.setContentsMargins(10, 0, 10, 0)
        auto_btn = QPushButton("Auto align")
        auto_btn.setFixedSize(100, 30)

        update_btn = QPushButton("Update drawing")
        update_btn.setFixedSize(120, 30)

        self.ratio_label = QLabel("")

        controls.addWidget(auto_btn)
        controls.addWidget(update_btn)
        controls.addWidget(self.ratio_label)

        settings_layout.addLayout(controls, stretch=0)

        auto_btn.clicked.connect(lambda: self.auto_position(self.sorted_window))
        update_btn.clicked.connect(self.update_layout_frame)

        # Layout preview
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.layout_container_layout = QVBoxLayout(self.layout_container)

        self.upper_switch = QCheckBox("Restrict to upper half", self)
        self.upper_switch.stateChanged.connect(self._on_upper_toggle)
        settings_layout.addWidget(self.upper_switch)

        self.lower_switch = QCheckBox("Restrict to lower half", self)
        self.lower_switch.stateChanged.connect(self._on_lower_toggle)
        settings_layout.addWidget(self.lower_switch)

        settings_layout.addWidget(self.layout_container, stretch=1)

        # Save area
        save_layout = QHBoxLayout(self.save_area)
        save_layout.addWidget(QLabel("Config Name:"))

        self.config_name_edit = QLineEdit(self.config_name)
        save_layout.addWidget(self.config_name_edit)

        save_btn = QPushButton("Save Config")
        save_btn.setFixedSize(100, 30)
        save_layout.addWidget(save_btn)

        save_btn.clicked.connect(self.on_save)
        settings_layout.addWidget(self.save_area, stretch=0)

        self.layout().addWidget(self.settings_area)

        self.resize(self.sizeHint())
        window_min_height = UIConstants.WINDOW_MIN_HEIGHT + (len(self.settings_rows) * 50)
        self.setMinimumSize(UIConstants.WINDOW_MIN_WIDTH, window_min_height)

        if self.parent():
            p_geo = self.parent().geometry()
            self.move(
                p_geo.x(),
                p_geo.y(),
            )

        self.update_layout_frame()

    def add_move_buttons(self, row: WindowSettingsRow) -> None:
        """Add Up/Down buttons to a settings row."""
        btn_layout = QHBoxLayout()
        up_btn = QPushButton("↑")
        down_btn = QPushButton("↓")

        up_btn.setFixedSize(30, 30)
        down_btn.setFixedSize(30, 30)

        btn_layout.addWidget(up_btn)
        btn_layout.addWidget(down_btn)

        row.layout.layout().insertLayout(0, btn_layout)

        up_btn.clicked.connect(lambda _, r=row: self.move_row(r, -1))
        down_btn.clicked.connect(lambda _, r=row: self.move_row(r, 1))

    def move_row(self, row: WindowSettingsRow, direction: int) -> None:
        """Move the row up (-1) or down (+1) in the layout."""
        index = self.rows_layout.indexOf(row)
        new_index = index + direction
        if 0 <= new_index < self.rows_layout.count():
            self.rows_layout.removeWidget(row)
            self.rows_layout.insertWidget(new_index, row)

            title = self.row_to_title[row]
            current_index = self.sorted_window.index(title)
            self.sorted_window.pop(current_index)
            self.sorted_window.insert(new_index, title)

            self.update_layout_frame()

    def gather_windows(self) -> list[WindowInfo]:
        """Get windows for the layout preview."""
        windows = []
        for row in self.settings_rows.values():
            vals = row.get_values()
            pos_x, pos_y = validate_int_pair(vals["position"])
            size_w, size_h = validate_int_pair(vals["size"])
            windows.append(WindowInfo(vals["name"],
                                      pos_x, pos_y, size_w, size_h,
                                      always_on_top=vals["always_on_top"], exists=True,
                                      search_title="",
                                      ))
        return windows

    def update_layout_frame(self) -> None:
        """Update the layout preview."""
        windows = self.gather_windows()

        if self.layout_preview:
            self.layout_preview.setParent(None)

        self.layout_preview = ScreenLayoutWidget(
            self, self.screen_width, self.screen_height_org,
            windows, self.assets_dir, window_details=True,
        )
        self.layout_container_layout.addWidget(self.layout_preview)

    def update_row(self,
                   title: str,
                   pos: str | None = None,
                   size: str | None = None,
                   *,
                   aot: bool | None = None,
                   titlebar: bool | None = None,
                   ) -> None:
        """Update a WindowSettingsRow without overwriting unchanged values."""
        row = self.settings_rows[title]
        vals = row.get_values()

        row.set_values(
            name=vals["name"],
            pos=pos if pos is not None else vals["position"],
            size=size if size is not None else vals["size"],
            aot=aot if aot is not None else vals["always_on_top"],
            titlebar=titlebar if titlebar is not None else vals["titlebar"],
        )


    def _calc_four(self, layout_configs: list,
                   screen_width: int, screen_height: int, usable_height: int,
                   ) -> list[tuple]:
        _ = screen_height
        layout = layout_configs[self.layout_number]
        positions = []
        for (rel_x, rel_y), (rel_w, rel_h) in layout:
            raw_x = int(rel_x * screen_width)
            raw_y = int(rel_y * usable_height)
            raw_w = int(rel_w * screen_width)
            raw_h = int(rel_h * usable_height)
            positions.append((raw_x, raw_y, raw_w, raw_h))
        return positions


    def _calc_three(self, layout_configs: list,
                   screen_width: int, screen_height: int, usable_height: int,
                   ) -> list[tuple]:
        numerator, denominator, weight_1 = layout_configs[self.layout_number]
        weight_1 = Fraction(weight_1)
        if not (0 <= weight_1 <= 1):
            weight_1 = Fraction(1, 2)

        weight_2 = 1 - weight_1
        ratio = Fraction(numerator, denominator)

        aux_width = screen_width - (screen_height * ratio)
        left_width = aux_width * weight_1
        center_width = screen_height * ratio
        right_width = aux_width * weight_2

        return [
            (0, self.y_offset, left_width, usable_height),
            (left_width, self.y_offset, center_width, screen_height),
            (left_width + center_width, self.y_offset, right_width, usable_height),
        ]


    def _calc_two(self, layout_configs: list,
                  screen_width: int, screen_height: int, usable_height: int,
                  ) -> list[tuple]:
        numerator, denominator, side = layout_configs[self.layout_number]
        ratio = Fraction(numerator, denominator)

        config = {
            "R": ("Right", screen_height * ratio, 1, screen_height, screen_height),
            "L": ("Left", screen_height * ratio, 0, screen_height, screen_height),
            "CL": ("Center Left", screen_height * ratio, 1, usable_height, screen_height),
            "CR": ("Center Right", screen_height * ratio, 0, screen_height, usable_height),
        }

        side_text, side_width, aot, left_height, right_height = config.get(side, ("", 0, 0, 0, 0))

        if side in ("R", "CL"):
            right_width = side_width
            left_width = (screen_width - right_width) / (2 if side == "CL" else 1)
            left_x = 0
        else:
            left_width = side_width
            right_width = (screen_width - left_width) / (2 if side == "CR" else 1)
            left_x = right_width if side == "CR" else 0

        right_x = left_x + left_width
        return [
            (int(left_x), self.y_offset, int(left_width), int(left_height)),
            (int(right_x), self.y_offset, int(right_width), int(right_height)),
        ]


    def _calc_one(self, layout_configs: list,
                  screen_width: int, screen_height: int, usable_height: int,
                  ) -> list[tuple]:
        _usable_height = usable_height
        numerator, denominator, side = layout_configs[self.layout_number]
        ratio = Fraction(numerator, denominator)

        raw_x = 0
        window_width = screen_height * ratio

        if side == "R":
            raw_x = screen_width - window_width
        elif side == "L":
            raw_x = 0
        elif side == "C":
            raw_x = (screen_width / 2) - (window_width / 2)

        return [(int(raw_x), 0, int(window_width), int(screen_height))]


    def _get_layout_info(self, num_windows: int, layout_configs: list) -> dict:
        config_layout = layout_configs[self.layout_number]

        if num_windows == 4:  # noqa: PLR2004
            return {
                "name_func": lambda: "_".join(
                    self.settings_rows[title].get_values()["name"] for title in self.sorted_window
                ),
                "label": f"{self.preset_label_text} ",
                "aot_flags": [False] * 4,
                "titlebar_defaults": [True] * 4,
            }
        if num_windows == 3:  # noqa: PLR2004
            numerator, denominator, weight_1 = config_layout
            weight_1 = Fraction(weight_1)
            weight_2 = 1 - weight_1
            return {
                "name_func": lambda: clean_window_title(
                    self.settings_rows[self.sorted_window[1]].get_values()["name"], titlecase=True,
                    )[0],
                    "label": (
                        f"{self.preset_label_text} Aspect: {numerator}/{denominator} "
                        f"Left {weight_1.numerator}/{weight_1.denominator} "
                        f"Right {weight_2.numerator}/{weight_2.denominator}"
                        ),
                        "aot_flags": [False, True, False],
                        "titlebar_defaults": [True, False, True],
                        }
        if num_windows == 2:  # noqa: PLR2004
            numerator, denominator, side = config_layout
            config = {
                "R": ("Right", 1), "L": ("Left", 0),
                "CL": ("Center Left", 1), "CR": ("Center Right", 0),
            }
            side_text, aot_idx = config.get(side, ("", 0))
            return {
                "name_func": lambda: clean_window_title(
                    self.settings_rows[self.sorted_window[aot_idx]].get_values()["name"], titlecase=True,
                    )[0],
                    "label": f"{self.preset_label_text}{side_text:10} {numerator}/{denominator}",
                    "aot_flags": [aot_idx == 0, aot_idx == 1],
                    "titlebar_defaults": [aot_idx != 0, aot_idx != 1],
                    }
      # 1 window
        numerator, denominator, side = config_layout
        side_map = {"R": "Right", "L": "Left", "C": "Center", "": "Fullscreen"}
        side_text = side_map.get(side, "Fullscreen")
        return {
            "name_func": lambda: clean_window_title(
                self.settings_rows[self.sorted_window[0]].get_values()["name"], titlecase=True,
            )[0],
            "label": f"{self.preset_label_text}{side_text:10} {numerator}/{denominator}",
            "aot_flags": [True],
            "titlebar_defaults": [False],
        }


    def _apply_layout(self, positions: list[tuple], sorted_windows: list[str],
                    num_windows: int, layout_configs: list) -> None:
        layout_info = self._get_layout_info(num_windows, layout_configs)

        for i, (raw_x, raw_y, raw_w, raw_h) in enumerate(positions):
            title = sorted_windows[i]
            x, y, w, h, tbar = self._calculate_offsets(raw_x, raw_y, raw_w, raw_h, title)

            aot = layout_info["aot_flags"][i]
            titlebar_default = layout_info["titlebar_defaults"][i]

            self.update_row(
                title,
                pos=f"{int(x)},{int(y)}",
                size=f"{int(w)},{int(h)}",
                aot=aot,
                titlebar=resolve_titlebar(override=tbar, default=titlebar_default),
            )

        # Set name and labels
        if not self.edit_mode:
            self.config_name_edit.setText(f"{layout_info['name_func']()}_Preset_{self.layout_number + 1}")

        self.ratio_label.setText(layout_info["label"])


    def auto_position(self, sorted_windows: list[str]) -> None:
        """Automatically set window configuration based on presets."""
        loaded_layouts, def_offsets = self.cfg_man.load_or_create_layouts()
        def_layouts = dict(loaded_layouts)
        self.auto_align_offsets = def_offsets
        screen_width = self.screen_width
        screen_height = self.screen_height - self.y_offset
        taskbar_height = UIConstants.TASKBAR_HEIGHT
        usable_height = screen_height - taskbar_height
        if self.upper_switch.isChecked():
            usable_height = screen_height

        num_windows = len(sorted_windows)
        if str(num_windows) not in def_layouts:
            in_defaults = (
                "" if num_windows not in self.cfg_man.default_layouts else " Try to reset to defaults."
            )
            self.ratio_label.setText(f"No auto-alignment available for {num_windows} windows. {in_defaults}")
            return

        layout_configs = def_layouts[str(num_windows)]
        layout_max = len(layout_configs) - 1
        self.preset_label_text = f"Preset {self.layout_number + 1}/{layout_max + 1}\t"

        # Route to appropriate position calculator
        pos_calculators = {
            1: self._calc_one,
            2: self._calc_two,
            3: self._calc_three,
            4: self._calc_four,
            }

        if num_windows in pos_calculators:
            try:
                positions = pos_calculators[num_windows](layout_configs, screen_width, screen_height, usable_height)
                self._apply_layout(positions, sorted_windows, num_windows, layout_configs)
            except TypeError as e:
                logger.info("Error calculating layout, possible invalid settings file: %s", e)


        self.layout_number = 0 if self.layout_number >= layout_max else self.layout_number + 1
        self.update_layout_frame()


    def _calculate_offsets(self, x: int, y: int, w: int, h: int, title: str) -> tuple[int, int, int, int, str]:
        pure_title = clean_window_title(title)[0]
        if pure_title in self.auto_align_offsets:
            new_x = x + self.auto_align_offsets[pure_title][0]
            new_y = y + self.auto_align_offsets[pure_title][1]
            new_w = w + self.auto_align_offsets[pure_title][2]
            new_h = h + self.auto_align_offsets[pure_title][3]
            titlebar = self.auto_align_offsets[pure_title][4]
            return new_x, new_y, new_w, new_h, titlebar

        return x, y, w, h, ""


    def on_save(self) -> None:
        """Save the config to file."""
        config_data = { title: row.get_values() for title, row in self.settings_rows.items() }
        name = self.config_name_edit.text().strip()
        if not name:
            self.err_msg.setText("ERROR:\nConfig name is required!")
            self.err_msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            self.err_msg.show()
            return

        if name.lower() == "no configs found":
            self.err_msg.setText("ERROR:\nInvalid config name!")
            self.err_msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            self.err_msg.show()
            return

        apply_order = self.apply_order or []
        apply_order_widget = self.layout_container.findChild(QListWidget)
        if apply_order_widget:
            apply_order = [ apply_order_widget.item(i).text() for i in range(apply_order_widget.count()) ]

        ignore_list = self.ignore_edit.text().strip().split(",") or []

        if self.save_callback(name, config_data, apply_order, ignore_list):
            if self.refresh_callback:
                self.refresh_callback(name)
            self.accept()


class WindowSettingsRow(QWidget):
    """Create a row for the create config settings window."""

    def __init__(self, title: str, values: dict) -> None:
        """Initialize variables."""
        super().__init__()
        self.layout = QHBoxLayout(self)

        pos = values.get("position", "0,0")
        size = values.get("size", "100,100")
        aot = to_bool(val=values.get("always_on_top", "false"))
        titlebar = to_bool(val=values.get("titlebar", "true"))
        name = values.get("name", title)
        self.exe = values.get("exe", "")

        # Larger name input
        self.name_edit = QLineEdit(name)
        self.name_edit.setMinimumWidth(150)

        # Smaller pos/size inputs
        self.pos_edit = QLineEdit(pos)
        self.pos_edit.setFixedWidth(80)
        self.size_edit = QLineEdit(size)
        self.size_edit.setFixedWidth(80)

        self.aot_cb = QCheckBox("On Top")
        self.aot_cb.setChecked(bool(aot))
        self.titlebar_cb = QCheckBox("Titlebar")
        self.titlebar_cb.setChecked(bool(titlebar))
        self.process_priority_cb = QCheckBox("Process priority")
        self.process_priority_cb.setChecked(False)

        self.layout.addWidget(self.name_edit, stretch=2)
        self.layout.addWidget(QLabel("Pos:"))
        self.layout.addWidget(self.pos_edit, stretch=0)
        self.layout.addWidget(QLabel("Size:"))
        self.layout.addWidget(self.size_edit, stretch=0)
        self.layout.addWidget(self.aot_cb)
        self.layout.addWidget(self.titlebar_cb)
        self.layout.addWidget(self.process_priority_cb)

    def get_values(self) -> dict:
        """Return dict with window values."""
        return {
            "name": self.name_edit.text().strip(),
            "position": self.pos_edit.text(),
            "size": self.size_edit.text(),
            "always_on_top": self.aot_cb.isChecked(),
            "titlebar": self.titlebar_cb.isChecked(),
            "process_priority": self.process_priority_cb.isChecked(),
            "exe": self.exe,
        }

    def set_values(self,  # noqa: PLR0913
                   name: str,
                   pos: str,
                   size: str,
                   *,
                   aot: bool,
                   titlebar: bool,
                   process_priority: bool = False,
                   ) -> None:
        """Update the settings row values."""
        self.name_edit.setText(name)
        self.pos_edit.setText(pos)
        self.size_edit.setText(size)
        self.aot_cb.setChecked(aot)
        self.titlebar_cb.setChecked(titlebar)
        self.process_priority_cb.setChecked(process_priority)


# Helper function
def resolve_titlebar(*, override: str, default: bool) -> bool:
    """Determine titlebar setting based on override value."""
    if override == "on":
        return False
    if override == "off":
        return True
    return default

