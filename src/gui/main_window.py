from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..constants import APP_NAME, APP_VERSION, MAX_CONTROLLERS, PROFILE_DIR
from ..engine.auto_profile import AutoProfileManager
from ..engine.multi_device_manager import MultiDeviceManager
from .auto_profiles_tab import AutoProfilesTab
from .controller_tab import ProfileTabWidget
from .controllers_table import ControllersTableWidget
from .styles import get_stylesheet

logger = logging.getLogger(__name__)


class _LogEmitter(QObject):
    message = Signal(str)


class QtLogHandler(logging.Handler):
    """Forwards logging records to a Qt signal (thread-safe)."""

    def __init__(self):
        super().__init__()
        self.emitter = _LogEmitter()
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
        ))

    def emit(self, record):
        try:
            self.emitter.message.emit(self.format(record))
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(980, 660)
        self.setStyleSheet(get_stylesheet())
        self._settings = QSettings("DS4Linux", "DS4Linux")

        self._multi_manager = MultiDeviceManager(max_slots=MAX_CONTROLLERS)
        self._auto_profile = AutoProfileManager(self._multi_manager._profile_manager)
        self._log_handler: QtLogHandler | None = None
        self._tray: QSystemTrayIcon | None = None

        self._setup_ui()
        self._setup_tray()
        self._connect_signals()
        self._install_log_handler()
        self._update_status()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 8)
        main_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(f"{APP_NAME}")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        header.addWidget(title)
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("dimLabel")
        header.addWidget(version)
        header.addStretch()
        self.status_chip = QLabel("Nenhum controle conectado")
        self.status_chip.setObjectName("dimLabel")
        header.addWidget(self.status_chip)
        main_layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs, 1)

        self._controllers_table = ControllersTableWidget(self._multi_manager)
        self.tabs.addTab(self._controllers_table, "Controles")

        self._profiles_tab = QTabWidget()
        self._profiles_tab.setDocumentMode(True)
        self.tabs.addTab(self._profiles_tab, "Perfil")

        self.tabs.addTab(AutoProfilesTab(self._auto_profile), "Auto Perfis")
        self.tabs.addTab(self._build_settings_tab(), "Configurações")

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self.tabs.addTab(self._log_text, "Log")

        self.statusBar().showMessage("Pronto")

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        about = QGroupBox("Sobre")
        about_form = QFormLayout(about)
        about_form.addRow("Aplicativo:", QLabel(f"{APP_NAME} v{APP_VERSION}"))
        about_form.addRow("Driver:", QLabel("udev + uinput (sem root)"))
        about_form.addRow("Emulação:", QLabel("Xbox 360 / PlayStation 4"))
        layout.addWidget(about)

        setup = QGroupBox("Sistema")
        setup_layout = QVBoxLayout(setup)
        self.udev_status = QLabel()
        setup_layout.addWidget(self.udev_status)
        buttons = QHBoxLayout()
        self.check_btn = QPushButton("Verificar de novo")
        self.check_btn.clicked.connect(self._refresh_system_status)
        buttons.addWidget(self.check_btn)
        self.install_btn = QPushButton("Executar configuração...")
        self.install_btn.clicked.connect(self._run_setup_dialog)
        buttons.addWidget(self.install_btn)
        buttons.addStretch()
        setup_layout.addLayout(buttons)
        layout.addWidget(setup)

        folders = QGroupBox("Pastas")
        folders_layout = QHBoxLayout(folders)
        open_profiles = QPushButton("Abrir pasta de perfis")
        open_profiles.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(PROFILE_DIR)))
        )
        folders_layout.addWidget(open_profiles)
        folders_layout.addStretch()
        layout.addWidget(folders)

        tray_group = QGroupBox("Bandeja")
        tray_layout = QVBoxLayout(tray_group)
        self.close_to_tray_cb = QCheckBox("Fechar a janela minimiza para a bandeja")
        self.close_to_tray_cb.setChecked(
            self._settings.value("close_to_tray", True, type=bool)
        )
        self.close_to_tray_cb.toggled.connect(
            lambda v: self._settings.setValue("close_to_tray", v)
        )
        tray_layout.addWidget(self.close_to_tray_cb)
        layout.addWidget(tray_group)

        layout.addStretch()
        self._refresh_system_status()
        return page

    # ------------------------------------------------------------------
    def _setup_tray(self):
        icon_path = Path(__file__).resolve().parents[2] / "assets" / "icon.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()
        if icon.isNull():
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.transparent)
            icon = QIcon(pixmap)

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(f"{APP_NAME} — controle virtual ativo")

        menu = QMenu()
        show_action = QAction("Abrir", self)
        show_action.triggered.connect(self.show_normal)
        menu.addAction(show_action)
        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: self.show_normal() if reason == QSystemTrayIcon.Trigger else None
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()

    def _install_log_handler(self):
        self._log_handler = QtLogHandler()
        self._log_handler.emitter.message.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)

    def _append_log(self, text: str):
        self._log_text.append(text)
        # Keep the widget light
        if self._log_text.document().blockCount() > 800:
            self._log_text.clear()

    # ------------------------------------------------------------------
    def _connect_signals(self):
        self._controllers_table.controller_edit.connect(self._on_controller_edit)
        self._multi_manager.device_connected_signal.connect(self._on_devices_changed)
        self._multi_manager.device_disconnected_signal.connect(self._on_devices_changed)

    def _on_devices_changed(self, *args):
        self._update_status()

    def _update_status(self):
        connected = [s for s in self._multi_manager.get_all_slots() if s.is_connected]
        if connected:
            text = f"{len(connected)} controle(s) conectado(s)"
            self.status_chip.setText(f"● {text}")
            self.status_chip.setStyleSheet("color:#6bff6b; font-weight:bold;")
            self.statusBar().showMessage(text)
        else:
            self.status_chip.setText("○ Nenhum controle conectado")
            self.status_chip.setStyleSheet("color:#8a8fa3;")
            self.statusBar().showMessage("Aguardando controle...")

    def _refresh_system_status(self):
        try:
            from ..engine.system_checker import is_module_loaded, is_udev_rules_installed
            rules_ok = is_udev_rules_installed()
            module_ok = is_module_loaded()
        except Exception:
            rules_ok = module_ok = False
        self.udev_status.setText(
            f"Regras udev: {'✔ instaladas' if rules_ok else '✘ ausentes'}    "
            f"Módulo hid-playstation: {'✔ carregado' if module_ok else '⚠ não carregado'}"
        )
        self.udev_status.setStyleSheet(
            "color:#6bff6b;" if rules_ok else "color:#ffb454;"
        )

    def _run_setup_dialog(self):
        from .setup_dialog import SetupDialog
        dlg = SetupDialog(self)
        dlg.exec()
        self._refresh_system_status()

    # ------------------------------------------------------------------
    def _on_controller_edit(self, slot_id: int):
        logger.info("Opening profile editor for slot %s", slot_id)
        slot = self._multi_manager.get_slot(slot_id)
        if not slot:
            logger.warning("Slot %s not found", slot_id)
            return

        while self._profiles_tab.count() > 0:
            self._profiles_tab.removeTab(0)

        profile_tab = ProfileTabWidget(
            slot_id, slot, self._multi_manager._profile_manager
        )
        profile_tab.save_requested.connect(self._on_profile_saved)
        profile_tab.profile_saved.connect(self._on_profile_saved)
        self._profiles_tab.addTab(profile_tab, f"Controle {slot_id + 1}")
        self.tabs.setCurrentWidget(self._profiles_tab)

    def _on_profile_saved(self):
        self._controllers_table.refresh()

    # ------------------------------------------------------------------
    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self.cleanup()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def cleanup(self):
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None
        if self._tray is not None:
            self._tray.hide()
        try:
            self._multi_manager.cleanup()
        except Exception:
            logger.debug("cleanup failed", exc_info=True)

    def closeEvent(self, event):
        close_to_tray = self._settings.value("close_to_tray", True, type=bool)
        if close_to_tray and self._tray is not None and self._tray.isVisible():
            event.ignore()
            self.hide()
            self._tray.showMessage(
                APP_NAME,
                "Continuo rodando na bandeja para manter o controle virtual ativo.",
                QSystemTrayIcon.Information,
                3000,
            )
            return
        self.cleanup()
        super().closeEvent(event)
