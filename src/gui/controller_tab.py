from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QLabel, QSpinBox, QDoubleSpinBox,
    QCheckBox, QSlider, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QListWidget, QListWidgetItem,
    QGridLayout, QLineEdit, QRadioButton, QTabWidget, QFrame,
    QScrollArea, QStyle, QMessageBox, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, Slot, QSize, QRectF
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush, QPen, QFont

from ..constants import DS4Btn, XboxBtn, PS4Btn
from ..engine.input_mapper import ProfileConfig, AxisConfig, TriggerConfig
from ..engine.virtual_device import VirtualDeviceType as VDT
from ..config.profile_manager import ProfileManager
from .color_dialog import ColorDialog
from .mapping_tab import MappingTabWidget

logger = logging.getLogger(__name__)


class ControllerVisualWidget(QWidget):
    """Visual outline of a DS4 controller for the mapping editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 280)
        self._mappings: Dict[int, int] = {}

    def set_mappings(self, mappings: Dict[int, int]):
        self._mappings = mappings
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # Body
        p.setPen(QPen(QColor("#555560"), 2))
        p.setBrush(QBrush(QColor("#2a2a3e")))
        p.drawRoundedRect(20, 15, w - 40, h - 60, 35, 35)

        # Touchpad
        p.setBrush(QBrush(QColor("#1e1e2e")))
        tp = QRectF(cx - 65, 55, 130, 55)
        p.drawRoundedRect(tp, 6, 6)
        p.setPen(QPen(QColor("#a0a0b0"), 1))
        p.drawText(tp, Qt.AlignCenter, "TOUCHPAD")

        # Left stick
        ls_cx, ls_cy = cx - 55, cy + 25
        p.setBrush(QBrush(QColor("#3a3a4e")))
        p.drawEllipse(QRectF(ls_cx - 30, ls_cy - 30, 60, 60))
        p.setPen(QPen(QColor("#a0a0b0"), 1))
        p.drawText(QRectF(ls_cx - 30, ls_cy - 10, 60, 20), Qt.AlignCenter, "LS")

        # Right stick
        rs_cx, rs_cy = cx + 55, cy + 25
        p.drawEllipse(QRectF(rs_cx - 30, rs_cy - 30, 60, 60))
        p.drawText(QRectF(rs_cx - 30, rs_cy - 10, 60, 20), Qt.AlignCenter, "RS")

        # D-Pad
        dp_cx, dp_cy = cx - 55, cy - 15
        p.setBrush(QBrush(QColor("#3a3a4e")))
        dp_s = 45
        p.drawRoundedRect(QRectF(dp_cx - dp_s // 2, dp_cy - dp_s // 2, dp_s, dp_s), 4, 4)
        p.drawText(QRectF(dp_cx - dp_s // 2, dp_cy - 10, dp_s, 20), Qt.AlignCenter, "DPAD")

        # Face buttons
        fb_cx, fb_cy = cx + 55, cy - 15
        br = 20
        labels = [("△", "triangle"), ("○", "circle"), ("×", "cross"), ("□", "square")]
        for i, (vis, val) in enumerate(labels):
            angle = 90 + i * 90
            import math
            a = math.radians(angle)
            bx = fb_cx + br * 1.8 * math.cos(a)
            by = fb_cy + br * 1.8 * math.sin(a)
            p.drawEllipse(QRectF(bx - br, by - br, br * 2, br * 2))
            p.drawText(QRectF(bx - br, by - 10, br * 2, 20), Qt.AlignCenter, vis)

        # Share / Options / PS
        p.setBrush(QBrush(QColor("#3a3a4e")))
        p.drawEllipse(QRectF(cx - 65, cy - 55, 20, 20))
        p.drawEllipse(QRectF(cx + 45, cy - 55, 20, 20))
        p.drawEllipse(QRectF(cx - 10, cy - 58, 20, 20))
        p.setPen(QPen(QColor("#a0a0b0"), 1))
        p.drawText(QRectF(cx - 65, cy - 55, 20, 20), Qt.AlignCenter, "S")
        p.drawText(QRectF(cx + 45, cy - 55, 20, 20), Qt.AlignCenter, "O")
        p.drawText(QRectF(cx - 10, cy - 58, 20, 20), Qt.AlignCenter, "PS")

        # Shoulders / Triggers
        p.setBrush(QBrush(QColor("#00cccc")) if self._mappings else QBrush(QColor("#00d4aa")))
        p.drawRoundedRect(QRectF(12, 10, 85, 14), 7, 7)
        p.drawRoundedRect(QRectF(w - 97, 10, 85, 14), 7, 7)
        p.setPen(QPen(QColor("#1e1e2e"), 1))
        p.drawText(QRectF(12, 10, 85, 14), Qt.AlignCenter, "L1")
        p.drawText(QRectF(w - 97, 10, 85, 14), Qt.AlignCenter, "R1")

        # L2 / R2 triggers (more prominent)
        p.setBrush(QBrush(QColor("#00cccc")) if self._mappings else QBrush(QColor("#00d4aa")))
        p.drawRoundedRect(QRectF(10, 0, 80, 16), 8, 8)
        p.drawRoundedRect(QRectF(w - 90, 0, 80, 16), 8, 8)
        p.setPen(QPen(QColor("#1e1e2e"), 1))
        p.drawText(QRectF(10, 0, 80, 16), Qt.AlignCenter, "L2")
        p.drawText(QRectF(w - 90, 0, 80, 16), Qt.AlignCenter, "R2")


class AxisConfigWidget(QWidget):
    """LS/RS, L2/R2 configuration grid – mirrors DS4Windows 'Axis Config' tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ls_rs_spins: Dict[str, tuple] = {}
        self.l2r2_spins: Dict[str, tuple] = {}
        self.ls_curve: QComboBox
        self.rs_curve: QComboBox
        self.ls_square: QCheckBox
        self.ls_square_val: QDoubleSpinBox
        self.rs_square: QCheckBox
        self.rs_square_val: QDoubleSpinBox
        self.ls_curve_in: QSpinBox
        self.rs_curve_in: QSpinBox
        self.ls_rot: QSpinBox
        self.rs_rot: QSpinBox
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # — LS/RS —
        grp = QGroupBox("LS / RS")
        gl = QGridLayout(grp)
        headers = ["Parameter", "LS", "RS"]
        for c, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet("font-weight: 600; color: #00d4aa;")
            gl.addWidget(lbl, 0, c)

        params = [
            ("Dead Zone", 0.10, 0.03),
            ("Max Zone", 1.00, 0.90),
            ("Anti-dead Zone", 0.20, 0.00),
            ("Sensitivity", 1.00, 1.00),
            ("Output Curve", -1, -1),   # placeholder, handled below
            ("Square Stick", -1, -1),
            ("Curve Input", 0, 0),
            ("Rotation", 4, 0),
        ]

        row = 1
        for name, ls_v, rs_v in params:
            gl.addWidget(QLabel(name), row, 0)
            if name in ("Output Curve",):
                self.ls_curve = QComboBox()
                self.ls_curve.addItems(["Linear", "Enhanced Precision"])
                self.rs_curve = QComboBox()
                self.rs_curve.addItems(["Linear", "Enhanced Precision"])
                gl.addWidget(self.ls_curve, row, 1)
                gl.addWidget(self.rs_curve, row, 2)
            elif name == "Square Stick":
                h = QHBoxLayout()
                self.ls_square = QCheckBox()
                self.ls_square_val = QDoubleSpinBox()
                self.ls_square_val.setRange(0, 100)
                self.ls_square_val.setValue(5.0)
                h.addWidget(self.ls_square)
                h.addWidget(self.ls_square_val)
                h.addStretch()
                w = QWidget()
                w.setLayout(h)
                gl.addWidget(w, row, 1)
                h2 = QHBoxLayout()
                self.rs_square = QCheckBox()
                self.rs_square_val = QDoubleSpinBox()
                self.rs_square_val.setRange(0, 100)
                self.rs_square_val.setValue(5.0)
                h2.addWidget(self.rs_square)
                h2.addWidget(self.rs_square_val)
                h2.addStretch()
                w2 = QWidget()
                w2.setLayout(h2)
                gl.addWidget(w2, row, 2)
            elif name == "Curve Input":
                self.ls_curve_in = QSpinBox()
                self.ls_curve_in.setRange(-100, 100)
                self.ls_curve_in.setSuffix("%")
                self.ls_curve_in.setValue(ls_v)
                self.rs_curve_in = QSpinBox()
                self.rs_curve_in.setRange(-100, 100)
                self.rs_curve_in.setSuffix("%")
                self.rs_curve_in.setValue(rs_v)
                gl.addWidget(self.ls_curve_in, row, 1)
                gl.addWidget(self.rs_curve_in, row, 2)
            elif name == "Rotation":
                self.ls_rot = QSpinBox()
                self.ls_rot.setRange(-180, 180)
                self.ls_rot.setValue(ls_v)
                self.rs_rot = QSpinBox()
                self.rs_rot.setRange(-180, 180)
                self.rs_rot.setValue(rs_v)
                gl.addWidget(self.ls_rot, row, 1)
                gl.addWidget(self.rs_rot, row, 2)
            else:
                ls_s = QDoubleSpinBox()
                ls_s.setRange(0.0, 2.0)
                ls_s.setSingleStep(0.01)
                ls_s.setDecimals(2)
                ls_s.setValue(ls_v)
                rs_s = QDoubleSpinBox()
                rs_s.setRange(0.0, 2.0)
                rs_s.setSingleStep(0.01)
                rs_s.setDecimals(2)
                rs_s.setValue(rs_v)
                gl.addWidget(ls_s, row, 1)
                gl.addWidget(rs_s, row, 2)
                self.ls_rs_spins[name] = (ls_s, rs_s)
            row += 1

        layout.addWidget(grp)

        # — L2/R2 —
        grp2 = QGroupBox("L2 / R2")
        gl2 = QGridLayout(grp2)
        for c, h in enumerate(["Parameter", "L2", "R2"]):
            lbl = QLabel(h)
            lbl.setStyleSheet("font-weight: 600; color: #00d4aa;")
            gl2.addWidget(lbl, 0, c)

        params2 = [
            ("Dead Zone", 0.20, 0.20),
            ("Max Zone", 1.00, 1.00),
            ("Anti-dead Zone", 0.00, 0.00),
            ("Sensitivity", 1.00, 1.00),
        ]
        for r, (name, l2_v, r2_v) in enumerate(params2, 1):
            gl2.addWidget(QLabel(name), r, 0)
            l2_s = QDoubleSpinBox()
            l2_s.setRange(0.0, 2.0)
            l2_s.setSingleStep(0.01)
            l2_s.setDecimals(2)
            l2_s.setValue(l2_v)
            r2_s = QDoubleSpinBox()
            r2_s.setRange(0.0, 2.0)
            r2_s.setSingleStep(0.01)
            r2_s.setDecimals(2)
            r2_s.setValue(r2_v)
            gl2.addWidget(l2_s, r, 1)
            gl2.addWidget(r2_s, r, 2)
            self.l2r2_spins[name] = (l2_s, r2_s)

        layout.addWidget(grp2)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Sync with profile
    # ------------------------------------------------------------------
    def set_from_profile(self, prof: ProfileConfig):
        ls, rs, lt, rt = prof.left_stick, prof.right_stick, prof.left_trigger, prof.right_trigger

        self.ls_rs_spins["Dead Zone"] = (self.ls_rs_spins["Dead Zone"][0], self.ls_rs_spins["Dead Zone"][1])
        self.ls_rs_spins["Dead Zone"][0].setValue(ls.deadzone)
        self.ls_rs_spins["Dead Zone"][1].setValue(rs.deadzone)
        self.ls_rs_spins["Max Zone"][0].setValue(ls.max_zone)
        self.ls_rs_spins["Max Zone"][1].setValue(rs.max_zone)
        self.ls_rs_spins["Anti-dead Zone"][0].setValue(ls.anti_deadzone)
        self.ls_rs_spins["Anti-dead Zone"][1].setValue(rs.anti_deadzone)
        self.ls_rs_spins["Sensitivity"][0].setValue(ls.sensitivity)
        self.ls_rs_spins["Sensitivity"][1].setValue(rs.sensitivity)
        self.ls_curve.setCurrentText(ls.output_curve)
        self.rs_curve.setCurrentText(rs.output_curve)
        self.ls_square.setChecked(ls.square_stick)
        self.ls_square_val.setValue(ls.square_stick_value)
        self.rs_square.setChecked(rs.square_stick)
        self.rs_square_val.setValue(rs.square_stick_value)
        self.ls_curve_in.setValue(ls.curve_input)
        self.rs_curve_in.setValue(rs.curve_input)
        self.ls_rot.setValue(ls.rotation)
        self.rs_rot.setValue(rs.rotation)

        self.l2r2_spins["Dead Zone"][0].setValue(lt.deadzone)
        self.l2r2_spins["Dead Zone"][1].setValue(rt.deadzone)
        self.l2r2_spins["Max Zone"][0].setValue(lt.max_zone)
        self.l2r2_spins["Max Zone"][1].setValue(rt.max_zone)
        self.l2r2_spins["Anti-dead Zone"][0].setValue(lt.anti_deadzone)
        self.l2r2_spins["Anti-dead Zone"][1].setValue(rt.anti_deadzone)
        self.l2r2_spins["Sensitivity"][0].setValue(lt.sensitivity)
        self.l2r2_spins["Sensitivity"][1].setValue(rt.sensitivity)

    def get_axis_config(self) -> tuple:
        """Return (ls, rs, lt, rt) AxisConfig objects from widget values."""
        ls_spins = self.ls_rs_spins
        ls = AxisConfig(
            deadzone=ls_spins["Dead Zone"][0].value(),
            max_zone=ls_spins["Max Zone"][0].value(),
            anti_deadzone=ls_spins["Anti-dead Zone"][0].value(),
            sensitivity=ls_spins["Sensitivity"][0].value(),
            output_curve=self.ls_curve.currentText(),
            square_stick=self.ls_square.isChecked(),
            square_stick_value=self.ls_square_val.value(),
            curve_input=self.ls_curve_in.value(),
            rotation=self.ls_rot.value(),
        )
        rs = AxisConfig(
            deadzone=ls_spins["Dead Zone"][1].value(),
            max_zone=ls_spins["Max Zone"][1].value(),
            anti_deadzone=ls_spins["Anti-dead Zone"][1].value(),
            sensitivity=ls_spins["Sensitivity"][1].value(),
            output_curve=self.rs_curve.currentText(),
            square_stick=self.rs_square.isChecked(),
            square_stick_value=self.rs_square_val.value(),
            curve_input=self.rs_curve_in.value(),
            rotation=self.rs_rot.value(),
        )
        lt = TriggerConfig(
            deadzone=self.l2r2_spins["Dead Zone"][0].value(),
            max_zone=self.l2r2_spins["Max Zone"][0].value(),
            anti_deadzone=self.l2r2_spins["Anti-dead Zone"][0].value(),
            sensitivity=self.l2r2_spins["Sensitivity"][0].value(),
        )
        rt = TriggerConfig(
            deadzone=self.l2r2_spins["Dead Zone"][1].value(),
            max_zone=self.l2r2_spins["Max Zone"][1].value(),
            anti_deadzone=self.l2r2_spins["Anti-dead Zone"][1].value(),
            sensitivity=self.l2r2_spins["Sensitivity"][1].value(),
        )
        return ls, rs, lt, rt


