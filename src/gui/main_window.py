from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QComboBox, QPushButton, QLabel,
    QMessageBox, QSystemTrayIcon, QMenu, QFrame, QScrollArea,
    QGridLayout, QTextEdit, QSplitter, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit,
    QDoubleSpinBox, QSpinBox, QSlider, QRadioButton, QButtonGroup,
    QListWidget, QListWidgetItem, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize, QRectF
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction, QFont, QPainter, QBrush, QPen, QLinearGradient

from ..constants import APP_NAME, APP_VERSION, MAX_CONTROLLERS
from ..engine.multi_device_manager import MultiDeviceManager
from ..config.profile_manager import ProfileManager
from .styles import get_stylesheet
from .color_dialog import ColorDialog

import logging
logger = logging.getLogger(__name__)


class ControllerVisualWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 350)
        self.setMaximumSize(400, 450)
        self._mappings = {}
        
    def set_mappings(self, mappings: dict):
        self._mappings = mappings
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        
        # Controller body outline
        painter.setPen(QPen(QColor("#606080"), 2))
        painter.setBrush(QBrush(QColor("#2a2a3e")))
        
        # Main body rounded rect
        body_rect = QRectF(30, 30, w - 60, h - 100)
        painter.drawRoundedRect(body_rect, 40, 40)
        
        # Touchpad
        tp_rect = QRectF(cx - 80, 55, 160, 60)
        painter.setBrush(QBrush(QColor("#1e1e2e")))
        painter.drawRoundedRect(tp_rect, 8, 8)
        painter.setPen(QPen(QColor("#a0a0b0"), 1))
        painter.drawText(tp_rect, Qt.AlignCenter, "Touchpad")
        
        # Left stick
        ls_cx, ls_cy = cx - 65, cy + 30
        painter.setBrush(QBrush(QColor("#3a3a4e")))
        painter.drawEllipse(QRectF(ls_cx - 35, ls_cy - 35, 70, 70))
        painter.setPen(QPen(QColor("#a0a0b0"), 1))
        painter.drawText(QRectF(ls_cx - 35, ls_cy - 10, 70, 20), Qt.AlignCenter, "LS")
        
        # Right stick
        rs_cx, rs_cy = cx + 65, cy + 30
        painter.drawEllipse(QRectF(rs_cx - 35, rs_cy - 35, 70, 70))
        painter.drawText(QRectF(rs_cx - 35, rs_cy - 10, 70, 20), Qt.AlignCenter, "RS")
        
        # D-Pad
        dp_cx, dp_cy = cx - 65, cy - 30
        painter.setBrush(QBrush(QColor("#3a3a4e")))
        dp_size = 45
        painter.drawRoundedRect(QRectF(dp_cx - dp_size//2, dp_cy - dp_size//2, dp_size, dp_size), 4, 4)
        painter.drawText(QRectF(dp_cx - dp_size//2, dp_cy - 10, dp_size, 20), Qt.AlignCenter, "D-Pad")
        
        # Face buttons
        fb_cx, fb_cy = cx + 65, cy - 30
        btn_r = 22
        for dx, dy, label in [(0, -35, "△"), (35, 0, "○"), (0, 35, "×"), (-35, 0, "□")]:
            painter.drawEllipse(QRectF(fb_cx + dx - btn_r, fb_cy + dy - btn_r, btn_r*2, btn_r*2))
            painter.drawText(QRectF(fb_cx + dx - btn_r, fb_cy + dy - 10, btn_r*2, 20), Qt.AlignCenter, label)
        
        # Shoulders
        painter.setBrush(QBrush(QColor("#00d4aa")))
        painter.drawRoundedRect(QRectF(20, 20, 100, 18), 8, 8)
        painter.drawRoundedRect(QRectF(w - 120, 20, 100, 18), 8, 8)
        painter.setPen(QPen(QColor("#1e1e2e"), 1))
        painter.drawText(QRectF(20, 20, 100, 18), Qt.AlignCenter, "L1")
        painter.drawText(QRectF(w - 120, 20, 100, 18), Qt.AlignCenter, "R1")
        
        # Triggers
        painter.drawRoundedRect(QRectF(20, 0, 100, 22), 8, 8)
        painter.drawRoundedRect(QRectF(w - 120, 0, 100, 22), 8, 8)
        painter.drawText(QRectF(20, 0, 100, 22), Qt.AlignCenter, "L2")
        painter.drawText(QRectF(w - 120, 0, 100, 22), Qt.AlignCenter, "R2")
        
        # PS button
        painter.setBrush(QBrush(QColor("#3a3a4e")))
        painter.drawEllipse(QRectF(cx - 12, cy - 55, 24, 24))
        painter.setPen(QPen(QColor("#a0a0b0"), 1))
        painter.drawText(QRectF(cx - 12, cy - 55, 24, 24), Qt.AlignCenter, "PS")
        
        # Share/Options
        painter.drawEllipse(QRectF(cx - 80, cy - 55, 20, 20))
        painter.drawEllipse(QRectF(cx + 60, cy - 55, 20, 20))
        painter.drawText(QRectF(cx - 80, cy - 55, 20, 20), Qt.AlignCenter, "S")
        painter.drawText(QRectF(cx + 60, cy - 55, 20, 20), Qt.AlignCenter, "O")


class AxisConfigWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # LS/RS Section
        ls_rs_group = QGroupBox("LS / RS")
        ls_rs_layout = QGridLayout(ls_rs_group)
        
        headers = ["", "LS", "RS"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet("font-weight: 600; color: #00d4aa;")
            ls_rs_layout.addWidget(lbl, 0, col)
            
        params = [
            ("Dead Zone", "0.10", "0.03"),
            ("Max Zone", "1.00", "0.90"),
            ("Anti-dead Zone", "0.20", "0.00"),
            ("Sensitivity", "1.00", "1.00"),
        ]
        
        self.ls_rs_spins = {}
        for row, (name, ls_val, rs_val) in enumerate(params, 1):
            lbl = QLabel(name)
            ls_spin = QDoubleSpinBox()
            ls_spin.setRange(0.0, 2.0)
            ls_spin.setSingleStep(0.01)
            ls_spin.setDecimals(2)
            ls_spin.setValue(float(ls_val))
            rs_spin = QDoubleSpinBox()
            rs_spin.setRange(0.0, 2.0)
            rs_spin.setSingleStep(0.01)
            rs_spin.setDecimals(2)
            rs_spin.setValue(float(rs_val))
            
            ls_rs_layout.addWidget(lbl, row, 0)
            ls_rs_layout.addWidget(ls_spin, row, 1)
            ls_rs_layout.addWidget(rs_spin, row, 2)
            self.ls_rs_spins[name] = (ls_spin, rs_spin)
            
        # Output Curve
        curve_lbl = QLabel("Output Curve")
        self.ls_curve = QComboBox()
        self.ls_curve.addItems(["Linear", "Enhanced Precision"])
        self.rs_curve = QComboBox()
        self.rs_curve.addItems(["Linear", "Enhanced Precision"])
        ls_rs_layout.addWidget(curve_lbl, len(params)+1, 0)
        ls_rs_layout.addWidget(self.ls_curve, len(params)+1, 1)
        ls_rs_layout.addWidget(self.rs_curve, len(params)+1, 2)
        
        # Square Stick
        sq_lbl = QLabel("Square Stick")
        self.ls_square = QCheckBox()
        self.ls_square_val = QDoubleSpinBox()
        self.ls_square_val.setRange(0, 100)
        self.ls_square_val.setValue(5.0)
        self.rs_square = QCheckBox()
        self.rs_square_val = QDoubleSpinBox()
        self.rs_square_val.setRange(0, 100)
        self.rs_square_val.setValue(5.0)
        
        sq_layout_ls = QHBoxLayout()
        sq_layout_ls.addWidget(self.ls_square)
        sq_layout_ls.addWidget(self.ls_square_val)
        sq_layout_ls.addStretch()
        
        sq_layout_rs = QHBoxLayout()
        sq_layout_rs.addWidget(self.rs_square)
        sq_layout_rs.addWidget(self.rs_square_val)
        sq_layout_rs.addStretch()
        
        sq_w_ls = QWidget()
        sq_w_ls.setLayout(sq_layout_ls)
        sq_w_rs = QWidget()
        sq_w_rs.setLayout(sq_layout_rs)
        
        ls_rs_layout.addWidget(sq_lbl, len(params)+2, 0)
        ls_rs_layout.addWidget(sq_w_ls, len(params)+2, 1)
        ls_rs_layout.addWidget(sq_w_rs, len(params)+2, 2)
        
        # Curve Input
        ci_lbl = QLabel("Curve Input")
        self.ls_curve_in = QSpinBox()
        self.ls_curve_in.setRange(-100, 100)
        self.ls_curve_in.setSuffix("%")
        self.rs_curve_in = QSpinBox()
        self.rs_curve_in.setRange(-100, 100)
        self.rs_curve_in.setSuffix("%")
        ls_rs_layout.addWidget(ci_lbl, len(params)+3, 0)
        ls_rs_layout.addWidget(self.ls_curve_in, len(params)+3, 1)
        ls_rs_layout.addWidget(self.rs_curve_in, len(params)+3, 2)
        
        # Rotation
        rot_lbl = QLabel("Rotation")
        self.ls_rot = QSpinBox()
        self.ls_rot.setRange(-180, 180)
        self.ls_rot.setValue(4)
        self.rs_rot = QSpinBox()
        self.rs_rot.setRange(-180, 180)
        self.rs_rot.setValue(0)
        ls_rs_layout.addWidget(rot_lbl, len(params)+4, 0)
        ls_rs_layout.addWidget(self.ls_rot, len(params)+4, 1)
        ls_rs_layout.addWidget(self.rs_rot, len(params)+4, 2)
        
        layout.addWidget(ls_rs_group)
        
        # L2/R2 Section
        l2r2_group = QGroupBox("L2 / R2")
        l2r2_layout = QGridLayout(l2r2_group)
        
        for col, h in enumerate(["", "L2", "R2"]):
            lbl = QLabel(h)
            lbl.setStyleSheet("font-weight: 600; color: #00d4aa;")
            l2r2_layout.addWidget(lbl, 0, col)
            
        params2 = [
            ("Dead Zone", "0.20", "0.20"),
            ("Max Zone", "1.00", "1.00"),
            ("Anti-dead Zone", "0.00", "0.00"),
            ("Sensitivity", "1.00", "1.00"),
        ]
        
        self.l2r2_spins = {}
        for row, (name, l2_val, r2_val) in enumerate(params2, 1):
            lbl = QLabel(name)
            l2_spin = QDoubleSpinBox()
            l2_spin.setRange(0.0, 2.0)
            l2_spin.setSingleStep(0.01)
            l2_spin.setDecimals(2)
            l2_spin.setValue(float(l2_val))
            r2_spin = QDoubleSpinBox()
            r2_spin.setRange(0.0, 2.0)
            r2_spin.setSingleStep(0.01)
            r2_spin.setDecimals(2)
            r2_spin.setValue(float(r2_val))
            
            l2r2_layout.addWidget(lbl, row, 0)
            l2r2_layout.addWidget(l2_spin, row, 1)
            l2r2_layout.addWidget(r2_spin, row, 2)
            self.l2r2_spins[name] = (l2_spin, r2_spin)
            
        layout.addWidget(l2r2_group)
        layout.addStretch()


class LightbarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Color preview
        self.color_preview = QFrame()
        self.color_preview.setFixedHeight(80)
        self.color_preview.setStyleSheet("background-color: #00d4aa; border-radius: 8px; border: 2px solid #3a3a5c;")
        layout.addWidget(self.color_preview)
        
        # Color picker button
        pick_btn = QPushButton("Choose Color")
        pick_btn.setObjectName("primaryButton")
        pick_btn.clicked.connect(self._pick_color)
        layout.addWidget(pick_btn)
        
        # Brightness
        bright_group = QGroupBox("Brightness")
        bright_layout = QVBoxLayout(bright_group)
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 255)
        self.brightness_slider.setValue(255)
        self.brightness_slider.valueChanged.connect(self._on_brightness)
        bright_layout.addWidget(self.brightness_slider)
        self.bright_label = QLabel("255")
        self.bright_label.setAlignment(Qt.AlignCenter)
        self.bright_label.setStyleSheet("font-weight: 600; color: #00d4aa;")
        bright_layout.addWidget(self.bright_label)
        layout.addWidget(bright_group)
        
        # Presets
        preset_group = QGroupBox("Presets")
        preset_layout = QGridLayout(preset_group)
        presets = [
            ("#00D4AA", "Teal"), ("#FF6B6B", "Red"), ("#FFD93D", "Yellow"),
            ("#6BFF6B", "Green"), ("#A855F7", "Purple"), ("#FF8800", "Orange"),
            ("#0088FF", "Blue"), ("#FFFFFF", "White"), ("#000000", "Off"),
        ]
        for i, (hex_c, name) in enumerate(presets):
            btn = QPushButton(name)
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"background: {hex_c}; color: {'#1e1e2e' if hex_c != '#000000' else '#e0e0e0'}; border-radius: 6px; font-weight: 600;")
            btn.clicked.connect(lambda _, c=hex_c: self._apply_preset(c))
            preset_layout.addWidget(btn, i // 3, i % 3)
        layout.addWidget(preset_group)
        
        # Battery-based color (DS4Windows feature)
        bat_group = QGroupBox("Battery Color Gradient")
        bat_layout = QFormLayout(bat_group)
        self.bat_enable = QCheckBox("Enable battery gradient")
        bat_layout.addRow(self.bat_enable)
        
        self.bat_high = QPushButton("High (Green)")
        self.bat_high.setStyleSheet("background: #6bff6b; color: #1e1e2e; border-radius: 4px;")
        self.bat_med = QPushButton("Medium (Yellow)")
        self.bat_med.setStyleSheet("background: #ffd93d; color: #1e1e2e; border-radius: 4px;")
        self.bat_low = QPushButton("Low (Red)")
        self.bat_low.setStyleSheet("background: #ff6b6b; color: #1e1e2e; border-radius: 4px;")
        bat_layout.addRow("High:", self.bat_high)
        bat_layout.addRow("Medium:", self.bat_med)
        bat_layout.addRow("Low:", self.bat_low)
        layout.addWidget(bat_group)
        
        layout.addStretch()
        
    def _pick_color(self):
        color = ColorDialog.get_color_static(QColor(self.color_preview.styleSheet().split("background-color: ")[1].split(";")[0]), self)
        if color.isValid():
            self._apply_color(color)
            
    def _apply_color(self, color: QColor):
        self.color_preview.setStyleSheet(f"background-color: {color.name()}; border-radius: 8px; border: 2px solid #3a3a5c;")
        
    def _apply_preset(self, hex_c: str):
        self._apply_color(QColor(hex_c))
        
    def _on_brightness(self, val: int):
        self.bright_label.setText(str(val))


class TouchpadWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Mode selection
        mode_group = QGroupBox("Touchpad Mode")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_mouse = QRadioButton("Use As Mouse")
        self.mode_controls = QRadioButton("Use As Controls")
        self.mode_mouse.setChecked(True)
        mode_layout.addWidget(self.mode_mouse)
        mode_layout.addWidget(self.mode_controls)
        layout.addWidget(mode_group)
        
        # Features
        feat_group = QGroupBox("Features")
        feat_layout = QGridLayout(feat_group)
        
        features = [
            ("Slide", True, 100), ("Scroll", False, 0), ("Tap", False, 0),
            ("Double Tap", False, 0), ("Jitter Compensation", True, 0),
            ("Lower Right as RMB", False, 0), ("Start with Slide/Scroll Off", False, 0),
            ("Trackball", True, 10),
        ]
        
        self.feature_checks = {}
        self.feature_vals = {}
        
        for i, (name, checked, val) in enumerate(features):
            cb = QCheckBox(name)
            cb.setChecked(checked)
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setValue(val)
            spin.setEnabled(checked)
            cb.toggled.connect(spin.setEnabled)
            
            feat_layout.addWidget(cb, i, 0)
            feat_layout.addWidget(spin, i, 1)
            
            self.feature_checks[name] = cb
            self.feature_vals[name] = spin
            
        layout.addWidget(feat_group)
        
        # Invert dropdowns
        inv_group = QGroupBox("Invert")
        inv_layout = QFormLayout(inv_group)
        
        self.invert_dropdown = QComboBox()
        self.invert_dropdown.addItems(["None", "X", "Y", "Both"])
        self.disable_invert = QComboBox()
        self.disable_invert.addItems(["None", "X", "Y", "Both"])
        
        inv_layout.addRow("Invert:", self.invert_dropdown)
        inv_layout.addRow("Disable Invert:", self.disable_invert)
        layout.addWidget(inv_group)
        
        layout.addStretch()


class GyroWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        enable_group = QGroupBox("Gyro")
        enable_layout = QVBoxLayout(enable_group)
        self.gyro_enable = QCheckBox("Enable Gyro")
        self.gyro_mouse = QCheckBox("Use as Mouse")
        enable_layout.addWidget(self.gyro_enable)
        enable_layout.addWidget(self.gyro_mouse)
        layout.addWidget(enable_group)
        
        sens_group = QGroupBox("Sensitivity")
        sens_layout = QFormLayout(sens_group)
        self.gyro_sens = QDoubleSpinBox()
        self.gyro_sens.setRange(0.1, 5.0)
        self.gyro_sens.setSingleStep(0.1)
        self.gyro_sens.setValue(1.0)
        sens_layout.addRow("Sensitivity:", self.gyro_sens)
        layout.addWidget(sens_group)
        
        calib_group = QGroupBox("Calibration")
        calib_layout = QVBoxLayout(calib_group)
        calib_btn = QPushButton("Calibrate Now")
        calib_btn.setObjectName("primaryButton")
        calib_layout.addWidget(calib_btn)
        layout.addWidget(calib_group)
        
        layout.addStretch()


class OtherWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Rumble
        rumble_group = QGroupBox("Rumble")
        rumble_layout = QFormLayout(rumble_group)
        self.rumble_enable = QCheckBox("Enable Rumble")
        self.rumble_enable.setChecked(True)
        self.rumble_heavy = QSpinBox()
        self.rumble_heavy.setRange(0, 255)
        self.rumble_heavy.setValue(255)
        self.rumble_light = QSpinBox()
        self.rumble_light.setRange(0, 255)
        self.rumble_light.setValue(255)
        rumble_layout.addRow(self.rumble_enable)
        rumble_layout.addRow("Heavy Motor:", self.rumble_heavy)
        rumble_layout.addRow("Light Motor:", self.rumble_light)
        layout.addWidget(rumble_group)
        
        # LED behavior
        led_group = QGroupBox("LED Behavior")
        led_layout = QFormLayout(led_group)
        self.led_behavior = QComboBox()
        self.led_behavior.addItems(["Profile Color", "Battery Level", "Player Number", "Game Data"])
        led_layout.addRow("Mode:", self.led_behavior)
        layout.addWidget(led_group)
        
        # Connection
        conn_group = QGroupBox("Connection")
        conn_layout = QFormLayout(conn_group)
        self.auto_reconnect = QCheckBox("Auto Reconnect")
        self.auto_reconnect.setChecked(True)
        conn_layout.addRow(self.auto_reconnect)
        layout.addWidget(conn_group)
        
        layout.addStretch()


class ProfileTabWidget(QWidget):
    def __init__(self, slot_id: int, slot, profile_manager, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.slot = slot
        self.profile_manager = profile_manager
        self._current_profile = None
        self._setup_ui()
        self._connect_signals()
        self._load_current_profile()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Profile header
        header = QHBoxLayout()
        header.addWidget(QLabel("Profile:"))
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Profile name...")
        header.addWidget(self.profile_name, 1)
        
        self.save_profile_btn = QPushButton("Save")
        self.save_profile_btn.setObjectName("primaryButton")
        self.cancel_profile_btn = QPushButton("Cancel")
        header.addWidget(self.save_profile_btn)
        header.addWidget(self.cancel_profile_btn)
        
        self.keep_size = QCheckBox("Keep this window size after closing")
        header.addWidget(self.keep_size)
        layout.addLayout(header)
        
        # Sub-tabs
        self.sub_tabs = QTabWidget()
        layout.addWidget(self.sub_tabs, 1)
        
        # Controls tab
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        
        # Left panel - visual + mapping list
        left_panel = QVBoxLayout()
        self.visual = ControllerVisualWidget()
        left_panel.addWidget(self.visual)
        
        self.mapping_list = QListWidget()
        self.mapping_list.setMaximumHeight(200)
        left_panel.addWidget(self.mapping_list)
        
        # Touchpad
        self.touchpad = TouchpadWidget()
        left_panel.addWidget(self.touchpad)
        
        controls_layout.addLayout(left_panel, 1)
        
        # Right panel - axis config, lightbar, gyro, other
        self.right_tabs = QTabWidget()
        self.axis_config = AxisConfigWidget()
        self.lightbar = LightbarWidget()
        self.gyro = GyroWidget()
        self.other = OtherWidget()
        
        self.right_tabs.addTab(self.axis_config, "Axis Config")
        self.right_tabs.addTab(self.lightbar, "Lightbar")
        self.right_tabs.addTab(self.gyro, "Gyro")
        self.right_tabs.addTab(self.other, "Other")
        
        controls_layout.addWidget(self.right_tabs, 1)
        
        self.sub_tabs.addTab(controls_widget, "Controls")
        
        # Special Actions tab (placeholder)
        special_widget = QWidget()
        special_layout = QVBoxLayout(special_widget)
        special_layout.addWidget(QLabel("Special Actions / Macros - Coming Soon"))
        special_layout.addStretch()
        self.sub_tabs.addTab(special_widget, "Special Actions")
        
        # Controller Readings tab (placeholder)
        readings_widget = QWidget()
        readings_layout = QVBoxLayout(readings_widget)
        readings_layout.addWidget(QLabel("Controller Readings - Live Input Display"))
        readings_layout.addStretch()
        self.sub_tabs.addTab(readings_widget, "Controller Readings")
        
        # Footer
        footer = QHBoxLayout()
        self.status_label = QLabel(f"Controller {self.slot_id + 1} is using Profile \"Default\"")
        self.status_label.setStyleSheet("color: #a0a0b0;")
        footer.addWidget(self.status_label)
        footer.addStretch()
        self.hotkeys_link = QLabel('<a href="#">Hotkeys/About</a>')
        self.hotkeys_link.setOpenExternalLinks(False)
        footer.addWidget(self.hotkeys_link)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("dangerButton")
        footer.addWidget(self.stop_btn)
        layout.addLayout(footer)
        
    def _connect_signals(self):
        self.save_profile_btn.clicked.connect(self._save_profile)
        self.cancel_profile_btn.clicked.connect(self._cancel_profile)
        self.stop_btn.clicked.connect(self._stop_controller)
        
    def _load_current_profile(self):
        profile_name = self.profile_manager.get_current_profile_name() or "Default"
        self._current_profile = self.profile_manager.load_profile(profile_name)
        self.profile_name.setText(profile_name)
        self._apply_profile_to_ui()
        
    def _apply_profile_to_ui(self):
        if not self._current_profile:
            return
            
        # Update axis config
        ls = self._current_profile.left_stick
        rs = self._current_profile.right_stick
        lt = self._current_profile.left_trigger
        rt = self._current_profile.right_trigger
        
        for name, (ls_spin, rs_spin) in self.axis_config.ls_rs_spins.items():
            if name == "Dead Zone":
                ls_spin.setValue(ls.deadzone)
                rs_spin.setValue(rs.deadzone)
            elif name == "Max Zone":
                ls_spin.setValue(ls.sensitivity)
                rs_spin.setValue(rs.sensitivity)
            elif name == "Anti-dead Zone":
                ls_spin.setValue(0.2)
                rs_spin.setValue(0.0)
            elif name == "Sensitivity":
                ls_spin.setValue(ls.sensitivity)
                rs_spin.setValue(rs.sensitivity)
                
        for name, (l2_spin, r2_spin) in self.axis_config.l2r2_spins.items():
            if name == "Dead Zone":
                l2_spin.setValue(lt.deadzone)
                r2_spin.setValue(rt.deadzone)
            elif name == "Max Zone":
                l2_spin.setValue(1.0)
                r2_spin.setValue(1.0)
            elif name == "Anti-dead Zone":
                l2_spin.setValue(0.0)
                r2_spin.setValue(0.0)
            elif name == "Sensitivity":
                l2_spin.setValue(lt.sensitivity)
                r2_spin.setValue(rt.sensitivity)
                
        # Update lightbar
        self.lightbar._apply_color(QColor(*self._current_profile.led_color))
        self.lightbar.brightness_slider.setValue(self._current_profile.led_brightness)
        
        # Update mapping list
        self._update_mapping_list()
        self.status_label.setText(f"Controller {self.slot_id + 1} is using Profile \"{self._current_profile.name}\"")
        
    def _update_mapping_list(self):
        self.mapping_list.clear()
        if not self._current_profile:
            return
        from ..constants import DS4Btn, XboxBtn, PS4Btn
        btn_names = {}
        for enum_class in (DS4Btn, XboxBtn, PS4Btn):
            for member in enum_class:
                btn_names[member.value] = member.name
        for phys, virt in self._current_profile.button_maps.items():
            phys_name = btn_names.get(phys, f"0x{phys:03X}")
            virt_name = btn_names.get(virt, f"0x{virt:03X}")
            self.mapping_list.addItem(f"{phys_name}: {virt_name}")
            
    def _save_profile(self):
        name = self.profile_name.text().strip()
        if not name:
            return
        if self._current_profile:
            self._current_profile.name = name
        self.profile_manager.save_profile(name, self._current_profile)
        self._load_current_profile()
        
    def _cancel_profile(self):
        self._load_current_profile()
        
    def _stop_controller(self):
        self.slot.stop_worker()
        self.slot.disconnect()


class ControllersTableWidget(QWidget):
    controller_selected = Signal(int)
    controller_edit = Signal(int)
    
    def __init__(self, multi_manager, parent=None):
        super().__init__(parent)
        self.multi_manager = multi_manager
        self._setup_ui()
        self._refresh()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["#", "ID", "Status", "Ex", "Battery", "Link Profile", "Selected Profile", "Color"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
    def _refresh(self):
        self.table.setRowCount(0)
        slots = self.multi_manager.get_all_slots()
        for i, slot in enumerate(slots):
            self.table.insertRow(i)
            
            # Index
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            
            # ID
            if slot.is_connected and slot.device:
                dev_name = f"{slot.device.name} ({slot.device_path})"
            else:
                dev_name = "No controller"
            self.table.setItem(i, 1, QTableWidgetItem(dev_name))
            
            # Status
            status_text = "Bluetooth" if slot.is_connected else "Disconnected"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor("#6bff6b" if slot.is_connected else "#ff6b6b"))
            self.table.setItem(i, 2, status_item)
            
            # Ex (HidHide access)
            ex_item = QTableWidgetItem("🔑" if slot.is_connected else "")
            ex_item.setToolTip("HidHide Access")
            ex_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, ex_item)
            
            # Battery
            bat_text = "100%" if slot.is_connected else "--"
            self.table.setItem(i, 4, QTableWidgetItem(bat_text))
            
            # Link Profile checkbox
            link_chk = QCheckBox()
            link_chk.setChecked(True)
            link_chk.setStyleSheet("margin-left: 40%; margin-right: 40%;")
            self.table.setCellWidget(i, 5, link_chk)
            
            # Selected Profile dropdown
            profile_combo = QComboBox()
            # Add profiles from manager
            from ..config.profile_manager import ProfileManager
            pm = ProfileManager()
            profile_combo.addItems(pm.list_profiles())
            self.table.setCellWidget(i, 6, profile_combo)
            
            # Color box
            color_item = QTableWidgetItem()
            color_item.setBackground(QColor("#00d4aa"))
            self.table.setItem(i, 7, color_item)
            
            # Edit button
            edit_btn = QPushButton("Editar")
            edit_btn.clicked.connect(lambda _, idx=i: self.controller_edit.emit(idx))
            self.table.setCellWidget(i, 7, edit_btn)
            
        self.table.resizeRowsToContents()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        self.setStyleSheet(get_stylesheet())

        self._profile_manager = ProfileManager()
        self._multi_manager = MultiDeviceManager(max_slots=MAX_CONTROLLERS)
        self._profile_tabs = []

        self._tray_icon: QSystemTrayIcon = None
        self._tray_menu: QMenu = None

        self._setup_tray()
        self._setup_ui()
        self._connect_signals()
        self._auto_connect_devices()

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray not available")
            return

        self._tray_icon = QSystemTrayIcon(self)
        icon = self._create_tray_icon()
        self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip(f"{APP_NAME} - DS4 Emulator")

        self._tray_menu = QMenu(self)
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        self._tray_menu.addAction(show_action)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _create_tray_icon(self) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 212, 170))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 24, 24, 6, 6)
        painter.setBrush(QColor(30, 30, 46))
        painter.drawRoundedRect(8, 8, 16, 16, 4, 4)
        painter.end()
        return QIcon(pixmap)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_application(self):
        self._multi_manager.cleanup()
        if self._tray_icon:
            self._tray_icon.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        if self._tray_icon and self._tray_icon.isVisible():
            event.ignore()
            self.hide()
            self._tray_icon.showMessage(
                APP_NAME,
                "Application minimized to tray. Double-click to restore.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self.quit_application()
            event.accept()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Main tabs (DS4Windows style)
        self._main_tabs = QTabWidget()
        self._main_tabs.setDocumentMode(True)
        main_layout.addWidget(self._main_tabs, 1)

        # Controllers tab
        self._controllers_table = ControllersTableWidget(self._multi_manager)
        self._main_tabs.addTab(self._controllers_table, "Controllers")

        # Profiles tab
        self._profiles_tab = QWidget()
        profiles_layout = QVBoxLayout(self._profiles_tab)
        self._profiles_label = QLabel("Profiles Management - Select a controller from Controllers tab to edit its profile")
        self._profiles_label.setAlignment(Qt.AlignCenter)
        self._profiles_label.setStyleSheet("color: #a0a0b0; font-size: 14px;")
        profiles_layout.addWidget(self._profiles_label)
        self._main_tabs.addTab(self._profiles_tab, "Profiles")

        # Auto Profiles tab (placeholder)
        auto_widget = QWidget()
        auto_layout = QVBoxLayout(auto_widget)
        auto_layout.addWidget(QLabel("Auto Profiles - Coming Soon"))
        auto_layout.addStretch()
        self._main_tabs.addTab(auto_widget, "Auto Profiles")

        # Settings tab
        self._create_settings_tab()

        # Log tab
        self._create_log_tab()

        # Footer status bar
        self._footer = QWidget()
        self._footer.setFixedHeight(36)
        self._footer.setStyleSheet("background: #252536; border-top: 1px solid #3a3a5c;")
        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(12, 0, 12, 0)
        
        self._status_label = QLabel("UDP server listening on address 127.0.0.1 port 26760")
        self._status_label.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        footer_layout.addWidget(self._status_label)
        footer_layout.addStretch()
        
        self._stop_all_btn = QPushButton("Parar")
        self._stop_all_btn.setObjectName("dangerButton")
        self._stop_all_btn.setFixedWidth(80)
        footer_layout.addWidget(self._stop_all_btn)
        
        main_layout.addWidget(self._footer)

    def _create_settings_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        startup_group = QGroupBox("Startup")
        startup_layout = QFormLayout(startup_group)

        self._minimize_tray = QCheckBox("Minimize to tray on close")
        self._minimize_tray.setChecked(True)
        startup_layout.addRow(self._minimize_tray)

        self._start_minimized = QCheckBox("Start minimized")
        startup_layout.addRow(self._start_minimized)

        self._auto_connect_all = QCheckBox("Auto-connect all controllers on startup")
        self._auto_connect_all.setChecked(True)
        startup_layout.addRow(self._auto_connect_all)

        layout.addWidget(startup_group)

        udev_group = QGroupBox("System Integration")
        udev_layout = QVBoxLayout(udev_group)

        self._install_udev_btn = QPushButton("Install udev Rules")
        self._install_udev_btn.setObjectName("primaryButton")
        self._install_udev_btn.clicked.connect(self._install_udev_rules)
        udev_layout.addWidget(self._install_udev_btn)

        self._udev_status = QLabel("Checking...")
        self._udev_status.setStyleSheet("color: #a0a0b0;")
        udev_layout.addWidget(self._udev_status)

        layout.addWidget(udev_group)

        about_group = QGroupBox("About")
        about_layout = QVBoxLayout(about_group)
        about_text = QLabel(f"{APP_NAME} v{APP_VERSION}\nDualShock 4 Multi-Controller Emulator for Linux\n\nSupports up to {MAX_CONTROLLERS} controllers simultaneously\nBuilt with PySide6 & evdev\n\nInspired by DS4Windows")
        about_text.setWordWrap(True)
        about_text.setStyleSheet("color: #a0a0b0;")
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)

        layout.addStretch()
        scroll.setWidget(content)
        self._main_tabs.addTab(scroll, "Settings")

    def _create_log_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont("Monospace", 10))
        self._log_text.setStyleSheet("""
            QTextEdit {
                background: #1a1a2e;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                color: #e0e0e0;
            }
        """)
        layout.addWidget(self._log_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._log_text.clear)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

        scroll.setWidget(content)
        self._main_tabs.addTab(scroll, "Log")

    def _connect_signals(self):
        self._controllers_table.controller_edit.connect(self._on_controller_edit)
        self._stop_all_btn.clicked.connect(self._stop_all_controllers)
        
        for slot in self._multi_manager.get_all_slots():
            slot.log_message.connect(self._on_log_message)

    def _auto_connect_devices(self):
        connected = self._multi_manager.auto_assign_devices()
        if connected > 0:
            self._on_log_message(f"Auto-connected {connected} controller(s)")
        self._controllers_table._refresh()

    def _on_controller_edit(self, slot_idx: int):
        slot = self._multi_manager.get_slot(slot_idx)
        if not slot:
            return
            
        # Remove existing profile tab for this slot if exists
        for i in range(self._main_tabs.count() - 1, 1, -1):  # Keep first 2 tabs (Controllers, Profiles)
            tab_text = self._main_tabs.tabText(i)
            if tab_text.startswith(f"Controller {slot_idx + 1}"):
                widget = self._main_tabs.widget(i)
                self._main_tabs.removeTab(i)
                widget.deleteLater()
        
        # Create new profile tab
        profile_tab = ProfileTabWidget(slot_idx, slot, self._profile_manager)
        tab_idx = self._main_tabs.insertTab(2, profile_tab, f"Controller {slot_idx + 1}")
        self._main_tabs.setCurrentIndex(tab_idx)
        self._profile_tabs.append(profile_tab)

    def _stop_all_controllers(self):
        self._multi_manager.disconnect_all()
        self._controllers_table._refresh()
        self._on_log_message("All controllers stopped")

    @Slot(str)
    def _on_log_message(self, msg: str):
        self._log_text.append(msg)
        self._log_text.verticalScrollBar().setValue(self._log_text.verticalScrollBar().maximum())
        self._controllers_table._refresh()

    @Slot()
    def _install_udev_rules(self):
        import subprocess
        try:
            result = subprocess.run(
                ["pkexec", "sh", "-c", "cp udev/99-ds4linux.rules /etc/udev/rules.d/ && udevadm control --reload-rules && udevadm trigger"],
                capture_output=True, text=True, cwd="/home/servidor/Git/Ds4linux"
            )
            if result.returncode == 0:
                self._udev_status.setText("✓ udev rules installed")
                self._udev_status.setStyleSheet("color: #6bff6b;")
            else:
                self._udev_status.setText(f"✗ Failed: {result.stderr}")
                self._udev_status.setStyleSheet("color: #ff6b6b;")
        except Exception as e:
            self._udev_status.setText(f"✗ Error: {e}")
            self._udev_status.setStyleSheet("color: #ff6b6b;")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter