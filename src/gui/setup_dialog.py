from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QProgressBar, QGroupBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot, QThread
from PySide6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)


class _SetupWorker(QThread):
    """Background thread that runs system setup commands."""

    log_signal = Signal(str)
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, list)

    def __init__(self, password: str):
        super().__init__()
        self._password = password

    def run(self):
        from ..engine.system_checker import (
            is_module_loaded, load_module,
            is_udev_rules_installed, install_udev_rules,
            scan_ds4_devices, _fix_led_permissions,
        )

        messages = []

        self.progress_signal.emit(10, "Verificando driver do kernel...")
        if not is_module_loaded():
            self.log_signal.emit("Carregando módulo hid-playstation...")
            if load_module(password=self._password):
                messages.append("✅ Driver hid-playstation carregado")
            else:
                messages.append("❌ Falha ao carregar hid-playstation")
                self.finished_signal.emit(False, messages)
                return
        else:
            messages.append("✅ Driver hid-playstation ativo")
            self.log_signal.emit("Driver hid-playstation já carregado")

        self.progress_signal.emit(40, "Verificando regras udev...")
        if not is_udev_rules_installed():
            self.log_signal.emit("Instalando regras udev...")
            ok, msg = install_udev_rules(password=self._password)
            if ok:
                messages.append("✅ Regras udev instaladas")
            else:
                messages.append(f"❌ Falha ao instalar regras udev: {msg}")
                self.finished_signal.emit(False, messages)
                return
        else:
            messages.append("✅ Regras udev já instaladas")
            self.log_signal.emit("Regras udev já instaladas")

        self.progress_signal.emit(60, "Corrigindo permissões de LED...")
        self.log_signal.emit("Corrigindo permissões dos LEDs...")
        _fix_led_permissions(password=self._password)
        messages.append("✅ Permissões de LED corrigidas")

        self.progress_signal.emit(80, "Procurando controles...")
        self.log_signal.emit("Escaneando controles conectados...")
        devices = scan_ds4_devices()

        if devices:
            for dev in devices:
                messages.append(f"✅ Controle detectado: {dev['name']} ({dev['path']})")
            self.log_signal.emit(f"{len(devices)} controle(s) encontrado(s)")
        else:
            messages.append("⚠️ Nenhum controle detectado — conecte o DS4 e reinicie")
            self.log_signal.emit("Nenhum controle DS4 encontrado")

        self.progress_signal.emit(100, "Conclusão...")
        success = all("❌" not in m for m in messages)
        self.finished_signal.emit(success, messages)


class SetupDialog(QDialog):
    """
    First-launch dialog: asks for sudo password ONCE, runs system setup,
    saves password for future use. All automatic after that.
    """

    setup_complete = Signal(bool, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração do Sistema — DS4Linux")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMinimumSize(480, 340)
        self._setup_ui()
        self._worker = None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        self.setStyleSheet("""
            QDialog {
                background: #1e1e2e;
                border: 1px solid #3a3a5c;
                border-radius: 12px;
            }
            QLabel { color: #e0e0e0; }
        """)

        # Title
        title = QLabel("🎮 Configuração Inicial do DS4Linux")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d4aa;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "O DS4Linux precisa configurar o sistema uma única vez. "
            "Digite sua senha de administrador (sudo) e clique em 'Configurar'. "
            "A senha será salva criptografada e usada automaticamente nas próximas vezes."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(desc)

        # Password field
        pw_group = QGroupBox("Senha de Administrador (sudo)")
        pw_layout = QHBoxLayout(pw_group)
        self._pw_input = QLineEdit()
        self._pw_input.setEchoMode(QLineEdit.Password)
        self._pw_input.setPlaceholderText("Digite sua senha sudo...")
        self._pw_input.setMinimumHeight(36)
        self._pw_input.setStyleSheet("""
            QLineEdit {
                background: #252536;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                color: #e0e0e0;
                padding: 4px 10px;
                font-size: 14px;
            }
            QLineEdit:focus { border-color: #00d4aa; }
        """)
        self._pw_input.returnPressed.connect(self._start_setup)
        pw_layout.addWidget(self._pw_input)
        layout.addWidget(pw_group)

        # Remember checkbox
        self._remember_chk = QCheckBox("Lembrar senha para uso automático")
        self._remember_chk.setChecked(True)
        self._remember_chk.setStyleSheet("color: #a0a0b0; font-size: 12px;")
        layout.addWidget(self._remember_chk)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #252536;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                text-align: center;
                color: #00d4aa;
                font-weight: bold;
                height: 24px;
            }
            QProgressBar::chunk { background: #00d4aa; border-radius: 5px; }
        """)
        layout.addWidget(self._progress)

        # Status label
        self._status_label = QLabel("Aguardando senha...")
        self._status_label.setStyleSheet("color: #a0a0b0; font-size: 12px;")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        # Log area
        self._log_text = QLabel("")
        self._log_text.setWordWrap(True)
        self._log_text.setStyleSheet("color: #808090; font-size: 11px; font-family: monospace;")
        self._log_text.setMinimumHeight(70)
        layout.addWidget(self._log_text)

        # Buttons
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("Configurar Agora")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setFixedHeight(40)
        self._start_btn.clicked.connect(self._start_setup)
        btn_layout.addWidget(self._start_btn)

        self._cancel_btn = QPushButton("Pular")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    @Slot()
    def _start_setup(self):
        password = self._pw_input.text().strip()
        if not password:
            QMessageBox.warning(self, "Senha necessária", "Por favor, digite a senha sudo.")
            return

        self._start_btn.setEnabled(False)
        self._pw_input.setEnabled(False)
        self._status_label.setText("Executando configuração do sistema...")
        self._log_text.setText("")

        # Save password if checkbox is checked
        from ..engine.system_checker import _store_password
        if self._remember_chk.isChecked():
            _store_password(password)

        self._worker = _SetupWorker(password)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.log_signal.connect(self._on_log)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    @Slot(int, str)
    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._status_label.setText(msg)

    @Slot(str)
    def _on_log(self, msg: str):
        current = self._log_text.text()
        self._log_text.setText(current + "\n" + msg if current else msg)

    @Slot(bool, list)
    def _on_finished(self, success: bool, messages: list):
        self._start_btn.setEnabled(True)
        self._pw_input.setEnabled(True)

        result_text = "\n".join(f"  {m}" for m in messages)
        self._log_text.setText(result_text)

        if success:
            self._status_label.setStyleSheet("color: #6bff6b; font-size: 13px; font-weight: bold;")
            self._status_label.setText("✅ Configuração concluída com sucesso!")
            self.setup_complete.emit(True, messages)
            self.accept()
        else:
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 13px; font-weight: bold;")
            self._status_label.setText("❌ Parte da configuração falhou")
            QMessageBox.warning(
                self, "Configuração incompleta",
                "Algumas etapas falharam. Verifique o log acima.\n\n"
                "Você pode tentar novamente ou pular e configurar manualmente depois."
            )
            self.setup_complete.emit(False, messages)
            self._start_btn.setEnabled(True)
            self._pw_input.setEnabled(True)

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.setup_complete.emit(False, [])
        self.reject()
