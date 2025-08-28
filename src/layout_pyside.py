from __future__ import annotations

import os
from collections.abc import Callable
from fractions import Fraction

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from callbacks import CallbackManager
from constants import Colors, Fonts, LayoutDefaults, Messages, UIConstants

# Local imports
from utils import WindowInfo, clean_window_title, convert_hex_to_rgb, invert_hex_color

# ------------------------------
# Helper: safe callback getter
# ------------------------------

def _cb(d: dict[str, Callable]|None, key:str, default:Callable|None = None)->Callable:
    if d and key in d and callable(d[key]):
        return d[key]
    return (default or (lambda *a, **k: None))

# --------------------------------------
# Create Config Dialog (two-step wizard)
# --------------------------------------

class ConfigDialog(QDialog):
    def __init__(self, parent:object, window_titles:list, save_callback:Callable,
                 settings_callback:Callable, refresh_callback:Callable,
                 screen_width:int, screen_height:int, assets_dir:str,
                 auto_align_layouts:dict, max_windows:int=4,
                 )->None:
        super().__init__(parent)
        self.setWindowTitle("Create Config")
        self.resize(800, 600)

        self.colors = parent.colors
        self.use_images = parent.use_images

        self.window_titles = window_titles
        self.save_callback = save_callback
        self.settings_callback = settings_callback
        self.refresh_callback = refresh_callback
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.assets_dir = assets_dir
        self.auto_align_layouts = auto_align_layouts
        self.max_windows = max_windows

        self.layout_number = 0
        self.layout_preview = None

        main_layout = QVBoxLayout(self)

        # --- Selection stage (Stage 1) ---
        self.selection_area = QWidget()
        sel_layout = QVBoxLayout(self.selection_area)
        sel_layout.addWidget(QLabel("Select windows (max %d):" % self.max_windows))

        self.switches = {}
        for raw_title in self.window_titles:
            title = clean_window_title(raw_title, sanitize=True)
            cb = QCheckBox(title)
            self.switches[raw_title] = cb
            sel_layout.addWidget(cb)

        confirm_btn = QPushButton("Confirm Selection")
        confirm_btn.clicked.connect(self.confirm_selection)
        sel_layout.addWidget(confirm_btn)

        self.selection_area.adjustSize()   # scale to content
        main_layout.addWidget(self.selection_area)

        self.setLayout(main_layout)
        self.adjustSize()   # make the dialog shrink/grow to contents
        self.setSizeGripEnabled(True)  # allow resizing manually


        # Stage 2 and 3 containers
        self.settings_area = None
        self.save_area = None

    def confirm_selection(self):
        selected = [t for t, cb in self.switches.items() if cb.isChecked()]
        if not selected:
            QMessageBox.critical(self, "Error", "No windows selected")
            return
        if len(selected) > self.max_windows:
            QMessageBox.critical(self, "Error", f"Select up to {self.max_windows} windows only")
            return

        # Switch to settings view
        self.selection_area.hide()
        sorted_windows = sorted(
                selected,
                key=lambda title: int((self.settings_callback(title) or {}).get("position", "0,0").split(",")[0]),
            )
        self.show_config_settings(sorted_windows)

    def show_config_settings(self, sorted_windows):
        self.settings_area = QWidget()
        settings_layout = QVBoxLayout(self.settings_area)

        # --- Rows container (fixed height) ---
        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(0)

        self.settings_rows = {}
        for title in sorted_windows:
            values = self.settings_callback(title) or {}
            row = WindowSettingsRow(title, values)
            rows_layout.addWidget(row)
            self.settings_rows[title] = row

        settings_layout.addWidget(rows_container, stretch=0)

        # --- Controls (fixed height) ---
        controls = QHBoxLayout()
        auto_btn = QPushButton("Auto align")
        update_btn = QPushButton("Update drawing")
        self.ratio_label = QLabel("")
        controls.addWidget(auto_btn)
        controls.addWidget(update_btn)
        controls.addWidget(self.ratio_label)
        settings_layout.addLayout(controls, stretch=0)

        auto_btn.clicked.connect(lambda: self.auto_position(sorted_windows))
        update_btn.clicked.connect(self.update_layout_frame)

        # --- Layout preview (expands on resize) ---
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout_container_layout = QVBoxLayout(self.layout_container)   # <— fix
        settings_layout.addWidget(self.layout_container, stretch=1)

        # --- Save area (fixed height) ---
        self.save_area = QWidget()
        save_layout = QHBoxLayout(self.save_area)
        save_layout.addWidget(QLabel("Config Name:"))
        self.config_name_edit = QLineEdit()
        save_layout.addWidget(self.config_name_edit)
        save_btn = QPushButton("Save Config")
        save_layout.addWidget(save_btn)
        save_btn.clicked.connect(self.on_save)

        settings_layout.addWidget(self.save_area, stretch=0)

        self.layout().addWidget(self.settings_area)
        self.resize(self.sizeHint())
        window_min_height = 435 + (len(self.settings_rows) * 50)
        self.setMinimumSize(800, window_min_height)

        self.update_layout_frame()

    def gather_windows(self):
        windows = []
        for title, row in self.settings_rows.items():
            vals = row.get_values()
            pos_x, pos_y = self.validate_int_pair(vals["position"])
            size_w, size_h = self.validate_int_pair(vals["size"])
            windows.append(WindowInfo(
                vals["name"], pos_x, pos_y, size_w, size_h,
                always_on_top=vals["always_on_top"], exists=True,
                search_title="", source_url="", source="",
            ))
        return windows

    def update_layout_frame(self):
        windows = self.gather_windows()
        if self.layout_preview:
            self.layout_preview.setParent(None)
        self.layout_preview = ScreenLayoutWidget(
            self, self.screen_width, self.screen_height,
            windows, self.assets_dir, window_details=True,
        )
        self.layout_container_layout.addWidget(self.layout_preview)

    def update_row(self, title, pos=None, size=None, aot=None, titlebar=None):
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

    def auto_position(self, sorted_windows):
        screen_width = self.screen_width
        screen_height = self.screen_height
        taskbar_height = UIConstants.TASKBAR_HEIGHT
        usable_height = screen_height - taskbar_height

        if len(sorted_windows) not in self.auto_align_layouts:
            in_defaults = "" if len(sorted_windows) not in LayoutDefaults.DEFAULT_LAYOUTS else " Try to reset to defaults."
            self.ratio_label.setText(f"No auto-alignment available for {len(sorted_windows)} windows. {in_defaults}")
            return
        layout_configs = self.auto_align_layouts[len(sorted_windows)]
        layout_max = len(layout_configs) - 1

        side_text = ""

        two = 2
        three = 3
        four = 4

        # 4 windows
        if len(sorted_windows) == four:
            layout = layout_configs[self.layout_number]

            for i, ((rel_x, rel_y), (rel_w, rel_h)) in enumerate(layout):
                x = int(rel_x * screen_width)
                y = int(rel_y * usable_height)
                w = int(rel_w * screen_width)
                h = int(rel_h * usable_height)

                self.update_row(sorted_windows[i], pos=f"{x},{y}", size=f"{w},{h}")

            # Set name using all rows
            config_name = "_".join(
                self.settings_rows[title].get_values()["name"] for title in sorted_windows
            )
            self.config_name_edit.setText(f"{config_name}_Grid{self.layout_number + 1}")

        # 3 windows
        elif len(sorted_windows) == three:
            numerator, denominator, weight_1 = layout_configs[self.layout_number]
            weight_1 = Fraction(weight_1)
            if not (0 <= weight_1 <= 1):
                print(f"Invalid weight_1: {weight_1}. Resetting to 1/2.")
                weight_1 = Fraction(1, 2)
            weight_2 = 1 - weight_1
            ratio = Fraction(numerator, denominator)

            aux_width = screen_width - (screen_height * ratio)
            left_width = aux_width * weight_1
            center_width = screen_height * ratio
            right_width = aux_width * weight_2

            positions = [
                (0, 0, left_width, usable_height),
                (left_width, 0, center_width, screen_height),
                (left_width + center_width, 0, right_width, usable_height),
            ]

            for (x, y, w, h), title in zip(positions, sorted_windows, strict=False):
                self.update_row(
                    title,
                    pos=f"{int(x)},{int(y)}",
                    size=f"{int(w)},{int(h)}",
                    )

            # middle window override
            self.update_row(sorted_windows[1], aot=True, titlebar=False)

            clean_title = clean_window_title(
                sorted_windows[1],
                sanitize=True,
                titlecase=True,
                )
            self.config_name_edit.setText(
                f"{clean_title} ({numerator}-{denominator})(L_{weight_1.numerator}-"
                f"{weight_1.denominator})(R_{weight_2.numerator}-{weight_2.denominator})",
            )

        # 2 windows
        elif len(sorted_windows) == two:
            numerator, denominator, side = layout_configs[self.layout_number]
            ratio = Fraction(numerator, denominator)

            left_x = 0
            aot = 1 if side in ("R", "CL") else 0

            if side == "R":
                side_text = "Right"
                right_width = screen_height * ratio
                left_width = screen_width - right_width
            elif side == "L":
                side_text = "Left"
                left_width = screen_height * ratio
                right_width = screen_width - left_width
            elif side == "CL":
                side_text = "Center Left"
                right_width = screen_height * ratio
                left_width = (screen_width / 2) - (right_width / 2)
            elif side == "CR":
                side_text = "Center Right"
                left_width = screen_height * ratio
                right_width = (screen_width / 2) - (left_width / 2)
                left_x = right_width
            else:
                print("Invalid position value")
                left_width = right_width = 0

            left_height = right_height = screen_height if side in ("R", "L") else usable_height
            if side == "CL": right_height = screen_height
            if side == "CR": left_height = screen_height

            right_x = left_x + left_width if side == "CR" else left_width

            self.update_row(sorted_windows[0], pos=f"{int(left_x)},0",
                            size=f"{int(left_width)},{int(left_height)}",
                            aot=(aot == 0), titlebar=(aot != 0))

            self.update_row(sorted_windows[1], pos=f"{int(right_x)},0",
                            size=f"{int(right_width)},{int(right_height)}",
                            aot=(aot == 1), titlebar=(aot != 1))

            self.config_name_edit.setText(
                f"{self.settings_rows[sorted_windows[aot]].get_values()['name']} {side}_{numerator}-{denominator}",
            )

        else:
            numerator, denominator, side = layout_configs[self.layout_number]
            ratio = Fraction(numerator, denominator)

            x = 0
            window_width = screen_height * ratio

            if side == "R":
                side_text = "Right"
                x = screen_width - window_width
            elif side == "L":
                side_text = "Left"
                x = 0
            elif side == "C":
                side_text = "Center"
                x = (screen_width / 2) - (window_width / 2)
            else:
                side_text = "Fullscreen"

            for title in sorted_windows:
                self.update_row(title, pos=f"{int(x)},0",
                                size=f"{int(window_width)},{int(screen_height)}",
                                aot=True, titlebar=False)

            self.config_name_edit.setText(
                f"{self.settings_rows[sorted_windows[0]].get_values()['name']} {side}_{numerator}-{denominator}",
            )

        preset_label_text = f"Preset {self.layout_number + 1}/{layout_max + 1}\t"

        if len(sorted_windows) == four:
            self.ratio_label.setText(
                f"{preset_label_text} ",
            )
        elif len(sorted_windows) == three:
            self.ratio_label.setText(
                f"{preset_label_text}"
                f"Aspect: {numerator}/{denominator} "
                f"Left {weight_1.numerator}/{weight_1.denominator} Right {weight_2.numerator}/{weight_2.denominator}",
            )
        elif len(sorted_windows) == two:
            self.ratio_label.setText(
                f"{preset_label_text}"
                f"{side_text:10} {numerator}/{denominator}",
            )
        else:
            self.ratio_label.setText(
                f"{preset_label_text}"
                f"{side_text:10} {numerator}/{denominator}",
            )

        self.layout_number = 0 if self.layout_number >= layout_max else self.layout_number + 1
        self.update_layout_frame()

    def on_save(self):
        config_data = {title: row.get_values() for title, row in self.settings_rows.items()}
        name = self.config_name_edit.text().strip()
        if not name:
            QMessageBox.critical(self, "Error", "Config name is required")
            return
        if self.save_callback(name, config_data):
            if self.refresh_callback:
                self.refresh_callback(name)
            self.accept()

    @staticmethod
    def validate_int_pair(value, default=(0, 0)):
        try:
            x, y = map(int, value.split(","))
            return x, y
        except Exception:
            return default

