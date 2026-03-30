# src/gui/pyside_gui_manager.py
"""PySide GUI manager for the Ultrawide Window Positioner application."""

from __future__ import annotations

import logging
import sys
import time
from configparser import ConfigParser
from dataclasses import asdict
from typing import TYPE_CHECKING

import global_hotkeys
import hdrcapture
from PySide6.QtCore import QObject, QRect, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QFont, QIcon, QImage, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.config_dialog import ConfigDialog
from gui.layout_preview import ScreenLayoutWidget
from gui.workers import GenericWorker
from uwp_config import ConfigManager, get_ignore_list

# Local imports
from uwp_constants import Colors, Fonts, Messages, UIConstants
from uwp_utils import (
    WindowInfo,
    clean_window_title,
    config_to_metrics,
    format_coords,
    get_data_path,
    get_version,
    get_window_info,
    invert_hex_color,
    parse_coords,
    run_clean_subprocess,
)
from uwp_window import WindowManager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

text_normal = QFont(Fonts.TEXT_NORMAL[0], Fonts.TEXT_NORMAL[1], QFont.Weight.Normal)
text_small = QFont(Fonts.TEXT_SMALL[0], Fonts.TEXT_SMALL[1], QFont.Weight.Normal)

class PysideGuiManager(QMainWindow):
    """PySide-based GUI manager for the Ultrawide Window Positioner application."""

    def __init__(
            self,
            *,
            base_path: Path = "",
    ) -> None:
        """Initialize the main PySide GUI window."""
        super().__init__()
        self.screenshot_in_progress = None
        self.pending_delete = None
        self.scr_reapply = None
        self.del_msg = QMessageBox(self)
        self.del_msg.setWindowTitle("Confirm delete")
        self.del_msg.finished.connect(self._handle_delete_result)

        self.thread_pool = QThreadPool.globalInstance()
        self.reapply_in_progress = None

        self.capture_session = None
        self.window_capture = None
        self.compact = None
        self.base_path = base_path

        self.apply_thread_running = False

        self.config = None
        self.config_files = None
        self.config_active = False
        self.applied_config = None
        self.applied_config_name = None

        self.style_dark = True

        self.timer = None
        self.reapply = None
        self.reapply_paused = None

        self.managed_label = None
        self.managed_text = None
        self.colors = Colors()

        self._init_managers()

        self.settings = self.cfg_man.load_settings()

        low_ignore_list = [item.lower() for item in self.settings.ignored_windows]
        self.win_man.ignored_windows = low_ignore_list

        self._init_screen()
        self._init_ui_containers()
        self._setup_ui()

        self._apply_snap_selection()
        self.reapply_timer()
        self.managed_widget.installEventFilter(self)

        global_hotkeys.register_hotkey(self.settings.hotkey, self.toggle_always_on_top, None)
        global_hotkeys.start_checking_hotkeys()

        # Set window title with version
        version = get_version()
        if version:
            self.setWindowTitle(f"Ultrawide Window Positioner v{version}")
        else:
            self.setWindowTitle("Ultrawide Window Positioner")

        self.setWindowIcon(QIcon(str(get_data_path("Icon.png"))))

    # ---------------- Helper methods ----------------
    def _init_managers(self) -> None:
        """Initialize manager objects and related shortcuts."""
        self.cfg_man = ConfigManager(self.base_path)
        self.win_man = WindowManager()
        if not self.win_man.validate_state():
            logger.warning("Initial window manager state is invalid.")

        self.assets_dir: Path = self.base_path / "assets"

        self.svg_path = get_data_path("checkmark.svg")

    def _init_screen(self) -> None:
        """Initialize screen resolution variables."""
        screens = QApplication.screens()
        total_rect = QRect()
        for screen in screens:
            geo = screen.geometry()
            total_rect = total_rect.united(geo)
        self.res_x = total_rect.width()
        self.res_y = total_rect.height()
        self.y_offset = self.res_y // 2

    def _init_ui_containers(self) -> None:
        """Initialize main UI containers and layout."""
        central = QWidget()
        self.setCentralWidget(central)
        central.setContentsMargins(0, 0, 0, 0)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

    def _setup_ui(self) -> None:
        """Build the UI, apply theme, connect callbacks."""
        self._build_ui()
        self.toggle_compact(startup=True)
        self._apply_theme()
        self._connect_callbacks()

    def _apply_snap_selection(self) -> None:
        """Set initial snap radio button based on snap value."""
        snap_left = 1
        snap_right = 2
        if self.settings.snap == snap_left:
            self.left_radio.setChecked(True)
        elif self.settings.snap == snap_right:
            self.right_radio.setChecked(True)
        else:
            self.center_radio.setChecked(True)

    def eventFilter(self, source: QObject, event: QWheelEvent) -> bool:  # noqa: N802
        """Catch mouse wheel events on managed windows widget."""
        if source is self.managed_widget and event.type() == QWheelEvent:
            combo = self.combo_box
            delta = event.angleDelta().y()
            current = combo.currentIndex()
            new_index = max(0, current - 1) if delta > 0 else min(combo.count() - 1, current + 1)
            combo.setCurrentIndex(new_index)

            return True
        return super().eventFilter(source, event)

    def get_geometry_and_minsize(self) -> tuple[int, int, int, int]:
        """Get the sizes needed to set geometry and minsize."""
        compact_height_factor = 1
        if self.settings.compact:
            width = UIConstants.COMPACT_WIDTH
            height = UIConstants.COMPACT_HEIGHT
            min_width = UIConstants.COMPACT_WIDTH
            min_height = UIConstants.COMPACT_HEIGHT * compact_height_factor
        else:
            width = UIConstants.WINDOW_WIDTH
            height = UIConstants.WINDOW_HEIGHT
            min_width = UIConstants.WINDOW_MIN_WIDTH
            min_height = UIConstants.WINDOW_MIN_HEIGHT

        return width, height, min_width, min_height

    def toggle_elements(self, *, compact: bool, min_width: int) -> None:
        """Hide or show elements for compact/full mode."""
        hidden_elements = [
            self.layout_frame,
            self.theme_switch,
            self.filter_switch,
            self.edit_config_button,
            self.image_folder_button,
            self.screenshot_button,
            self.settings.details_switch,
            self.toggle_images_switch,
            self.aot_label,
            self.spacer_1,
            self.spacer_2,
            self.left_radio,
            self.center_radio,
            self.right_radio,
            self.settings.snap_label,
        ]

        resized_buttons = [
            self.apply_config_button,
            self.create_config_button,
            self.delete_config_button,
            self.detect_config_button,
            self.toggle_compact_button,
            self.edit_config_button,
            self.image_folder_button,
            self.screenshot_button,
        ]

        self.managed_widget.setVisible(compact)

        if compact:
            for button in resized_buttons:
                button.setFixedHeight(30)
            self.combo_box.setFixedWidth(min_width - 20)
        else:
            for button in resized_buttons:
                button.setFixedHeight(50)
            self.combo_box.setFixedWidth(int(min_width / 2))

        for widget in hidden_elements:
            if compact:
                widget.hide()
            else:
                widget.show()

        if compact:
            self.b1.setDirection(QBoxLayout.Direction.TopToBottom)  # vertical
            self.b2.setDirection(QBoxLayout.Direction.TopToBottom)  # vertical
        else:
            self.b1.setDirection(QBoxLayout.Direction.LeftToRight)  # horizontal
            self.b2.setDirection(QBoxLayout.Direction.LeftToRight)  # horizontal

    def update_managed_text(self, lines: list, aot_flags: list, missing: list) -> None:
        """Update the text for the managed windows view (for compact mode)."""
        self.managed_text.setReadOnly(False)
        self.managed_text.clear()

        for i, line in enumerate(lines):
            if aot_flags[i]:
                self.managed_text.setTextColor(self.colors.TEXT_ALWAYS_ON_TOP)
            else:
                self.managed_text.setTextColor(self.colors.TEXT_NORMAL)

            if missing[i]:
                self.managed_text.setTextColor("#777777")

            self.managed_text.append(line)

        self.managed_text.setReadOnly(True)

    # ---------------- Build the GUI ----------------

    def _build_ui(self) -> None:
        """Build the main PySide GUI layout."""
        width, height, min_width, min_height = self.get_geometry_and_minsize()

        self._build_header()
        self._build_combo_row(min_width)
        self._build_managed_area()
        self._build_layout_preview()
        self._build_status_row()
        self._build_buttons_area()
        self._build_images_and_snap_row()

    # ---------------- Helper methods ----------------

    def _build_header(self) -> None:
        """Create the header layout with resolution label."""
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(15, 0, 15, 0)
        header_layout.setSpacing(10)

        self.resolution_label = QLabel(f"{self.res_x} x {self.res_y}", self)

        header_layout.addWidget(self.resolution_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.main_layout.addLayout(header_layout)

    def _build_combo_row(self, min_width: int) -> None:
        """Create combo box row with theme switch."""
        combo_layout = QHBoxLayout()
        combo_layout.setContentsMargins(10, 0, 10, 0)
        combo_layout.setSpacing(0)
        width = min_width - 20 if self.settings.compact else min_width / 2

        self.combo_box = QComboBox(self)
        self.combo_box.setFixedWidth(width)

        self.filter_switch = QCheckBox("Filter configs", self)

        combo_layout.addWidget(self.combo_box, alignment=Qt.AlignmentFlag.AlignLeft)
        combo_layout.addWidget(self.filter_switch, alignment=Qt.AlignmentFlag.AlignLeft)

        self.theme_switch = QCheckBox("light / dark", self)
        self.theme_switch.setChecked(False)

        right_layout = QHBoxLayout()
        right_layout.addWidget(self.theme_switch, alignment=Qt.AlignmentFlag.AlignRight)
        combo_layout.addLayout(right_layout)

        self.main_layout.addLayout(combo_layout)

    def _build_managed_area(self) -> None:
        """Create managed windows area with label and text edit."""
        self.managed_widget = QWidget(self)
        self.managed_widget.setVisible(self.settings.compact)

        mf_layout = QVBoxLayout(self.managed_widget)
        mf_layout.setContentsMargins(10, 0, 10, 0)

        self.managed_label = QLabel("Managed windows:", self)
        self.managed_text = QTextEdit(self)

        self.managed_text.setFixedHeight(80)

        mf_layout.addWidget(self.managed_label, alignment=Qt.AlignmentFlag.AlignLeft)
        mf_layout.addWidget(self.managed_text)

        self.main_layout.addWidget(self.managed_widget)

    def _build_layout_preview(self) -> None:
        """Create layout container for screen preview."""
        lc_layout = QVBoxLayout()
        lc_layout.setContentsMargins(10, 5, 10, 0)

        self.layout_frame = ScreenLayoutWidget(
            self,
            self.res_x,
            self.res_y,
            windows=[],
            assets_dir=self.assets_dir,
            app_settings=self.settings,
        )
        lc_layout.addWidget(self.layout_frame, 1)
        self.main_layout.addLayout(lc_layout, 1)

    def _build_status_row(self) -> None:
        """Create a status row with info label."""
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(20, 0, 20, 0)

        self.info_label = QLabel("", self)

        status_layout.addWidget(self.info_label)

        self.main_layout.addLayout(status_layout)

    def _build_buttons_area(self) -> None:
        """Create buttons rows for config actions and AOT controls."""
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(10, 5, 10, 5)

        # Row 1: config buttons
        self.b1 = QHBoxLayout()

        self.apply_config_button = QPushButton("Apply config", self)
        self.create_config_button = QPushButton("Create config", self)
        self.edit_config_button = QPushButton("Edit config", self)
        self.delete_config_button = QPushButton("Delete config", self)

        self.b1.addWidget(self.apply_config_button)
        self.b1.addWidget(self.create_config_button)
        self.b1.addWidget(self.edit_config_button)
        self.b1.addWidget(self.delete_config_button)

        btn_layout.addLayout(self.b1)

        # Row 2: folder / screenshot / images
        self.b2 = QHBoxLayout()

        self.screenshot_button = QPushButton("Take screenshots", self)
        self.image_folder_button = QPushButton("Open image folder", self)
        self.detect_config_button = QPushButton("Detect config", self)
        self.toggle_compact_button = QPushButton("Toggle compact", self)

        self.screenshot_button.setEnabled(True)
        self.image_folder_button.setEnabled(True)

        self.b2.addWidget(self.screenshot_button)
        self.b2.addWidget(self.image_folder_button)
        self.b2.addWidget(self.detect_config_button)
        self.b2.addWidget(self.toggle_compact_button)

        btn_layout.addLayout(self.b2)

        # Row 3: AOT / toggle / detect
        aot_l = QHBoxLayout()
        self.aot_button = QPushButton("Toggle AOT", self)
        self.aot_label = QLabel(Messages.ALWAYS_ON_TOP_DISABLED, self)

        self.aot_button.setEnabled(False)
        self.aot_button.setFixedHeight(30)
        self.aot_label.setContentsMargins(10, 0, 10, 0)

        self.spacer_1 = QPushButton("")
        self.spacer_1.setFixedHeight(30)

        self.spacer_2 = QPushButton("")
        self.spacer_2.setFixedHeight(30)

        aot_l.addWidget(self.aot_button)
        aot_l.addWidget(self.aot_label)
        aot_l.addWidget(self.spacer_1)
        aot_l.addWidget(self.spacer_2)

        btn_layout.addLayout(aot_l)
        self.main_layout.addLayout(btn_layout)

        aot_bottom = QHBoxLayout()

        self.reapply_pause_label = QLabel("", self)
        self.reapply_pause_label.setContentsMargins(10, 0, 10, 0)
        aot_bottom.addWidget(self.reapply_pause_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.settings.snap_label = QLabel("Application open position:", self)
        self.settings.snap_label.setContentsMargins(10, 0, 50, 0)
        aot_bottom.addWidget(self.settings.snap_label, alignment=Qt.AlignmentFlag.AlignRight)

        self.main_layout.addLayout(aot_bottom)

    def update_reapply_label(self) -> None:
        """Update the text and color of the reapply status label."""
        reapply_txt = "Reapply "
        if self.reapply_paused:
            reapply_txt += "PAUSED"
            self.reapply_pause_label.setStyleSheet(f"color: {self.colors.TEXT_NOTICE}")
        elif self.reapply and self.config_active:
            reapply_txt += "ACTIVE"
            self.reapply_pause_label.setStyleSheet(f"color: {self.colors.TEXT_ALWAYS_ON_TOP}")
        else:
            reapply_txt += "INACTIVE"
            self.reapply_pause_label.setStyleSheet(f"color: {self.colors.TEXT_NORMAL}")
        self.reapply_pause_label.setText(reapply_txt)

    def _build_images_and_snap_row(self) -> None:
        """Create checkboxes for auto re-apply, details, images, and snap selection."""
        img_l = QHBoxLayout()
        img_l.setContentsMargins(10, 10, 10, 10)
        img_l.setSpacing(20)

        self.auto_apply_switch = QCheckBox("Auto re-apply", self)
        self.settings.details_switch = QCheckBox("Show window details", self)
        self.toggle_images_switch = QCheckBox("Images", self)

        self.settings.details_switch.setChecked(self.settings.details)
        self.toggle_images_switch.setChecked(self.settings.use_images)

        img_l.addWidget(self.auto_apply_switch)
        img_l.addWidget(self.settings.details_switch)
        img_l.addWidget(self.toggle_images_switch)
        img_l.addStretch()  # push snap group right

        # Snap selection
        snap_l = QHBoxLayout()
        snap_l.setSpacing(10)

        radio_width = 75
        self.left_radio = QRadioButton("Left", self)
        self.center_radio = QRadioButton("Center", self)
        self.right_radio = QRadioButton("Right", self)
        for radio in [self.left_radio, self.center_radio, self.right_radio]:
            radio.setFixedWidth(radio_width)

        self.settings.snap_group = QButtonGroup(self)
        self.settings.snap_group.addButton(self.left_radio, 1)
        self.settings.snap_group.addButton(self.center_radio, 0)
        self.settings.snap_group.addButton(self.right_radio, 2)

        for radio in [self.left_radio, self.center_radio, self.right_radio]:
            snap_l.addWidget(radio)

        img_l.addLayout(snap_l)
        self.main_layout.addLayout(img_l)

    # noinspection DuplicatedCode
    def _connect_callbacks(self) -> None:
        # Drop-down menu
        self.combo_box.currentIndexChanged.connect(self.on_config_select)

        # Buttons
        self.apply_config_button.clicked.connect(self.apply_settings)
        self.create_config_button.clicked.connect(self.create_config_ui)
        self.edit_config_button.clicked.connect(self.edit_config_dialog)
        self.delete_config_button.clicked.connect(self.delete_config)

        self.screenshot_button.clicked.connect(self.take_screenshot)
        self.image_folder_button.clicked.connect(self.open_image_folder)
        self.detect_config_button.clicked.connect(self.detect_config)
        self.toggle_compact_button.clicked.connect(self.toggle_compact)

        self.aot_button.clicked.connect(self.toggle_always_on_top)

        # Switches
        self.auto_apply_switch.stateChanged.connect(self._on_reapply_toggle)
        self.settings.details_switch.stateChanged.connect(self._on_details_toggle)
        self.toggle_images_switch.stateChanged.connect(self._on_images_toggle)

        self.filter_switch.stateChanged.connect(self.update_config_list)
        self.theme_switch.stateChanged.connect(self._on_theme_toggle)

        # Radio buttons
        self.settings.snap_group.buttonToggled.connect(self._on_snap_toggle)

    # ------------- Theme & toggles -------------

    def _apply_theme(self) -> None:
        font_size = text_small.pointSize() if self.settings.compact else text_normal.pointSize()
        self.setStyleSheet(f"""
            QWidget {{
                background: {self.colors.BACKGROUND};
                color: {self.colors.TEXT_NORMAL};
                padding: 0px;
                border: 0px solid {self.colors.BORDER_COLOR};
                font-size: {font_size}pt;
                }}
            QFrame {{
                background: {self.colors.BACKGROUND};
                padding: 0px;
                border: 0px solid {self.colors.BORDER_COLOR};
                }}
            QComboBox {{
                background: {self.colors.BUTTON_NORMAL};
                border-radius: 0px;
                border: 2px solid {self.colors.BORDER_COLOR};
                padding: 5px;
            }}
            QComboBox::drop-down {{
                border: 0px solid {self.colors.BORDER_COLOR};
            }}
            QComboBox::hover {{
                background: {self.colors.BUTTON_HOVER};
            }}
            QPushButton {{
                background: {self.colors.BUTTON_NORMAL};
                border-radius: 10px;
                border: 2px solid {self.colors.BORDER_COLOR};
                padding: 5px;
                height: 54px;
            }}
            QPushButton:hover {{
                background: {self.colors.BUTTON_HOVER};
            }}
            QPushButton:disabled {{
                background: {self.colors.BUTTON_DISABLED};
                color: #888;
            }}
            QLineEdit, QTextEdit, QComboBox {{
                background: {self.colors.BUTTON_NORMAL};
                border-radius: 0px;
                border: 2px solid {self.colors.BORDER_COLOR};
                padding: 5px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid {self.colors.BORDER_COLOR};
                background: {self.colors.BUTTON_NORMAL};
                color: palette(text);
                font-weight: bold;
                font-size: 12px;
                text-align: center;
            }}
            QCheckBox::indicator:hover {{
                background: {self.colors.BUTTON_HOVER};
            }}
            QCheckBox::indicator:checked {{
                background: {self.colors.BUTTON_ACTIVE};
                color: palette(highlighted-text);
                image: url({self.svg_path});
            }}
            QCheckBox::indicator:checked:hover {{
                background: {self.colors.BUTTON_ACTIVE_HOVER};
            }}
            QRadioButton::indicator:unchecked:hover {{
                background: {self.colors.BUTTON_HOVER};
            }}
            QRadioButton::indicator:checked {{
                border: 1px solid {self.colors.BORDER_COLOR};
                background: {self.colors.BUTTON_ACTIVE};
                border-radius: 10px;
                width: 18px;
                height: 18px;
            }}
            QRadioButton::indicator:checked:hover {{
                background: {self.colors.BUTTON_ACTIVE_HOVER};
            }}
            QRadioButton::indicator:unchecked {{
                border: 1px solid {self.colors.BORDER_COLOR};
                background: {self.colors.BUTTON_NORMAL};
                border-radius: 10px;
                width: 18px;
                height: 18px;
            }}
        """)
        self.spacer_1.setStyleSheet(f"background:{self.colors.BACKGROUND}; border: none")
        self.spacer_2.setStyleSheet(f"background:{self.colors.BACKGROUND}; border: none")

        # Re-apply dynamic states after theme reset
        self.format_apply_button(selected_config_shortname=None)


    def format_apply_button(self, selected_config_shortname: str | None) -> None:
        """Set the state and color for apply and reset buttons."""
        btn_color = self.colors.BUTTON_ACTIVE if self.config_active else self.colors.BUTTON_NORMAL
        hover_color = self.colors.BUTTON_ACTIVE_HOVER if self.config_active else self.colors.BUTTON_HOVER
        self.aot_button.setEnabled(bool(self.win_man.topmost_windows))

        self.apply_config_button.setStyleSheet(f"""
            QPushButton {{
                background: {btn_color};
                border-radius: 10px;
                border: 2px solid {self.colors.BORDER_COLOR};
                padding: 5px;
                height: 54px;
            }}
            QPushButton:hover {{
                background: {hover_color};
            }}
            """)

        if self.config_active:
            self.apply_config_button.setText("Reset active config")
            self.info_label.setText(f"Active: {
                selected_config_shortname if selected_config_shortname
                else self.applied_config_name
            }")
        else:
            self.apply_config_button.setText("Apply config")
            self.info_label.setText("")

    def invert_colors(self) -> None:
        """Invert all colors in the color list."""
        for attr in dir(self.colors):
            if attr.isupper():
                value = getattr(self.colors, attr)
                if isinstance(value, str):
                    setattr(self.colors, attr, invert_hex_color(value))

    def _save_settings(self) -> None:
        """Save GUI settings."""
        self.cfg_man.save_settings(self.settings)

    def reapply_timer(self) -> None:
        """Timer for auto reapply."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.auto_reapply)
        self.timer.start(500)

    def setup_managed_text(self) -> None:
        """Show or hide the managed windows frame for compact mode."""
        self.managed_text.setFixedHeight(80)

    def set_layout_frame(self, windows: list[WindowInfo]) -> None:
        """Layout frame population."""
        self.layout_frame.windows = windows
        self.layout_frame.update()

    def update_config_list(self, config: str | None = None) -> None:
        """Get new config list from disk."""
        files = self.cfg_man.list_config_files()
        self.config_files = self._filter_combo(files)

        if self.config_files:
            names = list(self.config_files.keys())
            if isinstance(config, str):
                cfg = config
            else:
                self.win_man.update_window_list()
                cfg = self.cfg_man.detect_default_config(self.win_man.all_windows.keys())
            self.set_combo_values(names, cfg)
            self.on_config_select()
        else:
            self.set_combo_values(["No configs found"], "No configs found")
            self.on_config_select()

    def set_combo_values(self, values: list, current: str) -> None:
        """Update the values for the combobox."""
        self.combo_box.clear()
        self.combo_box.addItems(values)
        if current:
            self.combo_box.setCurrentText(current)

    def update_window_layout(self, config: ConfigParser, missing_windows: list) -> None:
        """Update the layout."""
        windows = self.win_man.get_windows_for_layout(config, missing_windows)
        self.set_layout_frame(windows)

    def update_managed_windows_list(self, config: ConfigParser, missing_windows: list) -> None:
        """Update the elements in the managed windows list used in compact mode."""
        if not hasattr(self, "managed_text"):
            self.setup_managed_text()

        lines = []
        aot_lines = []
        missing_lines = []

        if config:
            for section in config.sections():
                is_aot = config.getboolean(section, "always_on_top", fallback=False)
                title = f"* {section} * (AOT)" if is_aot else section
                missing = section in missing_windows
                if len(title) > UIConstants.WINDOW_TITLE_MAX_LENGTH:
                    title = title[:UIConstants.WINDOW_TITLE_MAX_LENGTH] + "..."
                lines.append(title)
                aot_lines.append(is_aot)
                missing_lines.append(missing)

        self.update_managed_text(lines, aot_lines, missing_lines)

    def verify_window_data(self, config: ConfigParser, matching_windows: list) -> list:
        """Compare the metrics of the windows in the config with the actual windows and return a list of results."""
        compare_results = []
        for match in matching_windows:
            results = {}
            metrics = self.win_man.get_window_metrics(match["hwnd"])
            if not metrics:
                continue

            section = match["short_name"]
            settings_metrics = config_to_metrics(config, section)

            win_met = {k: v for k, v in asdict(metrics).items() if k != "apply_order"}
            cfg_met = {k: v for k, v in asdict(settings_metrics).items() if k != "apply_order"}

            results["name"] = match["name"]
            results["hwnd"] = match["hwnd"]
            results["short_name"] = match["short_name"]
            results["identical"] = win_met == cfg_met
            compare_results.append(results)

        return compare_results

    @staticmethod
    def capture_window(window: dict, assets_dir: Path) -> None:
        """Take a screenshot of the window using hdrcapture and Qt for processing."""
        assets_dir.mkdir(parents=True, exist_ok=True)
        window_name = window["short_name"]
        max_size = QSize(1024, 1024)

        with hdrcapture.capture.window(hwnd=window["hwnd"]) as cap:
            frame = cap.capture()
            img_data = frame.ndarray()

            img = QImage(
                img_data.data,
                frame.width,
                frame.height,
                QImage.Format.Format_ARGB32,
            )

            if not img.isNull():
                if img.width() > max_size.width() or img.height() > max_size.height():
                    img = img.scaled(
                        max_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

                ratio = frame.width / frame.height

                ratio_suffixes = [
                    (3.0, "32-9"),
                    (2.0, "21-9"),
                    (1.5, "16-9"),
                    (1.2, "4-3"),
                    (0.85, "square"),
                    (0.65, "3-4"),
                    (0.5, "9-16"),
                    (0.35, "9-21"),
                ]

                suffix = next((s for threshold, s in ratio_suffixes if ratio > threshold), "9-32")

                save_path = assets_dir / f"{window_name.replace(' ', '_')}_{suffix}.png"
                # noinspection PyTypeChecker
                img.save(str(save_path), "PNG")
            else:
                logger.error("Failed to create QImage from mss buffer for %s", window_name)

    # Button actions
    def create_config_ui(self) -> None:
        """Create config popup window for creating configs."""
        self.win_man.update_window_list()
        sorted_windows = sorted(self.win_man.all_windows.keys())
        if not sorted_windows:
            return
        dlg = ConfigDialog(
            self,
            sorted_windows,
            self.cfg_man.save_window_config,
            self.win_man.collect_window_settings,
            self.update_config_list,
            self.res_x, self.res_y, self.y_offset,
            assets_dir=self.assets_dir,
        )
        dlg.exec()

    def delete_config(self) -> None:
        """Delete the currently selected config."""
        current_name = self.combo_box.currentText()

        if not current_name or current_name == "No configs found":
            return

        self.del_msg.setText(f"Delete config: '{current_name}'?")
        self.del_msg.setInformativeText("This can not be undone.")
        self.del_msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        self.del_msg.setDefaultButton(QMessageBox.StandardButton.Cancel)

        self.pending_delete = current_name

        self.del_msg.show()

    def _handle_delete_result(self, result: int) -> None:
        if result == QMessageBox.StandardButton.Ok and hasattr(self, "pending_delete"):
            if self.cfg_man.delete_config(self.pending_delete):
                self.update_config_list()
                del self.pending_delete
            elif self.pending_delete:
                QMessageBox.critical(self, "Error", "Failed to delete config. See debug log for details.")

    def edit_config_dialog(self) -> None:
        """Edit the current config."""
        # Get current config windows and settings
        config_name = self.combo_box.currentText()
        if not config_name or config_name.lower() == "no configs found":
            return

        def build_settings(title: str) -> dict:
            exe = ""
            window_settings = self.win_man.collect_window_settings(title)
            if window_settings:
                exe = window_settings.get("exe", "")

            sec = self.config[title]
            pos_x, pos_y = parse_coords(sec.get("position", "0,0"))
            w, h = parse_coords(sec.get("size", "0,0"))

            return {
                "position": format_coords(max(-7, pos_x), max(-31, pos_y)),
                "size": format_coords(max(250, w), max(250, h)),
                "always_on_top": sec.get("always_on_top", "false").lower(),
                "titlebar": sec.get("titlebar", "true").lower(),
                "original_title": title,
                "name": clean_window_title(title)[0],
                "exe": exe,
            }

        dlg = ConfigDialog(
            self,
            self.config.sections(),
            self.cfg_man.save_window_config,
            build_settings,
            self.update_config_list,
            self.res_x, self.res_y, self.y_offset,
            assets_dir=self.assets_dir,
            edit_mode=True,
            config_name=config_name,
        )
        dlg.exec()

    def apply_settings(self, *, reapply: bool = False) -> None:
        """Triggered by button click or screenshot logic."""
        if self.apply_thread_running:
            return

        self.apply_thread_running = True

        # We pass the logic function and its arguments to the worker
        kwargs = {"reapply": reapply}
        worker = GenericWorker(self._apply_settings_logic, **kwargs)

        # Connect the cleanup/UI update to run on the Main Thread when done
        worker.signals.finished.connect(self._on_apply_finished)

        self.thread_pool.start(worker)

    # Opening the folder containing the image files
    def open_image_folder(self) -> None:
        """Open the image folder in File Explorer."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            kwargs = {"check": True}
            run_clean_subprocess(["C:/windows/explorer", self.assets_dir], **kwargs)
        else:
            kwargs = {"check": True}
            run_clean_subprocess(["xdg-open", str(self.assets_dir)], check_output=False, **kwargs)

    def toggle_compact(self, startup: int = 0) -> None:
        """Toggle between compact and full mode."""
        if not startup:
            self.settings.compact = not self.settings.compact
            self._save_settings()

        if self.settings.compact:
            self.toggle_compact_button.setText("Full mode")
            self.aot_button.setText("AOT")
            self.detect_config_button.setText("Detect")
        else:
            self.toggle_compact_button.setText("Compact mode")
            self.aot_button.setText(f"Toggle AOT ({self.settings.hotkey})")
            self.detect_config_button.setText("Detect config")

        width, height, min_width, min_height = self.get_geometry_and_minsize()
        self.toggle_elements(compact=self.settings.compact, min_width=min_width)
        self.setMinimumSize(min_width, min_height)
        self._position_app_window()
        self.on_config_select()
        self._apply_theme()


    def _position_app_window(self) -> None:
        width, height, _, _ = self.get_geometry_and_minsize()
        snap_left = 1
        snap_right = 2
        if self.settings.snap == 0:
            pos_x = (self.res_x // 2) - (width // 2)
        elif self.settings.snap == snap_left:
            pos_x = 0
        elif self.settings.snap == snap_right:
            pos_x = self.res_x - width
        else:
            pos_x = 100
        pos_y = (self.res_y // 2) - (height // 2)

        self.setGeometry(pos_x, pos_y, width, height)

    def detect_config(self) -> None:
        """Detect the best matching config based on available windows."""
        default_config = self.cfg_man.detect_default_config(list(self.win_man.all_windows.keys()))
        if default_config:
            self.update_config_list(default_config)

    # Switch actions
    def _filter_combo(self, files: dict) -> dict:
        if not self.filter_switch.isChecked():
            return files

        filtered_files = {}
        for name, file in files.items():
            config = self.cfg_man.load_config(file)
            if not config:
                continue

            matching_windows, _ = self.get_matching_and_missing_windows(config)
            if matching_windows:
                filtered_files[name] = file

        return filtered_files

    def _on_theme_toggle(self, state: int) -> None:
        # True -> light; False -> dark
        self.style_dark = not bool(state)
        self.invert_colors()
        self._apply_theme()

    def _on_reapply_toggle(self) -> None:
        self.reapply_paused = False
        self.reapply = self.auto_apply_switch.isChecked()

    def _on_details_toggle(self) -> None:
        self.settings.details = self.settings.details_switch.isChecked()
        self._save_settings()
        if self.layout_frame:
            self.layout_frame.window_details = self.settings.details
            self.layout_frame.update()

    def _on_images_toggle(self) -> None:
        self.settings.use_images = self.toggle_images_switch.isChecked()
        self._save_settings()
        if self.layout_frame:
            self.layout_frame.use_images = self.settings.use_images
            self.layout_frame.update()

    # Radio button actions

    def _on_snap_toggle(self, button: QRadioButton) -> None:
        if button == self.left_radio:
            self.settings.snap = 1
        elif button == self.center_radio:
            self.settings.snap = 0
        elif button == self.right_radio:
            self.settings.snap = 2

        self._position_app_window()
        self._save_settings()

    # Drop-down menu action

    def on_config_select(self) -> None:
        """Load new config when selecting an item from the dropdown."""
        combo_value = self.combo_box.currentText()
        if combo_value:
            matching, missing = [], []
            if combo_value in self.config_files:
                cfg = self.config_files[combo_value]
                self.config = self.cfg_man.load_config(cfg)
                matching, missing = self.get_matching_and_missing_windows(self.config)

            scr_btn_enabled = (not self.applied_config or self.config == self.applied_config) and bool(matching)
            self.screenshot_button.setEnabled(scr_btn_enabled)
        else:
            self.config = None
            missing = []

        if not self.settings.compact:
            self.update_window_layout(self.config, missing)
        else:
            self.update_managed_windows_list(self.config, missing)

    def update_always_on_top_status(self) -> int | None:
        """Change the status label text to reflect current number of AOT windows."""
        count = None

        aot_windows = self.win_man.topmost_windows
        if aot_windows:
            count = 0
            for hwnd in aot_windows:
                info = get_window_info(hwnd)
                if info and info.aot:
                    count += 1

        if count == 0:
            self.aot_button.setStyleSheet(f"background-color: {self.colors.BUTTON_NOTICE}; height: 20px")
        else:
            self.aot_button.setStyleSheet(f"background-color: {self.colors.BUTTON_NORMAL}; height: 20px")

        if count is None:
            self.aot_label.setText("AOT: None")
        else:
            self.aot_label.setText(f"AOT: {count} window{'s' if count > 1 else ''}")

        return count

    def _apply_settings_logic(self, *, reapply: bool) -> None:
        self.win_man.remove_invalid_windows()

        if not reapply:
            cfg = self.combo_box.currentText()
            shortname = self.toggle_active_config(cfg)
            self.applied_config_name = shortname

        if self.applied_config:
            matching_windows, _ = self.get_matching_and_missing_windows(self.applied_config)

            for window in matching_windows:
                hwnd = window["hwnd"]
                self.win_man.add_managed_window(hwnd)

                settings = config_to_metrics(self.applied_config, window["short_name"])
                if settings:
                    self.win_man.apply_window_config(settings, hwnd)
                else:
                    logger.info("Failed to apply settings to %s", window)

        if not self.win_man.validate_state():
            logger.warning("Some windows failed to apply settings. See debug log for details.")


    def _on_apply_finished(self) -> None:
        self.update_always_on_top_status()
        self.format_apply_button(selected_config_shortname=self.applied_config_name)

        self.reapply_paused = False
        self.apply_thread_running = False

    def _update_missing_labels(self) -> None:
        if isinstance(self.config, ConfigParser):
            matching_windows, missing_windows = self.get_matching_and_missing_windows(self.config)
            for win in self.layout_frame.windows:
                name = win.name

                was_missing = not win.exists
                win.exists = name not in missing_windows
                is_now_missing = not win.exists

                if was_missing != is_now_missing:
                    self.layout_frame.update()

    def auto_reapply(self) -> None:
        """Automatically re-apply settings if conditions are met."""
        if self.reapply_in_progress or self.reapply_paused:
            return

        self.reapply_in_progress = True
        self.update_reapply_label()

        worker = GenericWorker(self._reapply_worker_logic)
        worker.signals.finished.connect(self._on_reapply_finished)
        self.thread_pool.start(worker)

    def _reapply_worker_logic(self) -> None:
        if not self.check_reapply_conditions():
            return

        matching, _ = self.get_matching_and_missing_windows(self.applied_config)
        if matching:
            win_match_config = self.verify_window_data(self.applied_config, matching)
            for win in win_match_config:
                if not win["identical"]:
                    settings = config_to_metrics(self.applied_config, win["short_name"])
                    if settings:
                        self.win_man.apply_window_config(settings, win["hwnd"])
                    else:
                        logger.info("Failed to apply settings to %s", win)

    def _on_reapply_finished(self) -> None:
        self._update_missing_labels()
        self.reapply_in_progress = False
        if not self.win_man.validate_state():
            logger.warning("Some windows failed to apply settings during auto re-apply. See debug log for details.")
            self.win_man.remove_invalid_windows()


    def toggle_always_on_top(self) -> None:
        """Toggle the always on top status for all managed windows."""
        self.reapply_paused = not self.reapply_paused
        worker = GenericWorker(self.win_man.toggle_always_on_top, own_hwnd=self.winId())
        worker.signals.finished.connect(self._on_reapply_finished)
        worker.signals.finished.connect(self.update_always_on_top_status)
        self.thread_pool.start(worker)

    def take_screenshot(self) -> None:
        """Take screenshots for all windows matching the current config."""
        if self.screenshot_in_progress:
            return

        self.screenshot_in_progress = True
        self.reapply_paused = True

        self.scr_reapply = False
        if self.applied_config == self.config:
            self.scr_reapply = True
        elif self.applied_config:
            return

        self.apply_settings(reapply=self.scr_reapply)

        worker = GenericWorker(self._take_screenshot_worker_logic)
        worker.signals.finished.connect(self._on_screenshot_finished)
        self.thread_pool.start(worker)

    def _take_screenshot_worker_logic(self) -> None:
        time.sleep(0.5)
        existing, missing = self.get_matching_and_missing_windows(self.config)
        if existing:
            for window in existing:
                self.capture_window(window, self.assets_dir)

            self.win_man.bring_to_front(self.winId())
            self.update_window_layout(self.config, missing)

    def _on_screenshot_finished(self) -> None:
        self.info_label.setText("Screenshot taken for all detected windows.")
        if not self.scr_reapply:
            self.apply_settings()
        self.reapply_paused = False
        QTimer.singleShot(500, self._reset_screenshot_in_progress)

    def _reset_screenshot_in_progress(self) -> None:
        self.screenshot_in_progress = False


    def toggle_active_config(self, cfg_name: str) -> str | None:
        """Toggle the active config."""
        if not cfg_name or cfg_name.lower() == "no configs found":
            return None

        self.config_active = not self.config_active
        if self.config_active:
            file = self.config_files[cfg_name]
            self.applied_config = self.cfg_man.load_config(file)

            logger.info("Applied config: %s", cfg_name)
            logger.info("Managed windows: %s\n", self.win_man.managed_windows)

            return cfg_name

        self.applied_config = None
        self.win_man.reset_all_windows()

        logger.info("Config cleared.")
        logger.info("Managed windows after reset: %s\n", self.win_man.managed_windows)

        if not self.win_man.validate_state():
            logger.warning("Some windows failed to reset. See debug log for details.")

        return None

    def check_reapply_conditions(self) -> bool:
        """Check if conditions are met for auto-reapply to run."""
        return all([self.reapply, self.config_active, not self.apply_thread_running, not self.reapply_paused])

    def get_matching_and_missing_windows(self, config: ConfigParser) -> tuple[list, list]:
        """Get the windows that match the config and the ones that are missing."""
        return self.win_man.find_matching_windows(config, get_ignore_list(config))
