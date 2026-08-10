from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QComboBox, QPushButton, QLabel,
    QSpinBox, QDoubleSpinBox, QCheckBox, QSlider, QListWidget,
    QListWidgetItem, QMessageBox, QSystemTrayIcon, QMenu,
    QStyle, QFrame, QScrollArea, QGridLayout, QLineEdit,
    QProgressBar, QTextEdit, QSplitter
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction, QFont

from ..constants import APP_NAME, APP_VERSION, MAX_CONTROLLERS, VirtualDeviceType
from ..engine.multi_device_manager import MultiDeviceManager
from ..engine.controller_slot import SlotStatus
from ..engine.virtual_device import VirtualDeviceType as VDT
from ..engine.input_mapper import ProfileConfig
from ..config.profile_manager import ProfileManager
from .color_dialog import ColorDialog, ColorPreview
from .styles import get_stylesheet

import logging
logger = logging.getLogger(__name__)


class ControllerTabWidget(QWidget):
    def __init__(self, slot_id: int, slot, profile_manager: ProfileManager, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.slot = slot
        self.profile_manager = profile_manager
        self._current_profile: ProfileConfig = None
        self._setup_ui()
        self._connect_signals()
        self._load_profile()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QHBoxLayout()
        title = QLabel(f"Controller {self.slot_id + 1}")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #00d4aa;")
        header.addWidget(title)
        header.addStretch()

        self.status_label = QLabel("● Disconnected")
        self.status_label.setStyleSheet("font-size: 13px; color: #ff6b6b; font-weight: 500;")
        header.addWidget(self.status_label)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self._toggle_connection)
        header.addWidget(self.connect_btn)
        layout.addLayout(header)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        self._create_device_tab(tabs)
        self._create_mapping_tab(tabs)
        self._create_led_tab(tabs)

    def _create_device_tab(self, parent_tabs):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        profile_group = QGroupBox("Profile")
        profile_layout = QFormLayout(profile_group)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.profile_manager.list_profiles())
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        profile_layout.addRow("Active Profile:", self.profile_combo)

        profile_btns = QHBoxLayout()
        self.new_profile_btn = QPushButton("New")
        self.new_profile_btn.clicked.connect(self._new_profile)
        self.save_profile_btn = QPushButton("Save")
        self.save_profile_btn.setObjectName("primaryButton")
        self.save_profile_btn.clicked.connect(self._save_profile)
        self.delete_profile_btn = QPushButton("Delete")
        self.delete_profile_btn.setObjectName("dangerButton")
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        profile_btns.addWidget(self.new_profile_btn)
        profile_btns.addWidget(self.save_profile_btn)
        profile_btns.addWidget(self.delete_profile_btn)
        profile_btns.addStretch()
        profile_layout.addRow(profile_btns)

        layout.addWidget(profile_group)

        device_group = QGroupBox("Device")
        device_layout = QFormLayout(device_group)

        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["xbox", "ps4"])
        self.device_type_combo.currentTextChanged.connect(self._on_device_type_changed)
        device_layout.addRow("Virtual Device:", self.device_type_combo)

        self.auto_connect = QCheckBox("Auto-connect on startup")
        self.auto_connect.setChecked(True)
        device_layout.addRow(self.auto_connect)

        layout.addWidget(device_group)

        layout.addStretch()
        scroll.setWidget(content)
        parent_tabs.addTab(scroll, "Device")

    def _create_mapping_tab(self, parent_tabs):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        btn_group = QGroupBox("Button Mapping")
        btn_layout = QVBoxLayout(btn_group)

        self.mapping_list = QListWidget()
        self.mapping_list.setAlternatingRowColors(True)
        btn_layout.addWidget(self.mapping_list)

        layout.addWidget(btn_group)

        stick_group = QGroupBox("Stick Settings")
        stick_layout = QFormLayout(stick_group)

        self.left_deadzone = QDoubleSpinBox()
        self.left_deadzone.setRange(0.0, 0.5)
        self.left_deadzone.setSingleStep(0.01)
        self.left_deadzone.setDecimals(2)
        self.left_deadzone.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Left Stick Deadzone:", self.left_deadzone)

        self.left_sensitivity = QDoubleSpinBox()
        self.left_sensitivity.setRange(0.1, 3.0)
        self.left_sensitivity.setSingleStep(0.1)
        self.left_sensitivity.setDecimals(1)
        self.left_sensitivity.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Left Stick Sensitivity:", self.left_sensitivity)

        self.left_invert = QCheckBox("Invert Y Axis")
        self.left_invert.stateChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow(self.left_invert)

        self.right_deadzone = QDoubleSpinBox()
        self.right_deadzone.setRange(0.0, 0.5)
        self.right_deadzone.setSingleStep(0.01)
        self.right_deadzone.setDecimals(2)
        self.right_deadzone.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Right Stick Deadzone:", self.right_deadzone)

        self.right_sensitivity = QDoubleSpinBox()
        self.right_sensitivity.setRange(0.1, 3.0)
        self.right_sensitivity.setSingleStep(0.1)
        self.right_sensitivity.setDecimals(1)
        self.right_sensitivity.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Right Stick Sensitivity:", self.right_sensitivity)

        self.right_invert = QCheckBox("Invert Y Axis")
        self.right_invert.stateChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow(self.right_invert)

        layout.addWidget(stick_group)

        trigger_group = QGroupBox("Trigger Settings")
        trigger_layout = QFormLayout(trigger_group)

        self.lt_deadzone = QDoubleSpinBox()
        self.lt_deadzone.setRange(0.0, 0.5)
        self.lt_deadzone.setSingleStep(0.01)
        self.lt_deadzone.setDecimals(2)
        self.lt_deadzone.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("L2 Deadzone:", self.lt_deadzone)

        self.lt_sensitivity = QDoubleSpinBox()
        self.lt_sensitivity.setRange(0.1, 3.0)
        self.lt_sensitivity.setSingleStep(0.1)
        self.lt_sensitivity.setDecimals(1)
        self.lt_sensitivity.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("L2 Sensitivity:", self.lt_sensitivity)

        self.rt_deadzone = QDoubleSpinBox()
        self.rt_deadzone.setRange(0.0, 0.5)
        self.rt_deadzone.setSingleStep(0.01)
        self.rt_deadzone.setDecimals(2)
        self.rt_deadzone.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("R2 Deadzone:", self.rt_deadzone)

        self.rt_sensitivity = QDoubleSpinBox()
        self.rt_sensitivity.setRange(0.1, 3.0)
        self.rt_sensitivity.setSingleStep(0.1)
        self.rt_sensitivity.setDecimals(1)
        self.rt_sensitivity.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("R2 Sensitivity:", self.rt_sensitivity)

        layout.addWidget(trigger_group)

        layout.addStretch()
        scroll.setWidget(content)
        parent_tabs.addTab(scroll, "Mapping")

    def _create_led_tab(self, parent_tabs):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        color_group = QGroupBox("LED Color")
        color_layout = QVBoxLayout(color_group)

        self.color_preview = ColorPreview()
        self.color_preview.set_color(QColor(0, 0, 255))
        color_layout.addWidget(self.color_preview, alignment=Qt.AlignCenter)

        self.color_btn = QPushButton("Choose Color")
        self.color_btn.setObjectName("primaryButton")
        self.color_btn.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_btn, alignment=Qt.AlignCenter)

        layout.addWidget(color_group)

        brightness_group = QGroupBox("Brightness")
        brightness_layout = QVBoxLayout(brightness_group)

        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 255)
        self.brightness_slider.setValue(255)
        self.brightness_slider.valueChanged.connect(self._on_brightness_changed)
        brightness_layout.addWidget(self.brightness_slider)

        self.brightness_label = QLabel("255")
        self.brightness_label.setAlignment(Qt.AlignCenter)
        self.brightness_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #00d4aa;")
        brightness_layout.addWidget(self.brightness_label)

        layout.addWidget(brightness_group)

        preset_group = QGroupBox("Presets")
        preset_layout = QGridLayout(preset_group)

        presets = [
            ("#00D4AA", "Teal"), ("#FF6B6B", "Red"), ("#FFD93D", "Yellow"),
            ("#6BFF6B", "Green"), ("#A855F7", "Purple"), ("#FF8800", "Orange"),
            ("#0088FF", "Blue"), ("#FFFFFF", "White"), ("#000000", "Off"),
        ]
        for i, (hex_color, name) in enumerate(presets):
            btn = QPushButton(name)
            btn.setFixedHeight(36)
            btn.setStyleSheet(f"background-color: {hex_color}; color: {'#1e1e2e' if hex_color != '#000000' else '#e0e0e0'}; border-radius: 6px; font-weight: 600;")
            btn.clicked.connect(lambda checked, c=hex_color: self._apply_preset_color(c))
            preset_layout.addWidget(btn, i // 3, i % 3)

        layout.addWidget(preset_group)

        layout.addStretch()
        scroll.setWidget(content)
        parent_tabs.addTab(scroll, "LED")

    def _connect_signals(self):
        self.slot.status_changed.connect(self._on_status_changed)
        self.slot.device_connected.connect(self._on_device_connected)
        self.slot.device_disconnected.connect(self._on_device_disconnected)
        self.slot.log_message.connect(self._on_log_message)

    def _load_profile(self):
        profile_name = self.profile_manager.get_current_profile_name() or "Default"
        self._current_profile = self.profile_manager.load_profile(profile_name)
        idx = self.profile_combo.findText(profile_name)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self._apply_profile_to_ui()

    def _apply_profile_to_ui(self):
        if not self._current_profile:
            return
        self.device_type_combo.setCurrentText(self._current_profile.device_type.value)

        self.left_deadzone.setValue(self._current_profile.left_stick.deadzone)
        self.left_sensitivity.setValue(self._current_profile.left_stick.sensitivity)
        self.left_invert.setChecked(self._current_profile.left_stick.inverted)

        self.right_deadzone.setValue(self._current_profile.right_stick.deadzone)
        self.right_sensitivity.setValue(self._current_profile.right_stick.sensitivity)
        self.right_invert.setChecked(self._current_profile.right_stick.inverted)

        self.lt_deadzone.setValue(self._current_profile.left_trigger.deadzone)
        self.lt_sensitivity.setValue(self._current_profile.left_trigger.sensitivity)
        self.rt_deadzone.setValue(self._current_profile.right_trigger.deadzone)
        self.rt_sensitivity.setValue(self._current_profile.right_trigger.sensitivity)

        self.color_preview.set_color(QColor(*self._current_profile.led_color))
        self.brightness_slider.setValue(self._current_profile.led_brightness)
        self.brightness_label.setText(str(self._current_profile.led_brightness))

        self._update_mapping_list()

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
            item = QListWidgetItem(f"{phys_name} → {virt_name}")
            item.setData(Qt.UserRole, (phys, virt))
            self.mapping_list.addItem(item)

    @Slot(str)
    def _on_status_changed(self, status: str):
        if status == SlotStatus.CONNECTED.value:
            self.status_label.setText("● Connected")
            self.status_label.setStyleSheet("font-size: 13px; color: #6bff6b; font-weight: 500;")
            self.connect_btn.setText("Disconnect")
        elif status == SlotStatus.CONNECTING.value:
            self.status_label.setText("● Connecting...")
            self.status_label.setStyleSheet("font-size: 13px; color: #ffd93d; font-weight: 500;")
        else:
            self.status_label.setText("● Disconnected")
            self.status_label.setStyleSheet("font-size: 13px; color: #ff6b6b; font-weight: 500;")
            self.connect_btn.setText("Connect")

    @Slot(object)
    def _on_device_connected(self, device):
        self.status_label.setText(f"● Connected: {device.name}")
        self.status_label.setStyleSheet("font-size: 13px; color: #6bff6b; font-weight: 500;")
        self.connect_btn.setText("Disconnect")

    @Slot()
    def _on_device_disconnected(self):
        self.status_label.setText("● Disconnected")
        self.status_label.setStyleSheet("font-size: 13px; color: #ff6b6b; font-weight: 500;")
        self.connect_btn.setText("Connect")

    @Slot(str)
    def _on_log_message(self, msg: str):
        pass

    @Slot()
    def _toggle_connection(self):
        if self.slot.is_connected:
            self.slot.stop_worker()
            self.slot.disconnect()
        else:
            if not self.slot.auto_connect():
                from ..engine.multi_device_manager import MultiDeviceManager
                pass
            else:
                self.slot.start_worker()

    @Slot(str)
    def _on_profile_changed(self, name: str):
        self._current_profile = self.profile_manager.load_profile(name)
        self.slot.set_profile(self._current_profile)
        self._apply_profile_to_ui()

    @Slot()
    def _new_profile(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if ok and name:
            if name in self.profile_manager.list_profiles():
                QMessageBox.warning(self, "Exists", "Profile already exists")
                return
            self.profile_manager.save_profile(name, self._current_profile)
            self.profile_combo.addItem(name)
            self.profile_combo.setCurrentText(name)

    @Slot()
    def _save_profile(self):
        if not self._current_profile:
            return
        self._current_profile.name = self.profile_combo.currentText()
        self.profile_manager.save_profile(self._current_profile.name, self._current_profile)
        self._on_log_message(f"Profile '{self._current_profile.name}' saved")

    @Slot()
    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name.lower() == "default":
            QMessageBox.warning(self, "Protected", "Cannot delete Default profile")
            return
        if self.profile_manager.delete_profile(name):
            self.profile_combo.removeItem(self.profile_combo.currentIndex())

    @Slot(str)
    def _on_device_type_changed(self, device_type: str):
        if self._current_profile:
            self._current_profile.device_type = VDT(device_type)
            self.slot._virtual_device.set_device_type(VDT(device_type))

    @Slot()
    def _on_stick_settings_changed(self):
        if not self._current_profile:
            return
        self._current_profile.left_stick.deadzone = self.left_deadzone.value()
        self._current_profile.left_stick.sensitivity = self.left_sensitivity.value()
        self._current_profile.left_stick.inverted = self.left_invert.isChecked()
        self._current_profile.right_stick.deadzone = self.right_deadzone.value()
        self._current_profile.right_stick.sensitivity = self.right_sensitivity.value()
        self._current_profile.right_stick.inverted = self.right_invert.isChecked()

    @Slot()
    def _on_trigger_settings_changed(self):
        if not self._current_profile:
            return
        self._current_profile.left_trigger.deadzone = self.lt_deadzone.value()
        self._current_profile.left_trigger.sensitivity = self.lt_sensitivity.value()
        self._current_profile.right_trigger.deadzone = self.rt_deadzone.value()
        self._current_profile.right_trigger.sensitivity = self.rt_sensitivity.value()

    @Slot()
    def _choose_color(self):
        color = ColorDialog.get_color_static(self.color_preview.get_color(), self)
        if color.isValid():
            self.color_preview.set_color(color)
            if self._current_profile:
                self._current_profile.led_color = (color.red(), color.green(), color.blue())
                if self.slot._led_controller:
                    self.slot._led_controller.set_color(color.red(), color.green(), color.blue())

    @Slot(int)
    def _on_brightness_changed(self, value: int):
        self.brightness_label.setText(str(value))
        if self._current_profile:
            self._current_profile.led_brightness = value
            if self.slot._led_controller:
                self.slot._led_controller.set_brightness(value)

    @Slot(str)
    def _apply_preset_color(self, hex_color: str):
        color = QColor(hex_color)
        self.color_preview.set_color(color)
        if self._current_profile:
            self._current_profile.led_color = (color.red(), color.green(), color.blue())
            if self.slot._led_controller:
                self.slot._led_controller.set_color(color.red(), color.green(), color.blue())