class WindowSettingsRow(QWidget):
    def __init__(self, title, values):
        super().__init__()
        layout = QHBoxLayout(self)

        pos = values.get("position", "0,0")
        size = values.get("size", "100,100")
        aot = self.to_bool(values.get("always_on_top", False))
        titlebar = self.to_bool(values.get("titlebar", True))
        name = values.get("name", title)

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

        layout.addWidget(self.name_edit, stretch=2)
        layout.addWidget(QLabel("Pos:"))
        layout.addWidget(self.pos_edit, stretch=0)
        layout.addWidget(QLabel("Size:"))
        layout.addWidget(self.size_edit, stretch=0)
        layout.addWidget(self.aot_cb)
        layout.addWidget(self.titlebar_cb)

    def to_bool(self, val):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("1", "true", "yes", "on")
        return bool(val)

    def get_values(self):
        """Return dict in same format as CTk version."""
        return {
            "name": self.name_edit.text().strip(),
            "position": self.pos_edit.text(),
            "size": self.size_edit.text(),
            "always_on_top": self.aot_cb.isChecked(),
            "titlebar": self.titlebar_cb.isChecked(),
        }

    def set_values(self, name = str, pos = [int, int], size = [int, int], aot = bool, titlebar = bool):
        self.name_edit.setText(name)
        self.pos_edit.setText(pos)
        self.size_edit.setText(size)
        self.aot_cb.setChecked(aot)
        self.titlebar_cb.setChecked(titlebar)


