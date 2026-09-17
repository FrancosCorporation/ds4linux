from __future__ import annotations
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QListWidget, QStackedWidget, QLabel, QTextEdit
)
from PySide6.QtCore import Qt, QSettings
from ..constants import APP_NAME, APP_VERSION, MAX_CONTROLLERS
from ..engine.multi_device_manager import MultiDeviceManager
from ..engine.auto_profile import AutoProfileManager
from .styles import get_stylesheet
from .controllers_table import ControllersTableWidget
from .controller_tab import ProfileTabWidget
from .auto_profiles_tab import AutoProfilesTab

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(get_stylesheet())
        self._multi_manager = MultiDeviceManager(max_slots=MAX_CONTROLLERS)
        self._auto_profile = AutoProfileManager(self._multi_manager._profile_manager)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Initialize Stack FIRST
        self._stack = QStackedWidget()

        # 2. Sidebar Navigation
        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(200)
        self._nav_list.addItems(["Controllers", "Perfis", "Auto Profiles", "Settings", "Log"])
        self._nav_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        main_layout.addWidget(self._nav_list)

        # 3. Add Stack to Layout
        main_layout.addWidget(self._stack)

        # 4. Add pages to Stack
        self._controllers_table = ControllersTableWidget(self._multi_manager)
        self._stack.addWidget(self._controllers_table)

        self._profiles_tab = QTabWidget()
        self._stack.addWidget(self._profiles_tab)

        self._stack.addWidget(AutoProfilesTab(self._auto_profile))
        
        self._stack.addWidget(QLabel("Settings Placeholder"))
        
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._stack.addWidget(self._log_text)
        
        self._nav_list.setCurrentRow(0)

    def _connect_signals(self):
        self._controllers_table.controller_edit.connect(self._on_controller_edit)

    def _on_controller_edit(self, slot_id: int):
        logger.info(f"Clicou em Editar para slot_id={slot_id}")
        slot = self._multi_manager.get_slot(slot_id)
        if not slot:
            logger.warning(f"Slot {slot_id} não encontrado")
            return

        while self._profiles_tab.count() > 0:
            self._profiles_tab.removeTab(0)

        profile_tab = ProfileTabWidget(slot_id, slot, self._multi_manager._profile_manager)
        profile_tab.save_requested.connect(self._on_profile_saved)
        profile_tab.profile_saved.connect(self._on_profile_saved)
        self._profiles_tab.addTab(profile_tab, f"Controller {slot_id + 1}")

        self._nav_list.setCurrentRow(1) # Switch to Profiles stack page

    def _on_profile_saved(self):
        self._controllers_table.refresh()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()
