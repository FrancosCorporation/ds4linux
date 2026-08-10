from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QComboBox, QPushButton, QLabel,
    QMessageBox, QSystemTrayIcon, QMenu, QFrame, QScrollArea,
    QGridLayout, QTextEdit, QSplitter, QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction, QFont

from ..constants import APP_NAME, APP_VERSION, MAX_CONTROLLERS
from ..engine.multi_device_manager import MultiDeviceManager
from ..config.profile_manager import ProfileManager
from .styles import get_stylesheet
from .controller_tab import ControllerTabWidget

import logging
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1000, 700)
        self.resize(1100, 750)
        self.setStyleSheet(get_stylesheet())

        self._profile_manager = ProfileManager()
        self._multi_manager = MultiDeviceManager(max_slots=MAX_CONTROLLERS)
        self._controller_tabs = []

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
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        header = self._create_header()
        main_layout.addWidget(header)

        self._main_tabs = QTabWidget()
        main_layout.addWidget(self._main_tabs, 1)

        for i in range(MAX_CONTROLLERS):
            slot = self._multi_manager.get_slot(i)
            tab = ControllerTabWidget(i, slot, self._profile_manager)
            self._controller_tabs.append(tab)
            self._main_tabs.addTab(tab, f"Controller {i+1}")

        self._create_global_tab()
        self._create_log_tab()

        status_bar = self.statusBar()
        status_bar.showMessage("Ready - Connect your DS4 controllers")

    def _create_header(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #00d4aa;")
        layout.addWidget(title)

        layout.addStretch()

        self._global_status = QLabel("No controllers connected")
        self._global_status.setStyleSheet("font-size: 13px; color: #a0a0b0;")
        layout.addWidget(self._global_status)

        return widget

    def _create_global_tab(self):
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
        about_text = QLabel(f"{APP_NAME} v{APP_VERSION}\nDualShock 4 Multi-Controller Emulator for Linux\n\nSupports up to {MAX_CONTROLLERS} controllers simultaneously\nBuilt with PySide6 & evdev")
        about_text.setWordWrap(True)
        about_text.setStyleSheet("color: #a0a0b0;")
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)

        layout.addStretch()
        scroll.setWidget(content)
        self._main_tabs.addTab(scroll, "Global")

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
        for i, tab in enumerate(self._controller_tabs):
            tab.slot.log_message.connect(self._on_log_message)
        
        self._multi_manager.get_slot(0).log_message.connect(self._on_log_message)
        self._multi_manager.get_slot(1).log_message.connect(self._on_log_message)

    def _auto_connect_devices(self):
        connected = self._multi_manager.auto_assign_devices()
        if connected > 0:
            self._update_global_status()
            self._on_log_message(f"Auto-connected {connected} controller(s)")

    def _update_global_status(self):
        connected = len(self._multi_manager.get_connected_slots())
        if connected == 0:
            self._global_status.setText("No controllers connected")
            self._global_status.setStyleSheet("font-size: 13px; color: #ff6b6b;")
        elif connected == 1:
            self._global_status.setText("1 controller connected")
            self._global_status.setStyleSheet("font-size: 13px; color: #6bff6b;")
        else:
            self._global_status.setText(f"{connected} controllers connected")
            self._global_status.setStyleSheet("font-size: 13px; color: #6bff6b;")

    @Slot(str)
    def _on_log_message(self, msg: str):
        self._log_text.append(msg)
        self._log_text.verticalScrollBar().setValue(self._log_text.verticalScrollBar().maximum())
        self._update_global_status()

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