# -------------------------
# Main window (QMainWindow)
# -------------------------

class PysideGuiManager(QMainWindow):
    def __init__(self, compact: int = 0, is_admin: bool = False, use_images: int = 0, snap: int = 0, details: int = 0, config_manager=None, asset_manager=None):
        super().__init__()

        self.ui_code = "pyside"

        # App title
        self.application_name = "Ultrawide Window Positioner"
        self.setWindowTitle(self.application_name)

        # Managers
        self.asset_manager = asset_manager
        self.config_manager = config_manager
        self.callback_manager = CallbackManager(self, self.config_manager, self.asset_manager)
        self.callbacks = self.callback_manager.callbacks
        self.assets_dir = self.callback_manager.assets_dir

        # State
        self.compact_mode = compact
        self.style_dark = True
        self.ctk_theme_bg = None  # placeholder for parity
        self.config_active = False
        self.applied_config = None
        self.colors = Colors()

        self.snap = snap
        self.reapply = False
        self.details = bool(details)
        self.use_images = bool(use_images)

        # Screen area size (SystemMetrics 78/79 in Win32; Qt alternative)
        # AvailableGeometry is closer to work-area; use that to mimic taskbar consideration elsewhere
        screen = QApplication.primaryScreen()
        geom = screen.geometry()
        self.res_x = geom.width()
        self.res_y = geom.height()

        width, height, min_width, min_height = self.get_geometry_and_minsize()

        # Startup position
        if self.snap == 0:
            pos_x = (self.res_x // 2) - ((width) // 2)
        elif self.snap == 1:
            pos_x = -7
        elif self.snap == 2:
            pos_x = self.res_x - (width) - 7
        else:
            pos_x = 100

        pos_y = (self.res_y // 2) - ((height) // 2)



        self.is_admin = is_admin
        self.client_info_missing = getattr(self.asset_manager, "client_info_missing", False)

        # Data
        self.canvas: ScreenLayoutWidget | None = None
        self.managed_label: QLabel | None = None
        self.managed_text: QTextEdit | None = None
        self.ratio_label: QLabel | None = None
        self.layout_frame_create_config: ScreenLayoutWidget | None = None
        self.layout_number = 0


        # Load auto-align layouts
        self.auto_align_layouts = self.config_manager.load_or_create_layouts(self.config_manager.layout_config_file)

        # Main UI containers
        central = QWidget()
        self.setCentralWidget(central)
        central.setContentsMargins(0,0,0,0)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(4)

        self._build_ui()
        self.toggle_compact(startup=True)
        self._connect_callbacks()
        self._apply_theme()  # default dark

        self.setMinimumSize(min_width, min_height)
        self.setGeometry(pos_x, pos_y, width, height)

        # Start monitoring for reapply
        self.reapply_timer()

        # Set event filter for managed windows widget
        self.managed_widget.installEventFilter(self)


    # Catch mouse wheel events on managed windows widget
    def eventFilter(self, source, event):
        if source is self.managed_widget and event.type() == QEvent.Wheel:
            combo = self.combo_box
            delta = event.angleDelta().y()
            current = combo.currentIndex()

            if delta > 0:  # scroll up
                new_index = max(0, current - 1)
            else:          # scroll down
                new_index = min(combo.count() - 1, current + 1)

            combo.setCurrentIndex(new_index)

            return True
        return super().eventFilter(source, event)


    def get_geometry_and_minsize(self):
        compact_height_factor = 0.8
        width = UIConstants.WINDOW_WIDTH if not self.compact_mode else UIConstants.COMPACT_WIDTH
        height = UIConstants.WINDOW_HEIGHT if not self.compact_mode else UIConstants.COMPACT_HEIGHT
        min_width = UIConstants.WINDOW_MIN_WIDTH if not self.compact_mode else UIConstants.COMPACT_WIDTH
        min_height = UIConstants.WINDOW_MIN_HEIGHT if not self.compact_mode else UIConstants.COMPACT_HEIGHT * compact_height_factor

        return width, height, min_width, min_height


    def toggle_elements(self, compact, min_width):
        hidden_elements = [
            self.layout_frame,
            self.admin_button,
            self.theme_switch,
            #self.create_config_button,
            #self.delete_config_button,
            self.dummy_spacer_button,
            self.config_folder_button,
            self.image_folder_button,
            self.image_download_button,
            self.screenshot_button,
            self.details_switch,
            self.toggle_images_switch,
            self.aot_label,
            self.left_radio,
            self.center_radio,
            self.right_radio,
            self.snap_label,
        ]

        self.managed_widget.setVisible(compact)

        if compact:
            self.combo_box.setFixedWidth(min_width - 20)
        else:
            self.combo_box.setFixedWidth(min_width / 2)

        for widget in hidden_elements:
            if compact:
                widget.hide()
            else:
                widget.show()


        if compact:
            self.b1.setDirection(QBoxLayout.TopToBottom)  # vertical
            self.b2.setDirection(QBoxLayout.TopToBottom)  # vertical
        else:
            self.b1.setDirection(QBoxLayout.LeftToRight)  # horizontal
            self.b2.setDirection(QBoxLayout.LeftToRight)  # horizontal


    def toggle_compact(self, startup=False):
        if not startup:
            self.compact_mode = not self.compact_mode

        width, height, min_width, min_height = self.get_geometry_and_minsize()
        self.toggle_elements(self.compact_mode, min_width)

        if self.snap == 0:
            pos_x = (self.res_x // 2) - ((width) // 2)
        elif self.snap == 1:
            pos_x = -7
        elif self.snap == 2:
            pos_x = self.res_x - (width) - 7
        else:
            pos_x = 100
        pos_y = (self.res_y // 2) - ((height) // 2)

        self.setMinimumSize(min_width, min_height)
        self.setGeometry(pos_x, pos_y, width, height)


    # Update the text for the managed windows view (for compact mode)
    def update_managed_text(self, lines, aot_flags):
        self.managed_text.setReadOnly(False)
        self.managed_text.clear()

        for i, line in enumerate(lines):
            if aot_flags[i]:
                self.managed_text.setTextColor(self.colors.TEXT_ALWAYS_ON_TOP)
            else:
                self.managed_text.setTextColor(self.colors.TEXT_NORMAL)  # define normal color
            self.managed_text.append(line)

        self.managed_text.setReadOnly(True)



    # ------------- UI composition -------------
    def _build_ui(self):
        width, height, min_width, min_height = self.get_geometry_and_minsize()

        # Header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(15, 0, 15, 0)
        header_layout.setSpacing(10)

        self.resolution_label = QLabel(f"{self.res_x} x {self.res_y}", self)
        header_layout.addWidget(self.resolution_label, alignment=Qt.AlignLeft)

        app_mode = "Admin" if self.is_admin else "User"
        self.admin_label = QLabel(f"{app_mode} mode", self)
        self.admin_label.setStyleSheet(
            f"color: {self.colors.ADMIN_ENABLED if self.is_admin else self.colors.TEXT_NORMAL};",
        )
        header_layout.addWidget(self.admin_label, alignment=Qt.AlignRight)
        self.main_layout.addLayout(header_layout)

        # Combo row
        combo_layout = QHBoxLayout()
        combo_layout.setContentsMargins(10, 0, 10, 0)
        combo_layout.setSpacing(0)

        self.combo_box = QComboBox(self)
        self.combo_box.setFixedWidth(min_width - 20 if self.compact_mode else min_width / 2)
        self.combo_box.currentIndexChanged.connect(lambda _: _cb(self.callbacks, "config_selected")())
        combo_layout.addWidget(self.combo_box, alignment=Qt.AlignLeft)

        self.admin_button = QPushButton("Restart as Admin" if not self.is_admin else "Admin mode", self)
        self.admin_button.setEnabled(not self.is_admin)
        self.admin_button.clicked.connect(_cb(self.callbacks, "restart_as_admin"))

        self.theme_switch = QCheckBox("light / dark", self)
        self.theme_switch.setChecked(False)
        self.theme_switch.stateChanged.connect(self._on_theme_toggle)

        right_layout = QHBoxLayout()
        right_layout.addWidget(self.theme_switch, alignment=Qt.AlignRight)
        right_layout.addWidget(self.admin_button, alignment=Qt.AlignRight)

        combo_layout.addLayout(right_layout)
        self.main_layout.addLayout(combo_layout)

        # Managed area
        self.managed_widget = QWidget(self)
        self.managed_widget.setVisible(self.compact_mode)
        mf_layout = QVBoxLayout(self.managed_widget)
        mf_layout.setContentsMargins(10, 0, 10, 0)

        self.managed_label = QLabel("Managed windows:", self)
        mf_layout.addWidget(self.managed_label, alignment=Qt.AlignLeft)

        self.managed_text = QTextEdit(self)
        self.managed_text.setFixedHeight(80)
        mf_layout.addWidget(self.managed_text)
        self.main_layout.addWidget(self.managed_widget)

        # Layout container (preview)
        lc_layout = QVBoxLayout()
        lc_layout.setContentsMargins(10, 5, 10, 0)

        self.layout_frame = ScreenLayoutWidget(
            self,
            self.res_x, self.res_y, [],
            assets_dir=getattr(self, "assets_dir", None),
            window_details=self.details,
        )
        lc_layout.addWidget(self.layout_frame, 1)
        self.main_layout.addLayout(lc_layout, 1)

        # Status row
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(20, 0, 20, 0)

        self.info_label = QLabel("", self)
        status_layout.addWidget(self.info_label)
        self.main_layout.addLayout(status_layout)

        # Buttons area
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(10, 5, 10, 5)

        # Row 1
        self.b1 = QHBoxLayout()
        self.apply_config_button = QPushButton("Apply config", self)
        self.reset_config_button = QPushButton("Reset config", self)
        self.create_config_button = QPushButton("Create config", self)
        self.delete_config_button = QPushButton("Delete config", self)

        self.b1.addWidget(self.apply_config_button)
        self.b1.addWidget(self.reset_config_button)
        self.b1.addWidget(self.create_config_button)
        self.b1.addWidget(self.delete_config_button)

        btn_layout.addLayout(self.b1)

        # Row 2
        self.b2 = QHBoxLayout()
        self.config_folder_button = QPushButton("Open config folder", self)
        self.screenshot_button = QPushButton("Take screenshots", self)
        self.image_download_button = (
            QPushButton("Download images"
                        if not self.client_info_missing else "Client info missing",
                        self)
                        )
        self.image_download_button.setEnabled(not self.client_info_missing)
        self.image_folder_button = QPushButton("Open image folder", self)

        self.b2.addWidget(self.config_folder_button)
        self.b2.addWidget(self.screenshot_button)
        self.b2.addWidget(self.image_download_button)
        self.b2.addWidget(self.image_folder_button)

        btn_layout.addLayout(self.b2)

        # AOT row
        aot_l = QHBoxLayout()

        self.aot_button = QPushButton("Toggle AOT", self)
        self.aot_button.setEnabled(False)
        self.aot_label = QLabel(Messages.ALWAYS_ON_TOP_DISABLED, self)
        self.aot_label.setContentsMargins(10,0,10,0)

        # Dummy button to keep consistent spacing
        self.dummy_spacer_button = QPushButton("dummy", self)
        self.dummy_spacer_button.setFixedHeight(0)
        self.dummy_spacer_button.setEnabled(False)
        self.dummy_spacer_button.setVisible(True)

        self.toggle_compact_button = QPushButton("Toggle compact", self)

        aot_l.addWidget(self.aot_button)
        aot_l.addWidget(self.aot_label)
        aot_l.addWidget(self.dummy_spacer_button)
        aot_l.addWidget(self.toggle_compact_button)

        btn_layout.addLayout(aot_l)

        # Images / switches row
        img_l = QHBoxLayout()
        img_l.setContentsMargins(0, 10, 0, 10)
        img_l.setSpacing(20)
        self.auto_apply_switch = QCheckBox("Auto re-apply", self)
        self.auto_apply_switch.stateChanged.connect(self._on_reapply_toggle)
        img_l.addWidget(self.auto_apply_switch)

        self.details_switch = QCheckBox("Show window details", self)
        self.details_switch.setChecked(self.details)
        self.details_switch.stateChanged.connect(self._on_details_toggle)
        img_l.addWidget(self.details_switch)

        self.toggle_images_switch = QCheckBox("Images", self)
        self.toggle_images_switch.setChecked(self.use_images)
        self.toggle_images_switch.stateChanged.connect(self._on_images_toggle)
        img_l.addWidget(self.toggle_images_switch)

        img_l.addStretch()  # push snap group right

        snap_l = QHBoxLayout()
        snap_l.setSpacing(10)
        self.snap_label = QLabel("Application open position:", self)
        snap_l.addWidget(self.snap_label)

        radio_width = 60
        self.left_radio = QRadioButton("Left", self)
        self.left_radio.setFixedWidth(radio_width)

        self.center_radio = QRadioButton("Center", self)
        self.center_radio.setFixedWidth(radio_width)

        self.right_radio = QRadioButton("Right", self)
        self.right_radio.setFixedWidth(radio_width)

        self.snap_group = QButtonGroup(self)
        self.snap_group.addButton(self.left_radio, 1)
        self.snap_group.addButton(self.center_radio, 0)
        self.snap_group.addButton(self.right_radio, 2)

        if self.snap == 1:
            self.left_radio.setChecked(True)
        elif self.snap == 2:
            self.right_radio.setChecked(True)
        else:
            self.center_radio.setChecked(True)

        snap_l.addWidget(self.left_radio)
        snap_l.addWidget(self.center_radio)
        snap_l.addWidget(self.right_radio)

        img_l.addLayout(snap_l)

        btn_layout.addLayout(img_l)

        self.main_layout.addLayout(btn_layout)



        # Default selection (match startup)
        if self.snap == 1:
            self.left_radio.setChecked(True)
        elif self.snap == 2:
            self.right_radio.setChecked(True)
        else:
            self.center_radio.setChecked(True)



    def _connect_callbacks(self):
        self.apply_config_button.clicked.connect(_cb(self.callbacks, "apply_config"))
        self.create_config_button.clicked.connect(_cb(self.callbacks, "create_config"))
        self.delete_config_button.clicked.connect(_cb(self.callbacks, "delete_config"))
        self.config_folder_button.clicked.connect(_cb(self.callbacks, "open_config_folder"))
        self.reset_config_button.clicked.connect(_cb(self.callbacks, "apply_config"))
        self.screenshot_button.clicked.connect(_cb(self.callbacks, "screenshot"))
        self.image_download_button.clicked.connect(_cb(self.callbacks, "download_images"))
        self.image_folder_button.clicked.connect(_cb(self.callbacks, "image_folder"))
        self.snap_group.buttonToggled.connect(self._on_snap_toggle)
        self.toggle_compact_button.clicked.connect(_cb(self.callbacks, "toggle_compact"))



    # ------------- Theme & toggles -------------

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QWidget {{ background: {self.colors.BACKGROUND}; color: {self.colors.TEXT_NORMAL}; padding: 0px; border: 0px solid {self.colors.BORDER_COLOR};}}
            QFrame {{ background: {self.colors.BACKGROUND}; padding: 0px; border: 0px solid {self.colors.BORDER_COLOR};}}
            QPushButton {{
                background: {self.colors.BUTTON_NORMAL};
                border-radius: 10;
                border: 2px solid {self.colors.BORDER_COLOR};
                padding: 5px;
                height: 40px;
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
                border-radius: 0;
                border: 2px solid {self.colors.BORDER_COLOR};
                padding: 5px;
            }}
            QCheckBox {{ padding: 0px; }}
        """)
        self.reset_config_button.setStyleSheet(f"""
            QPushButton {{
                background: {self.colors.BUTTON_ACTIVE};
                border: 1px solid {self.colors.BORDER_COLOR};
                padding: 5px;
            }}
            QPushButton:hover {{
                background: {self.colors.BUTTON_ACTIVE_HOVER};
            }}
            QPushButton:disabled {{
                background: {self.colors.BUTTON_DISABLED};
                color: #888;
            }}
        """)
        self.aot_button.setStyleSheet("""
            QPushButton {
                height: 20px;
            }
            """)
        self.toggle_compact_button.setStyleSheet("""
            QPushButton {
                height: 20px;
            }
            """)
        # Re-apply dynamic states after theme reset
        self.format_apply_reset_button()
        self.format_admin_button(self.is_admin)


    def format_apply_reset_button(self, selected_config_shortname=None, disable=None):
        if disable:
            self.apply_config_button.setDisabled(True)
            self.reset_config_button.setDisabled(True)
            return

        if self.config_active:
            self.apply_config_button.setDisabled(True)
            self.reset_config_button.setEnabled(True)
            self.info_label.setText(
                f"Active: {selected_config_shortname if selected_config_shortname else self.applied_config}",
            )
            self.aot_button.setEnabled(True)
        else:
            self.reset_config_button.setDisabled(True)
            self.apply_config_button.setEnabled(True)
            self.info_label.setText("")
            self.aot_button.setEnabled(False)
            self.reapply = False


    def format_admin_button(self, admin_enabled: bool):
        if admin_enabled:
            # Admin mode active → button looks active but disabled
            self.admin_button.setStyleSheet(f"""
                QPushButton {{
                    background: {self.colors.BUTTON_ACTIVE};
                    border: 2px solid {self.colors.BORDER_COLOR};
                    padding: 5px;
                    color: {self.colors.TEXT_NORMAL};
                    height: 20px;
                }}
                QPushButton:hover {{
                    background: {self.colors.BUTTON_ACTIVE_HOVER};
                }}
                QPushButton:disabled {{
                    background: {self.colors.BUTTON_ACTIVE};
                    color: {self.colors.TEXT_NORMAL};
                }}
            """)
            self.admin_button.setEnabled(False)
            self.admin_button.setText("Admin enabled")
        else:
            # Admin mode inactive → normal style, enabled
            self.admin_button.setStyleSheet(f"""
                QPushButton {{
                    background: {self.colors.BUTTON_NORMAL};
                    border: 1px solid {self.colors.BORDER_COLOR};
                    padding: 5px;
                    color: {self.colors.TEXT_NORMAL};
                    height: 20px;
                }}
                QPushButton:hover {{
                    background: {self.colors.BUTTON_HOVER};
                }}
                QPushButton:disabled {{
                    background: {self.colors.BUTTON_DISABLED};
                    color: #888;
                }}
            """)
            self.admin_button.setEnabled(True)
            self.admin_button.setText("Enable admin")


    def invert_colors(self):
        for attr in dir(self.colors):
            if attr.isupper():
                value = getattr(self.colors, attr)
                if isinstance(value, str):
                    setattr(self.colors, attr, invert_hex_color(value))


    def _on_theme_toggle(self, state: int):
        # True -> light; False -> dark
        self.style_dark = not bool(state)
        self.invert_colors()
        self._apply_theme()


    def _on_reapply_toggle(self, state: int):
        self.reapply = self.auto_apply_switch.isChecked()


    def _on_details_toggle(self, _state: int):
        self.details = self.details_switch.isChecked()
        self.callback_manager.save_settings()
        if self.layout_frame:
            self.layout_frame.window_details = self.details
            self.layout_frame.update()


    def _on_images_toggle(self, _state: int):
        self.use_images = self.toggle_images_switch.isChecked()
        self.callback_manager.save_settings()
        if self.layout_frame:
            self.layout_frame.use_images = self.use_images
            self.layout_frame.update()


    def _on_snap_toggle(self, button):
        if button == self.left_radio:
            self.snap = 1
        elif button == self.center_radio:
            self.snap = 0
        elif button == self.right_radio:
            self.snap = 2

        self.callback_manager.save_settings()


    # Timer for auto reapply
    def reapply_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.callback_manager.start_auto_reapply)
        self.timer.start(500)


    # ------------- Managed text (compact mode) -------------
    def setup_managed_text(self):
        if not self.managed_frame.isVisible():
            self.managed_frame.setVisible(True)
        # Label + Text already created; ensure heights
        self.managed_text.setFixedHeight(80)


    # ------------- Layout frame population -------------
    def set_layout_frame(self, windows: list[WindowInfo]):
        self.layout_frame.windows = windows
        self.layout_frame.update()


    # ------------- Create Config workflow -------------
    def create_config_ui(self, parent, window_titles, save_callback, settings_callback, refresh_callback):
        dlg = ConfigDialog(
            parent,
            window_titles,
            save_callback,
            settings_callback,
            refresh_callback,
            self.res_x, self.res_y,
            assets_dir=getattr(self, "assets_dir", None),
            auto_align_layouts=self.auto_align_layouts,
            )
        dlg.exec()







class ScreenLayoutWidget(QWidget):
    def __init__(self, parent, screen_width, screen_height, windows, assets_dir, window_details=True):
        super().__init__(parent)
        self.parent = parent
        self.colors = self.parent.colors
        self.use_images = self.parent.use_images
        self.assets_dir = assets_dir

        self.windows = windows

        self.window_details = window_details
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.link_labels = {}

        self.taskbar_height = 40
        self.line_height = 15



    def set_window_details(self, value: bool):
        self.window_details = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw_layout(painter, self.width(), self.height())

    def wheelEvent(self, event):
        combo = self.parent.combo_box
        delta = event.angleDelta().y()
        current = combo.currentIndex()

        if delta > 0:  # scroll up
            new_index = max(0, current - 1)
        else:          # scroll down
            new_index = min(combo.count() - 1, current + 1)

        combo.setCurrentIndex(new_index)


    # Draw the layout preview

    def draw_layout(self, painter, width, height):
        painter.fillRect(0, 0, width, height, QColor(self.colors.BACKGROUND))

        frame_width = 15
        edge_gap = 10
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

        self.active_labels = set()
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

        # Hide labels that are not active in this paint
        for title, label in self.link_labels.items():
            if title not in self.active_labels:
                label.hide()


        # ---- Outer border drawn last ----
        r, g, b = convert_hex_to_rgb(Colors.WINDOW_FRAME)
        frame_color = QColor(r, g, b)
        pen = QPen(frame_color, frame_width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(frame_rect)

    def draw_window(self, painter, x_offset, y_offset, win, scale):
        x = x_offset + win.pos_x * scale
        y = y_offset + win.pos_y * scale
        w = win.width * scale
        h = win.height * scale

        painter.setRenderHint(QPainter.Antialiasing, False)

        # Fill color
        fill_color = QColor(Colors.WINDOW_ALWAYS_ON_TOP if win.always_on_top else Colors.WINDOW_NORMAL)
        fill_color.setAlpha(255)  # fully opaque

        # Draw window with border
        pen = QPen(QColor(Colors.WINDOW_BORDER))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(int(x), int(y), int(w), int(h))

        # Draw images if enabled
        if self.use_images:
            self.draw_images(painter, x, y, w, h, win, scale)
        else:
            for lbl in self.link_labels.values():
                lbl.hide()

        # Draw window text
        self.draw_text(painter, x, y, w, h, win)

    def draw_text(self, painter, x, y, w, h, win):
        info_lines = [
            win.search_title or win.name,
            f"Pos: {win.pos_x}, {win.pos_y}" if self.window_details else "",
            f"Size: {win.width} x {win.height}" if self.window_details else "",
            f"AOT: {'Yes' if win.always_on_top else 'No'}" if self.window_details else "",
        ]
        padding_x = 4
        padding_y = 2

        font_title = QFont("Arial", 11, QFont.Bold)
        font_normal = QFont("Arial", 9)

        y_cursor = y + padding_y
        for i, line in enumerate(info_lines):
            if not line:
                continue
            painter.setFont(font_title if i == 0 else font_normal)

            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(line)
            text_rect.moveTo(int(x + padding_x), int(y_cursor))

            # keep inside window vertically
            if text_rect.bottom() > y + h - padding_y:
                break

            # background box
            bg_rect = text_rect.adjusted(-3, -1, +3, +1)
            painter.setBrush(QColor(0, 0, 0, 160))  # semi-transparent black
            painter.setPen(Qt.NoPen)
            painter.drawRect(bg_rect)

            # text
            painter.setPen(QColor(Colors.TEXT_NORMAL))
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, line)

            y_cursor += self.line_height

        if not win.exists:
            painter.setFont(font_title)
            painter.setPen(QColor(Colors.TEXT_ERROR))
            painter.drawText(int(x + w/2), int(y + 10), "Missing")

    def draw_images(self, painter, x, y, w, h, win, scale):
        image_paths = [
            os.path.join(self.assets_dir, f"{win.search_title.replace(' ', '_').replace(':', '')}.jpg"),
            os.path.join(self.assets_dir, f"{win.search_title.replace(' ', '_').replace(':', '')}.png"),
        ]

        for image_path in image_paths:
            if os.path.exists(image_path):
                # stretch
                pixmap = QPixmap(image_path).scaled(
                    int(w), int(h),
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation,
                )
                painter.drawPixmap(int(x), int(y), pixmap)

                # handle link
                if getattr(win, "source_url", None):
                    if win.search_title not in self.link_labels:
                        label = QLabel(self)
                        label.setOpenExternalLinks(True)
                        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
                        label.setStyleSheet(f"font: {Fonts.TEXT_SMALL}px; color: #1a73e8; background: transparent;")
                        self.link_labels[win.search_title] = label
                    else:
                        label = self.link_labels[win.search_title]

                    link_text = f'Image source {getattr(win, "source", "")}: <a href="{win.source_url}">{win.source_url}</a>'
                    label.setText(link_text)
                    label.adjustSize()

                    # place label relative to the current window
                    label.move(int(x + (w - label.width()) / 2), int(y + h - label.height() - 5))
                    label.show()
                    self.active_labels.add(win.search_title)
