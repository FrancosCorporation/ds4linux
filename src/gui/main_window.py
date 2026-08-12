from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QPushButton, QLabel, QMessageBox,
    QSystemTrayIcon, QMenu, QFrame, QScrollArea, QTextEdit,
    QCheckBox, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction, QFont, QPainter

from ..constants import APP_NAME, APP_VERSION, MAX_CONTROLLERS
from ..engine.multi_device_manager import MultiDeviceManager
from ..engine.auto_profile import AutoProfileManager
from .styles import get_stylesheet
from .controllers_table import ControllersTableWidget
from .controller_tab import ProfileTabWidget
from .auto_profiles_tab import AutoProfilesTab

logger = logging.getLogger(__name__)


class ProfileListWidget(QListWidget):
    """
    Profile list with double-click, context menu, and CRUD operations.
    """
    profile_selected = Signal(str)
    profile_edit_requested = Signal(str)
    profile_created = Signal(str)
    profile_deleted = Signal(str)

    def __init__(self, profile_manager, parent=None):
        super().__init__(parent)
        self._pm = profile_manager
        self._set_mouse_tracking()
        self._setup_ui()
        self._load_profiles()

    def _set_mouse_tracking(self):
        self.setMouseTracking(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _setup_ui(self):
        self.setStyleSheet("""
            QListWidget {
                background: #252536;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background: #00d4aa;
                color: #1e1e2e;
            }
            QListWidget::item:hover:!selected {
                background: #3a3a5c;
            }
        """)

    def _load_profiles(self):
        self.clear()
        profiles = self._pm.list_profiles()
        for name in profiles:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self.addItem(item)
        # Select current profile
        current = self._pm.get_current_profile_name()
        if current:
            for i in range(self.count()):
                if self.item(i).data(Qt.UserRole) == current:
                    self.setCurrentItem(self.item(i))
                    self.profile_selected.emit(current)
                    break

    def _on_double_click(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        if name:
            self.profile_edit_requested.emit(name)

    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        menu = QMenu(self)

        edit_action = QAction("✏️ Editar", menu)
        edit_action.triggered.connect(lambda: self.profile_edit_requested.emit(
            item.data(Qt.UserRole) if item else None
        ))
        menu.addAction(edit_action)

        if item:
            duplicate_action = QAction("📋 Duplicar", menu)
            duplicate_action.triggered.connect(lambda: self._duplicate_profile(item.data(Qt.UserRole)))
            menu.addAction(duplicate_action)

            delete_action = QAction("🗑️ Excluir", menu)
            delete_action.triggered.connect(lambda: self._delete_profile(item.data(Qt.UserRole)))
            menu.addAction(delete_action)

        menu.addSeparator()
        new_action = QAction("➕ Novo Perfil", menu)
        new_action.triggered.connect(self._create_new_profile)
        menu.addAction(new_action)

        menu.exec(self.mapToGlobal(pos))

    def _duplicate_profile(self, name: str):
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Duplicar Perfil", "Nome do novo perfil:")
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name in self._pm.list_profiles():
                QMessageBox.warning(self, "Erro", f"Perfil '{new_name}' já existe.")
                return
            # Load and save with new name
            profile = self._pm.load_profile(name)
            self._pm.save_profile(new_name, profile)
            self._load_profiles()
            self.profile_created.emit(new_name)

    def _delete_profile(self, name: str):
        if name.lower() == "default":
            QMessageBox.warning(self, "Erro", "Não é possível excluir o perfil padrão.")
            return
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o perfil '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._pm.delete_profile(name)
            self._load_profiles()
            self.profile_deleted.emit(name)

    def _create_new_profile(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Novo Perfil", "Nome do perfil:")
        if ok and name.strip():
            name = name.strip()
            if name in self._pm.list_profiles():
                QMessageBox.warning(self, "Erro", f"Perfil '{name}' já existe.")
                return
            self._pm.create_profile(name)
            self._load_profiles()
            self.profile_created.emit(name)

    def refresh(self):
        self._load_profiles()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setWindowIcon(self._create_app_icon())
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        self.setStyleSheet(get_stylesheet())

        self._multi_manager = MultiDeviceManager(max_slots=MAX_CONTROLLERS)
        self._auto_profile = AutoProfileManager(
            self._multi_manager._profile_manager
        )
        self._profile_tabs = []
        self._profiles_tab: QTabWidget = None
        self._profiles_tabs: Dict[int, "ProfileTabWidget"] = {}

        self._tray_icon: QSystemTrayIcon = None
        self._tray_menu: QMenu = None

        self._setup_tray()
        self._setup_ui()
        self._connect_signals()

    def _create_app_icon(self) -> QIcon:
        """Create the application window icon."""
        # Try SVG first
        svg_path = Path(__file__).parent / "icons" / "icon.svg"
        if svg_path.exists():
            return QIcon(str(svg_path))
        # Fallback to PNG
        icon_path = Path(__file__).parent / "icons" / "ds4linux.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        # Fallback: draw a simple icon
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 212, 170))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(8, 8, 48, 48, 12, 12)
        painter.setBrush(QColor(30, 30, 46))
        painter.drawRoundedRect(16, 20, 32, 24, 6, 6)
        painter.end()
        return QIcon(pixmap)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray not available")
            return

        self._tray_icon = QSystemTrayIcon(self)
        icon = self._create_app_icon()
        self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip(f"{APP_NAME} - DS4 Emulator")

        self._tray_menu = QMenu(self)
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_application)
        self._tray_menu.addAction(show_action)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_application(self):
        self._auto_profile.stop()
        self._multi_manager.cleanup()
        if self._tray_icon:
            self._tray_icon.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        """Properly clean up all devices before closing."""
        self._auto_profile.stop()
        self._multi_manager.cleanup()
        # Give threads time to finish
        import time; time.sleep(0.5)
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
            event.accept()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self._main_tabs = QTabWidget()
        self._main_tabs.setDocumentMode(True)
        main_layout.addWidget(self._main_tabs, 1)

        # Controllers tab (dynamic table - starts empty)
        self._controllers_table = ControllersTableWidget(self._multi_manager)
        self._controllers_table.controller_edit.connect(self._on_controller_edit)
        self._main_tabs.addTab(self._controllers_table, "Controllers")

        # Profiles tab - the single, reusable profile editor tab
        self._profiles_tab = QTabWidget()
        # We will add/remove content dynamically
        placeholder = QFrame()
        pl_layout = QVBoxLayout(placeholder)
        pl_layout.addWidget(QLabel("Select a controller and click 'Editar' to configure it."))
        pl_layout.addStretch()
        self._profiles_tab.addTab(placeholder, "Perfis")
        self._main_tabs.addTab(self._profiles_tab, "Perfis")

        # Auto Profiles tab
        self._auto_profiles_tab = AutoProfilesTab(self._auto_profile)
        self._main_tabs.addTab(self._auto_profiles_tab, "Auto Profiles")

        # Settings tab
        self._create_settings_tab()

        # Log tab
        self._create_log_tab()

        # Footer
        self._footer = QWidget()
        self._footer.setFixedHeight(36)
        self._footer.setStyleSheet("background: #252536; border-top: 1px solid #3a3a5c;")
        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(12, 0, 12, 0)

        self._status_label = QLabel("Ready - Connect your DS4 controllers")
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

        self._minimize_tray_chk = QCheckBox("Minimize to tray on close")
        self._minimize_tray_chk.setChecked(True)
        startup_layout.addRow(self._minimize_tray_chk)

        self._start_minimized = QCheckBox("Start minimized")
        startup_layout.addRow(self._start_minimized)

        self._auto_connect_chk = QCheckBox("Auto-connect all controllers on startup")
        self._auto_connect_chk.setChecked(True)
        startup_layout.addRow(self._auto_connect_chk)

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
        about_text = QLabel(
            f"{APP_NAME} v{APP_VERSION}\n"
            f"DualShock 4 Multi-Controller Emulator for Linux\n\n"
            f"Supports up to {MAX_CONTROLLERS} controllers simultaneously\n"
            f"Built with PySide6 & evdev\n\n"
            f"Inspired by DS4Windows"
        )
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
        self._stop_all_btn.clicked.connect(self._stop_all_controllers)

        for slot in self._multi_manager.get_all_slots():
            slot.log_message.connect(self._on_log_message)
            slot.status_changed.connect(self._on_slot_status_changed)
            slot.battery_update.connect(lambda pct: self._on_battery_update(pct))

        # Connect device connect/disconnect signals to update the table
        self._multi_manager.device_connected_signal.connect(self._on_device_connected)
        self._multi_manager.device_disconnected_signal.connect(self._on_device_disconnected)

        # Profile changes
        self._multi_manager._profile_manager.profiles_changed.connect(self._on_profiles_changed)

        # Auto-profile signals
        self._auto_profile.log_message.connect(self._on_log_message)
        self._auto_profile.profile_apply_requested.connect(
            self._multi_manager.apply_profile_to_all
        )

    def _on_controller_edit(self, slot_id: int):
        """Open the single Profiles tab with the selected controller's profile."""
        slot = self._multi_manager.get_slot(slot_id)
        if not slot:
            return

        # Remove existing profile editor if any
        self._profiles_tab.removeTab(0)

        # Create a new ProfileTabWidget for this controller
        profile_tab = ProfileTabWidget(slot_id, slot, self._multi_manager._profile_manager)
        profile_tab.save_requested.connect(self._on_profile_saved)
        self._profiles_tab.addTab(profile_tab, f"Controller {slot_id + 1}")

        # Switch to Profiles tab
        self._main_tabs.setCurrentWidget(self._profiles_tab)
        self._status_label.setText(f"Editing Controller {slot_id + 1} profile")

    def _on_profile_saved(self):
        """Refresh the controllers table after profile save."""
        self._controllers_table.refresh()

    def _on_device_connected(self, slot_id: int, device_path: str):
        self._controllers_table._refresh()
        connected = len(self._multi_manager.get_connected_slots())
        if connected == 0:
            self._status_label.setText("Ready - Connect your DS4 controllers")
        elif connected == 1:
            self._status_label.setText("1 controller connected")
        else:
            self._status_label.setText(f"{connected} controllers connected")

    def _on_device_disconnected(self, slot_id: int):
        self._controllers_table._refresh()
        connected = len(self._multi_manager.get_connected_slots())
        if connected == 0:
            self._status_label.setText("Ready - Connect your DS4 controllers")
        elif connected == 1:
            self._status_label.setText("1 controller connected")
        else:
            self._status_label.setText(f"{connected} controllers connected")

    def _on_profiles_changed(self):
        """Refresh profile combos when profiles are created/deleted."""
        self._controllers_table._refresh_profile_combos()

    def _on_slot_status_changed(self, status: str):
        self._controllers_table.refresh()
        connected = len(self._multi_manager.get_connected_slots())
        if connected == 0:
            self._status_label.setText("Ready - Connect your DS4 controllers")
        elif connected == 1:
            self._status_label.setText("1 controller connected")
        else:
            self._status_label.setText(f"{connected} controllers connected")

    def _on_battery_update(self, pct: int):
        self._controllers_table.refresh()

    @Slot(str)
    def _on_log_message(self, msg: str):
        self._log_text.append(msg)
        self._log_text.verticalScrollBar().setValue(
            self._log_text.verticalScrollBar().maximum()
        )

    def _stop_all_controllers(self):
        self._multi_manager.disconnect_all()
        self._controllers_table.refresh()
        self._on_log_message("All controllers stopped")

    @Slot()
    def _install_udev_rules(self):
        import subprocess
        try:
            result = subprocess.run(
                ["pkexec", "sh", "-c",
                 "cp udev/99-ds4linux.rules /etc/udev/rules.d/ && "
                 "udevadm control --reload-rules && udevadm trigger"],
                capture_output=True, text=True,
                cwd="/home/servidor/Git/Ds4linux"
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


# Fix import that was at bottom of file
from typing import Dict