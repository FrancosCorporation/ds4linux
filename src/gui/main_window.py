from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QComboBox, QPushButton, QLabel,
    QSpinBox, QDoubleSpinBox, QCheckBox, QSlider, QListWidget,
    QListWidgetItem, QMessageBox, QSystemTrayIcon, QMenu,
    QStyle, QFrame, QScrollArea, QGridLayout, QLineEdit,
    QProgressBar, QTextEdit
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction, QFont

from ..constants import APP_NAME, APP_VERSION, VIRTUAL_DEVICE_TYPES
from ..engine.worker_thread import WorkerThread
from ..engine.virtual_device import VirtualDevice, VirtualDeviceType
from ..engine.input_mapper import ProfileConfig
from ..config.profile_manager import ProfileManager
from .color_dialog import ColorDialog
from .styles import get_stylesheet

import logging
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(900, 650)
        self.resize(1000, 700)
        self.setStyleSheet(get_stylesheet())

        self._profile_manager = ProfileManager()
        self._worker = WorkerThread()
        self._virtual_device = VirtualDevice(VirtualDeviceType.XBOX)
        self._current_profile: ProfileConfig = None

        self._tray_icon: QSystemTrayIcon = None
        self._tray_menu: QMenu = None

        self._setup_tray()
        self._setup_ui()
        self._connect_signals()
        self._load_initial_profile()
        self._start_worker()

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
        self._worker.stop()
        if self._tray_icon:
            self._tray_icon.hide()
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
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        header = self._create_header()
        main_layout.addWidget(header)

        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs, 1)

        self._create_device_tab()
        self._create_mapping_tab()
        self._create_led_tab()
        self._create_advanced_tab()
        self._create_log_tab()

        status_bar = self.statusBar()
        status_bar.showMessage("Ready")

    def _create_header(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #00d4aa;")
        layout.addWidget(title)

        layout.addStretch()

        self._device_status = QLabel("● Disconnected")
        self._device_status.setStyleSheet("font-size: 13px; color: #ff6b6b; font-weight: 500;")
        layout.addWidget(self._device_status)

        self._emulation_status = QLabel("Emulation: Stopped")
        self._emulation_status.setStyleSheet("font-size: 13px; color: #a0a0b0;")
        layout.addWidget(self._emulation_status)

        return widget

    def _create_device_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        profile_group = QGroupBox("Profile")
        profile_layout = QFormLayout(profile_group)

        self._profile_combo = QComboBox()
        self._profile_combo.addItems(self._profile_manager.list_profiles())
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        profile_layout.addRow("Active Profile:", self._profile_combo)

        profile_btns = QHBoxLayout()
        self._new_profile_btn = QPushButton("New")
        self._new_profile_btn.clicked.connect(self._new_profile)
        self._save_profile_btn = QPushButton("Save")
        self._save_profile_btn.setObjectName("primaryButton")
        self._save_profile_btn.clicked.connect(self._save_profile)
        self._delete_profile_btn = QPushButton("Delete")
        self._delete_profile_btn.setObjectName("dangerButton")
        self._delete_profile_btn.clicked.connect(self._delete_profile)
        profile_btns.addWidget(self._new_profile_btn)
        profile_btns.addWidget(self._save_profile_btn)
        profile_btns.addWidget(self._delete_profile_btn)
        profile_btns.addStretch()
        profile_layout.addRow(profile_btns)

        layout.addWidget(profile_group)

        device_group = QGroupBox("Device")
        device_layout = QFormLayout(device_group)

        self._device_type_combo = QComboBox()
        self._device_type_combo.addItems(VIRTUAL_DEVICE_TYPES)
        self._device_type_combo.currentTextChanged.connect(self._on_device_type_changed)
        device_layout.addRow("Virtual Device:", self._device_type_combo)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("primaryButton")
        self._connect_btn.clicked.connect(self._toggle_connection)
        device_layout.addRow(self._connect_btn)

        self._auto_connect = QCheckBox("Auto-connect on startup")
        self._auto_connect.setChecked(True)
        device_layout.addRow(self._auto_connect)

        layout.addWidget(device_group)

        layout.addStretch()
        scroll.setWidget(content)
        self._tabs.addTab(scroll, "Device")

    def _create_mapping_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        btn_group = QGroupBox("Button Mapping")
        btn_layout = QVBoxLayout(btn_group)

        self._mapping_list = QListWidget()
        self._mapping_list.setAlternatingRowColors(True)
        btn_layout.addWidget(self._mapping_list)

        layout.addWidget(btn_group)

        stick_group = QGroupBox("Stick Settings")
        stick_layout = QFormLayout(stick_group)

        self._left_deadzone = QDoubleSpinBox()
        self._left_deadzone.setRange(0.0, 0.5)
        self._left_deadzone.setSingleStep(0.01)
        self._left_deadzone.setDecimals(2)
        self._left_deadzone.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Left Stick Deadzone:", self._left_deadzone)

        self._left_sensitivity = QDoubleSpinBox()
        self._left_sensitivity.setRange(0.1, 3.0)
        self._left_sensitivity.setSingleStep(0.1)
        self._left_sensitivity.setDecimals(1)
        self._left_sensitivity.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Left Stick Sensitivity:", self._left_sensitivity)

        self._left_invert = QCheckBox("Invert Y Axis")
        self._left_invert.stateChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow(self._left_invert)

        self._right_deadzone = QDoubleSpinBox()
        self._right_deadzone.setRange(0.0, 0.5)
        self._right_deadzone.setSingleStep(0.01)
        self._right_deadzone.setDecimals(2)
        self._right_deadzone.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Right Stick Deadzone:", self._right_deadzone)

        self._right_sensitivity = QDoubleSpinBox()
        self._right_sensitivity.setRange(0.1, 3.0)
        self._right_sensitivity.setSingleStep(0.1)
        self._right_sensitivity.setDecimals(1)
        self._right_sensitivity.valueChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow("Right Stick Sensitivity:", self._right_sensitivity)

        self._right_invert = QCheckBox("Invert Y Axis")
        self._right_invert.stateChanged.connect(self._on_stick_settings_changed)
        stick_layout.addRow(self._right_invert)

        layout.addWidget(stick_group)

        trigger_group = QGroupBox("Trigger Settings")
        trigger_layout = QFormLayout(trigger_group)

        self._lt_deadzone = QDoubleSpinBox()
        self._lt_deadzone.setRange(0.0, 0.5)
        self._lt_deadzone.setSingleStep(0.01)
        self._lt_deadzone.setDecimals(2)
        self._lt_deadzone.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("L2 Deadzone:", self._lt_deadzone)

        self._lt_sensitivity = QDoubleSpinBox()
        self._lt_sensitivity.setRange(0.1, 3.0)
        self._lt_sensitivity.setSingleStep(0.1)
        self._lt_sensitivity.setDecimals(1)
        self._lt_sensitivity.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("L2 Sensitivity:", self._lt_sensitivity)

        self._rt_deadzone = QDoubleSpinBox()
        self._rt_deadzone.setRange(0.0, 0.5)
        self._rt_deadzone.setSingleStep(0.01)
        self._rt_deadzone.setDecimals(2)
        self._rt_deadzone.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("R2 Deadzone:", self._rt_deadzone)

        self._rt_sensitivity = QDoubleSpinBox()
        self._rt_sensitivity.setRange(0.1, 3.0)
        self._rt_sensitivity.setSingleStep(0.1)
        self._rt_sensitivity.setDecimals(1)
        self._rt_sensitivity.valueChanged.connect(self._on_trigger_settings_changed)
        trigger_layout.addRow("R2 Sensitivity:", self._rt_sensitivity)

        layout.addWidget(trigger_group)

        layout.addStretch()
        scroll.setWidget(content)
        self._tabs.addTab(scroll, "Mapping")

    def _create_led_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        color_group = QGroupBox("LED Color")
        color_layout = QVBoxLayout(color_group)

        self._color_preview = ColorPreview()
        self._color_preview.set_color(QColor(0, 0, 255))
        color_layout.addWidget(self._color_preview, alignment=Qt.AlignCenter)

        self._color_btn = QPushButton("Choose Color")
        self._color_btn.setObjectName("primaryButton")
        self._color_btn.clicked.connect(self._choose_color)
        color_layout.addWidget(self._color_btn, alignment=Qt.AlignCenter)

        layout.addWidget(color_group)

        brightness_group = QGroupBox("Brightness")
        brightness_layout = QVBoxLayout(brightness_group)

        self._brightness_slider = QSlider(Qt.Horizontal)
        self._brightness_slider.setRange(0, 255)
        self._brightness_slider.setValue(255)
        self._brightness_slider.valueChanged.connect(self._on_brightness_changed)
        brightness_layout.addWidget(self._brightness_slider)

        self._brightness_label = QLabel("255")
        self._brightness_label.setAlignment(Qt.AlignCenter)
        self._brightness_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #00d4aa;")
        brightness_layout.addWidget(self._brightness_label)

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
        self._tabs.addTab(scroll, "LED")

    def _create_advanced_tab(self):
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
        about_text = QLabel(f"{APP_NAME} v{APP_VERSION}\nDualShock 4 Emulator for Linux\n\nBuilt with PySide6 & evdev")
        about_text.setWordWrap(True)
        about_text.setStyleSheet("color: #a0a0b0;")
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)

        layout.addStretch()
        scroll.setWidget(content)
        self._tabs.addTab(scroll, "Advanced")

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
        self._tabs.addTab(scroll, "Log")

    def _connect_signals(self):
        self._worker.device_connected.connect(self._on_device_connected)
        self._worker.device_disconnected.connect(self._on_device_disconnected)
        self._worker.log_message.connect(self._on_log_message)
        self._worker.event_received.connect(self._on_event_received)

    def _load_initial_profile(self):
        profile_name = self._profile_manager.get_current_profile_name() or "Default"
        self._current_profile = self._profile_manager.load_profile(profile_name)
        idx = self._profile_combo.findText(profile_name)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        self._apply_profile_to_ui()

    def _apply_profile_to_ui(self):
        if not self._current_profile:
            return
        self._device_type_combo.setCurrentText(self._current_profile.device_type.value)
        self._virtual_device.set_device_type(self._current_profile.device_type)

        self._left_deadzone.setValue(self._current_profile.left_stick.deadzone)
        self._left_sensitivity.setValue(self._current_profile.left_stick.sensitivity)
        self._left_invert.setChecked(self._current_profile.left_stick.inverted)

        self._right_deadzone.setValue(self._current_profile.right_stick.deadzone)
        self._right_sensitivity.setValue(self._current_profile.right_stick.sensitivity)
        self._right_invert.setChecked(self._current_profile.right_stick.inverted)

        self._lt_deadzone.setValue(self._current_profile.left_trigger.deadzone)
        self._lt_sensitivity.setValue(self._current_profile.left_trigger.sensitivity)
        self._rt_deadzone.setValue(self._current_profile.right_trigger.deadzone)
        self._rt_sensitivity.setValue(self._current_profile.right_trigger.sensitivity)

        self._color_preview.set_color(QColor(*self._current_profile.led_color))
        self._brightness_slider.setValue(self._current_profile.led_brightness)
        self._brightness_label.setText(str(self._current_profile.led_brightness))

        self._update_mapping_list()

    def _update_mapping_list(self):
        self._mapping_list.clear()
        if not self._current_profile:
            return
        from ..constants import DS4Btn, XboxBtn, PS4Btn
        btn_names = {**{v: k.name for k, v in DS4Btn.__members__.items()},
                     **{v: k.name for k, v in XboxBtn.__members__.items()},
                     **{v: k.name for k, v in PS4Btn.__members__.items()}}
        for phys, virt in self._current_profile.button_maps.items():
            phys_name = btn_names.get(phys, f"0x{phys:03X}")
            virt_name = btn_names.get(virt, f"0x{virt:03X}")
            item = QListWidgetItem(f"{phys_name} → {virt_name}")
            item.setData(Qt.UserRole, (phys, virt))
            self._mapping_list.addItem(item)

    def _start_worker(self):
        self._worker.set_virtual_device(self._virtual_device)
        from ..engine.input_mapper import InputMapper
        from ..engine.led_controller import LEDController
        mapper = InputMapper(self._current_profile)
        self._worker.set_input_mapper(mapper)
        led = LEDController()
        self._worker.set_led_controller(led)
        self._worker.start()

    @Slot()
    def _on_profile_changed(self, name: str):
        self._current_profile = self._profile_manager.load_profile(name)
        self._worker.set_input_mapper(None)
        from ..engine.input_mapper import InputMapper
        self._worker.set_input_mapper(InputMapper(self._current_profile))
        self._virtual_device.set_device_type(self._current_profile.device_type)
        self._apply_profile_to_ui()

    @Slot()
    def _new_profile(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if ok and name:
            if name in self._profile_manager.list_profiles():
                QMessageBox.warning(self, "Exists", "Profile already exists")
                return
            self._profile_manager.save_profile(name, self._current_profile)
            self._profile_combo.addItem(name)
            self._profile_combo.setCurrentText(name)

    @Slot()
    def _save_profile(self):
        if not self._current_profile:
            return
        self._current_profile.name = self._profile_combo.currentText()
        self._profile_manager.save_profile(self._current_profile.name, self._current_profile)
        self._log_message(f"Profile '{self._current_profile.name}' saved")

    @Slot()
    def _delete_profile(self):
        name = self._profile_combo.currentText()
        if name.lower() == "default":
            QMessageBox.warning(self, "Protected", "Cannot delete Default profile")
            return
        if self._profile_manager.delete_profile(name):
            self._profile_combo.removeItem(self._profile_combo.currentIndex())

    @Slot(str)
    def _on_device_type_changed(self, device_type: str):
        if self._current_profile:
            self._current_profile.device_type = VirtualDeviceType(device_type)
            self._virtual_device.set_device_type(VirtualDeviceType(device_type))

    @Slot()
    def _toggle_connection(self):
        if self._worker.is_device_connected():
            self._worker.stop()
            self._worker.wait(1000)
            self._connect_btn.setText("Connect")
            self._emulation_status.setText("Emulation: Stopped")
            self._device_status.setText("● Disconnected")
            self._device_status.setStyleSheet("font-size: 13px; color: #ff6b6b; font-weight: 500;")
        else:
            self._start_worker()
            self._connect_btn.setText("Disconnect")
            self._emulation_status.setText("Emulation: Running")

    @Slot()
    def _on_device_connected(self, device):
        self._device_status.setText(f"● Connected: {device.name}")
        self._device_status.setStyleSheet("font-size: 13px; color: #6bff6b; font-weight: 500;")
        self._emulation_status.setText("Emulation: Running")
        self._connect_btn.setText("Disconnect")

    @Slot()
    def _on_device_disconnected(self):
        self._device_status.setText("● Disconnected")
        self._device_status.setStyleSheet("font-size: 13px; color: #ff6b6b; font-weight: 500;")
        self._emulation_status.setText("Emulation: Stopped")
        self._connect_btn.setText("Connect")

    @Slot(str)
    def _on_log_message(self, msg: str):
        self._log_text.append(msg)
        self._log_text.verticalScrollBar().setValue(self._log_text.verticalScrollBar().maximum())

    @Slot(int, int, int)
    def _on_event_received(self, ev_type, code, value):
        pass

    @Slot()
    def _on_stick_settings_changed(self):
        if not self._current_profile:
            return
        self._current_profile.left_stick.deadzone = self._left_deadzone.value()
        self._current_profile.left_stick.sensitivity = self._left_sensitivity.value()
        self._current_profile.left_stick.inverted = self._left_invert.isChecked()
        self._current_profile.right_stick.deadzone = self._right_deadzone.value()
        self._current_profile.right_stick.sensitivity = self._right_sensitivity.value()
        self._current_profile.right_stick.inverted = self._right_invert.isChecked()

    @Slot()
    def _on_trigger_settings_changed(self):
        if not self._current_profile:
            return
        self._current_profile.left_trigger.deadzone = self._lt_deadzone.value()
        self._current_profile.left_trigger.sensitivity = self._lt_sensitivity.value()
        self._current_profile.right_trigger.deadzone = self._rt_deadzone.value()
        self._current_profile.right_trigger.sensitivity = self._rt_sensitivity.value()

    @Slot()
    def _choose_color(self):
        color = ColorDialog.get_color_static(self._color_preview.get_color(), self)
        if color.isValid():
            self._color_preview.set_color(color)
            if self._current_profile:
                self._current_profile.led_color = (color.red(), color.green(), color.blue())
                if self._worker._led_controller:
                    self._worker._led_controller.set_color(color.red(), color.green(), color.blue())

    @Slot(int)
    def _on_brightness_changed(self, value: int):
        self._brightness_label.setText(str(value))
        if self._current_profile:
            self._current_profile.led_brightness = value
            if self._worker._led_controller:
                self._worker._led_controller.set_brightness(value)

    @Slot(str)
    def _apply_preset_color(self, hex_color: str):
        color = QColor(hex_color)
        self._color_preview.set_color(color)
        if self._current_profile:
            self._current_profile.led_color = (color.red(), color.green(), color.blue())
            if self._worker._led_controller:
                self._worker._led_controller.set_color(color.red(), color.green(), color.blue())

    @Slot()
    def _install_udev_rules(self):
        import subprocess
        try:
            result = subprocess.run(["pkexec", "sh", "-c", "cp udev/99-ds4linux.rules /etc/udev/rules.d/ && udevadm control --reload-rules && udevadm trigger"],
                                  capture_output=True, text=True, cwd="/home/servidor/Git/Ds4linux")
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