class LightbarWidget(QWidget):
    color_changed = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(0, 212, 170)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Color preview
        self.preview = QFrame()
        self.preview.setFixedHeight(80)
        self.preview.setStyleSheet("background-color: #00d4aa; border-radius: 8px; border: 2px solid #3a3a5c;")
        layout.addWidget(self.preview)

        # Pick button
        self.pick_btn = QPushButton("Choose Color")
        self.pick_btn.setObjectName("primaryButton")
        self.pick_btn.clicked.connect(self._pick_color)
        layout.addWidget(self.pick_btn)

        # Brightness
        bright_grp = QGroupBox("Brightness")
        b_layout = QVBoxLayout(bright_grp)
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 255)
        self.brightness_slider.setValue(255)
        self.brightness_slider.valueChanged.connect(self._on_brightness)
        b_layout.addWidget(self.brightness_slider)
        self.bright_label = QLabel("255")
        self.bright_label.setAlignment(Qt.AlignCenter)
        self.bright_label.setStyleSheet("font-weight: 600; color: #00d4aa;")
        b_layout.addWidget(self.bright_label)
        layout.addWidget(bright_grp)

        # Presets
        preset_grp = QGroupBox("Presets")
        p_layout = QGridLayout(preset_grp)
        presets = [
            ("#00D4AA", "Teal"), ("#FF6B6B", "Red"), ("#FFD93D", "Yellow"),
            ("#6BFF6B", "Green"), ("#A855F7", "Purple"), ("#FF8800", "Orange"),
            ("#0088FF", "Blue"), ("#FFFFFF", "White"), ("#000000", "Off"),
        ]
        for i, (hx, name) in enumerate(presets):
            btn = QPushButton(name)
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"background: {hx}; color: {'#1e1e2e' if hx != '#000000' else '#e0e0e0'}; border-radius: 6px; font-weight: 600;")
            btn.clicked.connect(lambda _, c=hx: self._apply_preset(c))
            p_layout.addWidget(btn, i // 3, i % 3)
        layout.addWidget(preset_grp)

        layout.addStretch()

    def _pick_color(self):
        dlg = ColorDialog.initial_color = self._color
        color = ColorDialog.get_color_static(self._color, self)
        if color.isValid():
            self._apply_color(color)

    def _apply_color(self, color: QColor):
        self._color = color
        self.preview.setStyleSheet(f"background-color: {color.name()}; border-radius: 8px; border: 2px solid #3a3a5c;")
        self.color_changed.emit(color)

    def _apply_preset(self, hex_c: str):
        self._apply_color(QColor(hex_c))

    def _on_brightness(self, val: int):
        self.bright_label.setText(str(val))

    def get_color(self) -> QColor:
        return self._color

    def get_brightness(self) -> int:
        return self.brightness_slider.value()

    def set_color(self, color: QColor):
        self._apply_color(color)

    def set_brightness(self, val: int):
        self.brightness_slider.setValue(val)


class TouchpadWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        mode_grp = QGroupBox("Touchpad Mode")
        mode_layout = QVBoxLayout(mode_grp)
        mode_btn = QButtonGroup(self)
        self.mode_mouse = QRadioButton("Use As Mouse")
        self.mode_controls = QRadioButton("Use As Controls")
        self.mode_mouse.setChecked(True)
        mode_btn.addButton(self.mode_mouse)
        mode_btn.addButton(self.mode_controls)
        mode_layout.addWidget(self.mode_mouse)
        mode_layout.addWidget(self.mode_controls)
        layout.addWidget(mode_grp)

        feat_grp = QGroupBox("Features")
        feat_layout = QGridLayout(feat_grp)
        features = [
            ("Slide", True, 100), ("Scroll", False, 0), ("Tap", False, 0),
            ("Double Tap", False, 0), ("Jitter Compensation", True, 0),
            ("Lower Right as RMB", False, 0), ("Start with Slide/Scroll Off", False, 0),
            ("Trackball", True, 10),
        ]
        self.feature_checks: Dict[str, QCheckBox] = {}
        self.feature_vals: Dict[str, QSpinBox] = {}
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
        layout.addWidget(feat_grp)

        inv_grp = QGroupBox("Invert")
        inv_layout = QFormLayout(inv_grp)
        self.invert_dropdown = QComboBox()
        self.invert_dropdown.addItems(["None", "X", "Y", "Both"])
        self.disable_invert = QComboBox()
        self.disable_invert.addItems(["None", "X", "Y", "Both"])
        inv_layout.addRow("Invert:", self.invert_dropdown)
        inv_layout.addRow("Disable Invert:", self.disable_invert)
        layout.addWidget(inv_grp)

        layout.addStretch()


class GyroWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        grp = QGroupBox("Gyro")
        gl = QVBoxLayout(grp)
        self.gyro_enable = QCheckBox("Enable Gyro")
        self.gyro_mouse = QCheckBox("Use as Mouse")
        gl.addWidget(self.gyro_enable)
        gl.addWidget(self.gyro_mouse)
        layout.addWidget(grp)

        sens_grp = QGroupBox("Sensitivity")
        sens_layout = QFormLayout(sens_grp)
        self.gyro_sens = QDoubleSpinBox()
        self.gyro_sens.setRange(0.1, 5.0)
        self.gyro_sens.setSingleStep(0.1)
        self.gyro_sens.setValue(1.0)
        sens_layout.addRow("Sensitivity:", self.gyro_sens)
        layout.addWidget(sens_grp)

        calib_grp = QGroupBox("Calibration")
        calib_layout = QVBoxLayout(calib_grp)
        calib_btn = QPushButton("Calibrate Now")
        calib_btn.setObjectName("primaryButton")
        calib_layout.addWidget(calib_btn)
        layout.addWidget(calib_grp)

        layout.addStretch()


class OtherWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Rumble
        rumble_grp = QGroupBox("Rumble")
        rl = QFormLayout(rumble_grp)
        self.rumble_enable = QCheckBox("Enable Rumble")
        self.rumble_enable.setChecked(True)
        self.rumble_heavy = QSpinBox()
        self.rumble_heavy.setRange(0, 255)
        self.rumble_heavy.setValue(255)
        self.rumble_light = QSpinBox()
        self.rumble_light.setRange(0, 255)
        self.rumble_light.setValue(255)
        rl.addRow(self.rumble_enable)
        rl.addRow("Heavy Motor:", self.rumble_heavy)
        rl.addRow("Light Motor:", self.rumble_light)
        layout.addWidget(rumble_grp)

        # LED Behavior
        led_grp = QGroupBox("LED Behavior")
        led_layout = QFormLayout(led_grp)
        self.led_behavior = QComboBox()
        self.led_behavior.addItems(["Profile Color", "Battery Level", "Player Number", "Game Data"])
        led_layout.addRow("Mode:", self.led_behavior)
        layout.addWidget(led_grp)

        # Connection
        conn_grp = QGroupBox("Connection")
        conn_layout = QFormLayout(conn_grp)
        self.auto_reconnect = QCheckBox("Auto Reconnect")
        self.auto_reconnect.setChecked(True)
        conn_layout.addRow(self.auto_reconnect)
        layout.addWidget(conn_grp)

        layout.addStretch()


class ProfileTabWidget(QWidget):
    """
    Opened when user clicks 'Editar' on a controller row.
    Sub-tabs: Controls | Special Actions | Controller Readings
    Inside 'Controls': visual + mapping list + touchpad (left),
    AxisConfig | Lightbar | Gyro | Other (right).
    """

    save_requested = Signal()

    def __init__(self, slot_id: int, slot, profile_manager, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.slot = slot
        self.profile_manager = profile_manager or ProfileManager()
        self._current_profile: Optional[ProfileConfig] = None
        self._setup_ui()
        self._connect_signals()
        self._load_current_profile()
        # Connect to worker thread raw events for mapping
        self._connect_raw_events()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Header – profile name + device type + save/cancel
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

        # Device type selector
        dt_layout = QHBoxLayout()
        dt_layout.addWidget(QLabel("Virtual Controller:"))
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["xbox", "ps4"])
        self.device_type_combo.currentTextChanged.connect(self._on_device_type_changed)
        dt_layout.addWidget(self.device_type_combo)
        dt_layout.addStretch()
        layout.addLayout(dt_layout)

        # Sub-tabs in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sub_tabs = QTabWidget()
        scroll.setWidget(self.sub_tabs)
        layout.addWidget(scroll, 1)

        self._create_controls_tab()

        # Special Actions (placeholder)
        sp = QFrame()
        sp_layout = QVBoxLayout(sp)
        sp_layout.setContentsMargins(20, 20, 20, 20)
        sp_layout.addWidget(QLabel("Special Actions / Macros – Coming Soon"))
        sp_layout.addStretch()
        self.sub_tabs.addTab(sp, "Special Actions")

        # Controller Readings (placeholder)
        cr = QFrame()
        cr_layout = QVBoxLayout(cr)
        cr_layout.setContentsMargins(20, 20, 20, 20)
        cr_layout.addWidget(QLabel("Controller Readings – Live input display"))
        cr_layout.addStretch()
        self.sub_tabs.addTab(cr, "Controller Readings")

        # Footer
        footer = QHBoxLayout()
        self.status_label = QLabel(f"Controller {self.slot_id + 1} is using Profile \"Default\"")
        self.status_label.setStyleSheet("color: #a0a0b0;")
        footer.addWidget(self.status_label)
        footer.addStretch()
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("dangerButton")
        footer.addWidget(self.stop_btn)
        layout.addLayout(footer)

    def _create_controls_tab(self):
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        # Left: Mapping overlay + visual + touchpad
        left = QVBoxLayout()
        left.setSpacing(10)

        self.mapping_tab = MappingTabWidget()
        self.mapping_tab.mappings_changed.connect(self._on_mappings_changed)
        left.addWidget(self.mapping_tab)

        self.visual = ControllerVisualWidget()
        self.visual.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left.addWidget(self.visual)

        self.touchpad = TouchpadWidget()
        left.addWidget(self.touchpad)

        controls_layout.addLayout(left, 1)

        # Right: Axis Config | Lightbar | Gyro | Other
        self.right_tabs = QTabWidget()
        self.right_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

    def _connect_raw_events(self):
        """Connect to worker thread raw_event signal for mapping mode."""
        if hasattr(self.slot, '_worker') and self.slot._worker:
            self.slot._worker.raw_event.connect(self._on_raw_event)
            self.mapping_tab.set_raw_event_callback(self._on_raw_event)

    def _on_raw_event(self, event_type: int, code: int, value: int):
        """Route raw events to mapping tab."""
        self.mapping_tab._on_raw_event(event_type, code, value)

    def _connect_signals(self):
        self.save_profile_btn.clicked.connect(self._save_profile)
        self.cancel_profile_btn.clicked.connect(self._cancel_profile)
        self.stop_btn.clicked.connect(self._stop_controller)
        self.lightbar.color_changed.connect(self._on_lightbar_color_changed)
        self.lightbar.brightness_slider.valueChanged.connect(self._on_lightbar_brightness_changed)
        self.mapping_tab.mappings_changed.connect(self._on_mappings_changed)

        # axis config signals
        for spins in self.axis_config.ls_rs_spins.values():
            for sp in spins:
                sp.valueChanged.connect(self._on_axis_config_changed)
        for spins in self.axis_config.l2r2_spins.values():
            for sp in spins:
                sp.valueChanged.connect(self._on_axis_config_changed)
        self.axis_config.ls_curve.currentIndexChanged.connect(self._on_axis_config_changed)
        self.axis_config.rs_curve.currentIndexChanged.connect(self._on_axis_config_changed)
        self.axis_config.ls_square.toggled.connect(self._on_axis_config_changed)
        self.axis_config.rs_square.toggled.connect(self._on_axis_config_changed)

    # ------------------------------------------------------------------
    # Profile loading / saving
    # ------------------------------------------------------------------
    def _load_current_profile(self):
        prof_name = self.profile_manager.get_current_profile_name() or "Default"
        self._current_profile = self.profile_manager.load_profile(prof_name)
        self.profile_name.setText(prof_name)
        self._apply_profile_to_ui()

    def _apply_profile_to_ui(self):
        if not self._current_profile:
            return

        self.device_type_combo.setCurrentText(self._current_profile.device_type.value)
        self.axis_config.set_from_profile(self._current_profile)

        self.lightbar.set_color(QColor(*self._current_profile.led_color))
        self.lightbar.set_brightness(self._current_profile.led_brightness)

        # Load mappings into the overlay
        self.mapping_tab.set_mappings(self._current_profile.button_maps)
        self.visual.set_mappings(self._current_profile.button_maps)

        self.status_label.setText(
            f"Controller {self.slot_id + 1} is using Profile \"{self._current_profile.name}\""
        )

    # ------------------------------------------------------------------
    # Save / cancel
    # ------------------------------------------------------------------
    def _save_profile(self):
        name = self.profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Empty Name", "Please enter a profile name.")
            return

        # pull axis config from widgets
        ls, rs, lt, rt = self.axis_config.get_axis_config()
        self._current_profile.left_stick = ls
        self._current_profile.right_stick = rs
        self._current_profile.left_trigger = lt
        self._current_profile.right_trigger = rt

        # Get mappings from the overlay
        self._current_profile.button_maps = self.mapping_tab.get_mappings()

        color = self.lightbar.get_color()
        self._current_profile.led_color = (color.red(), color.green(), color.blue())
        self._current_profile.led_brightness = self.lightbar.get_brightness()

        self._current_profile.name = name
        self.profile_manager.save_profile(name, self._current_profile)
        self._load_current_profile()
        self.slot.set_profile(self._current_profile)
        self.save_requested.emit()

    def _cancel_profile(self):
        self._load_current_profile()

    def _stop_controller(self):
        self.slot.stop_worker()
        self.slot.detach_device()

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------
    def _on_device_type_changed(self, text: str):
        if not self._current_profile:
            return
        dt = VDT(text)
        self._current_profile.device_type = dt
        self.slot._virtual_device.set_device_type(dt)

    def _on_axis_config_changed(self):
        if not self._current_profile:
            return
        ls, rs, lt, rt = self.axis_config.get_axis_config()
        self._current_profile.left_stick = ls
        self._current_profile.right_stick = rs
        self._current_profile.left_trigger = lt
        self._current_profile.right_trigger = rt

    def _on_mappings_changed(self, mappings: Dict[int, int]):
        """Called when mappings are added/removed via the overlay."""
        if self._current_profile:
            self._current_profile.button_maps = mappings

    def _on_lightbar_color_changed(self, color: QColor):
        if self._current_profile:
            self._current_profile.led_color = (color.red(), color.green(), color.blue())
            if self.slot and self.slot._led_controller:
                self.slot._led_controller.set_color(color.red(), color.green(), color.blue())

    def _on_lightbar_brightness_changed(self, val: int):
        if self._current_profile:
            self._current_profile.led_brightness = val
            if self.slot and self.slot._led_controller:
                self.slot._led_controller.set_brightness(val)