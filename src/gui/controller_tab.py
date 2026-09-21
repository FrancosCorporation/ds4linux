from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config.profile_manager import ProfileManager
from ..constants import DS4Btn
from ..engine.input_mapper import AxisConfig, ProfileConfig, TriggerConfig
from ..engine.virtual_device import VirtualDeviceType as VDT
from .color_dialog import ColorDialog
from .mapping_tab import MappingTabWidget
from .styles import get_stylesheet

logger = logging.getLogger(__name__)

LED_PRESETS = [
    ("Ciano", (0, 212, 170)),
    ("Azul", (0, 90, 255)),
    ("Roxo", (150, 60, 255)),
    ("Rosa", (255, 60, 150)),
    ("Vermelho", (255, 40, 40)),
    ("Verde", (40, 220, 90)),
    ("Laranja", (255, 140, 0)),
    ("Branco", (255, 255, 255)),
]


class _ScrollPage(QScrollArea):
    """Scrollable page used inside the profile editor tabs."""

    def __init__(self, content: QWidget):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidget(content)


class ProfileEditorWindow(QWidget):
    """DS4Windows-style per-controller profile editor.

    Layout::

        Perfil: [nome]  [Salvar] [Cancelar]   [Emular: Xbox/PS4]
        ┌ Controles | Leituras ┐ ┌ Eixos | Lightbar | Gyro | Outros ┐
        │  imagem + mapeamentos│ │  configurações avançadas          │
        └──────────────────────┘ └───────────────────────────────────┘
        Controle 1 usando o perfil "X"                          [Parar]
    """

    save_requested = Signal()
    profile_saved = Signal(str)

    def __init__(self, slot_id: int, slot, profile_manager, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.slot = slot
        self.profile_manager = profile_manager or ProfileManager()
        self._current_profile: ProfileConfig | None = None
        self._settings = QSettings("DS4Linux", "DS4Linux")
        self.setStyleSheet(get_stylesheet())

        self._setup_ui()
        self._connect_signals()
        self._load_current_profile()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(10)

        # ---------------- header ----------------
        header = QHBoxLayout()
        header.setSpacing(8)

        header.addWidget(QLabel("Perfil:"))
        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.setPlaceholderText("Nome do perfil...")
        self.profile_name_edit.setMinimumWidth(180)
        header.addWidget(self.profile_name_edit)

        self.save_btn = QPushButton("Salvar")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._save_profile)
        header.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self._cancel_profile)
        header.addWidget(self.cancel_btn)

        header.addSpacing(12)
        header.addWidget(QLabel("Emular:"))
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItem("Xbox 360", VDT.XBOX)
        self.device_type_combo.addItem("PlayStation 4", VDT.PS4)
        header.addWidget(self.device_type_combo)

        header.addStretch()
        self.keep_size_cb = QCheckBox("Manter o tamanho da janela ao fechar")
        header.addWidget(self.keep_size_cb)
        root.addLayout(header)

        # ---------------- body ----------------
        body = QHBoxLayout()
        body.setSpacing(12)

        self.left_tabs = QTabWidget()
        self.left_tabs.setDocumentMode(True)
        self.left_tabs.addTab(self._build_controls_tab(), "Controles")
        self.left_tabs.addTab(self._build_readings_tab(), "Leituras")
        body.addWidget(self.left_tabs, 3)

        self.right_tabs = QTabWidget()
        self.right_tabs.setDocumentMode(True)
        self.right_tabs.addTab(_ScrollPage(self._build_axis_tab()), "Eixos")
        self.right_tabs.addTab(_ScrollPage(self._build_lightbar_tab()), "Lightbar")
        self.right_tabs.addTab(_ScrollPage(self._build_gyro_tab()), "Gyro")
        self.right_tabs.addTab(_ScrollPage(self._build_other_tab()), "Outros")
        body.addWidget(self.right_tabs, 2)

        root.addLayout(body, 1)

        # ---------------- footer ----------------
        footer = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("dimLabel")
        footer.addWidget(self.status_label)
        footer.addStretch()
        self.stop_btn = QPushButton("Parar")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setToolTip("Interromper a emulação deste controle")
        self.stop_btn.clicked.connect(self._stop_controller)
        footer.addWidget(self.stop_btn)
        root.addLayout(footer)

    # ------------------------------------------------------------------
    def _build_controls_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        self.mapping_tab = MappingTabWidget(
            worker=self.slot.worker if self.slot is not None else None
        )
        layout.addWidget(self.mapping_tab, 3)

        side = QVBoxLayout()
        side.setSpacing(10)

        touchpad_group = QGroupBox("Touchpad")
        touchpad_form = QFormLayout(touchpad_group)
        touchpad_form.setSpacing(8)
        self.touchpad_mode = QComboBox()
        self.touchpad_mode.addItems(["Desativado", "Modo Mouse", "Modo Controles"])
        touchpad_form.addRow("Modo:", self.touchpad_mode)
        self.touchpad_jitter = QDoubleSpinBox()
        self.touchpad_jitter.setRange(0.0, 1.0)
        self.touchpad_jitter.setSingleStep(0.05)
        self.touchpad_jitter.setDecimals(2)
        touchpad_form.addRow("Jitter:", self.touchpad_jitter)
        side.addWidget(touchpad_group)

        rumble_group = QGroupBox("Vibração")
        rumble_form = QFormLayout(rumble_group)
        rumble_form.setSpacing(8)
        self.rumble_enable = QCheckBox("Habilitar vibração")
        self.rumble_enable.setChecked(True)
        rumble_form.addRow(self.rumble_enable)
        self.rumble_intensity = QSpinBox()
        self.rumble_intensity.setRange(0, 100)
        self.rumble_intensity.setValue(100)
        self.rumble_intensity.setSuffix(" %")
        rumble_form.addRow("Intensidade:", self.rumble_intensity)
        self.rumble_test_btn = QPushButton("Testar vibração")
        self.rumble_test_btn.clicked.connect(self._test_rumble)
        rumble_form.addRow(self.rumble_test_btn)
        side.addWidget(rumble_group)

        side.addStretch()
        layout.addLayout(side, 2)
        return page

    # ------------------------------------------------------------------
    def _build_readings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel("Pressione botões e mova os analógicos para conferir a leitura ao vivo.")
        info.setObjectName("dimLabel")
        info.setWordWrap(True)
        layout.addWidget(info)

        sticks_group = QGroupBox("Analógicos")
        sticks = QFormLayout(sticks_group)
        sticks.setSpacing(8)

        def make_bar(lo, hi):
            bar = QProgressBar()
            bar.setRange(lo, hi)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(14)
            return bar

        self.ls_x_bar = make_bar(-32768, 32767)
        self.ls_y_bar = make_bar(-32768, 32767)
        self.rs_x_bar = make_bar(-32768, 32767)
        self.rs_y_bar = make_bar(-32768, 32767)
        sticks.addRow("LS X:", self.ls_x_bar)
        sticks.addRow("LS Y:", self.ls_y_bar)
        sticks.addRow("RS X:", self.rs_x_bar)
        sticks.addRow("RS Y:", self.rs_y_bar)
        layout.addWidget(sticks_group)

        triggers_group = QGroupBox("Gatilhos (L2 / R2)")
        triggers = QFormLayout(triggers_group)
        triggers.setSpacing(8)
        self.l2_bar = make_bar(0, 255)
        self.r2_bar = make_bar(0, 255)
        triggers.addRow("L2:", self.l2_bar)
        triggers.addRow("R2:", self.r2_bar)
        layout.addWidget(triggers_group)

        buttons_group = QGroupBox("Botões e direcionais")
        grid = QGridLayout(buttons_group)
        grid.setSpacing(6)

        self.btn_states: dict[int, QLabel] = {}
        all_btns = [
            (DS4Btn.SOUTH, "✕"), (DS4Btn.EAST, "○"),
            (DS4Btn.NORTH, "△"), (DS4Btn.WEST, "□"),
            (DS4Btn.DPAD_UP, "↑"), (DS4Btn.DPAD_DOWN, "↓"),
            (DS4Btn.DPAD_LEFT, "←"), (DS4Btn.DPAD_RIGHT, "→"),
            (DS4Btn.TL, "L1"), (DS4Btn.TR, "R1"),
            (DS4Btn.TL2, "L2"), (DS4Btn.TR2, "R2"),
            (DS4Btn.SELECT, "Share"), (DS4Btn.START, "Options"),
            (DS4Btn.THUMBL, "L3"), (DS4Btn.THUMBR, "R3"),
            (DS4Btn.PS, "PS"), (DS4Btn.TOUCHPAD, "Touch"),
        ]
        for i, (code, label) in enumerate(all_btns):
            row, col = divmod(i, 6)
            name = QLabel(label)
            name.setStyleSheet("color:#9aa0b4; font-size:11px;")
            state = QLabel("○")
            state.setAlignment(Qt.AlignCenter)
            state.setStyleSheet("font-size:14px; color:#5a5f73;")
            self.btn_states[code] = state
            grid.addWidget(name, row, col * 2)
            grid.addWidget(state, row, col * 2 + 1)
        layout.addWidget(buttons_group)

        self.connection_status = QLabel("Conectado: nenhum controle")
        self.connection_status.setStyleSheet("color:#ff6b6b; font-weight:bold;")
        layout.addWidget(self.connection_status)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    def _build_axis_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        sticks_group = QGroupBox("Analógicos (LS / RS)")
        grid = QGridLayout(sticks_group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(self._header_label(""), 0, 0)
        grid.addWidget(self._header_label("LS"), 0, 1)
        grid.addWidget(self._header_label("RS"), 0, 2)

        self.ls_deadzone = self._double(0.0, 0.99, 0.15)
        self.rs_deadzone = self._double(0.0, 0.99, 0.15)
        self._grid_row(grid, 1, "Dead Zone:", self.ls_deadzone, self.rs_deadzone)

        self.ls_maxzone = self._double(0.1, 1.0, 1.0)
        self.rs_maxzone = self._double(0.1, 1.0, 1.0)
        self._grid_row(grid, 2, "Max Zone:", self.ls_maxzone, self.rs_maxzone)

        self.ls_antideadzone = self._double(0.0, 0.99, 0.0)
        self.rs_antideadzone = self._double(0.0, 0.99, 0.0)
        self._grid_row(grid, 3, "Anti-dead Zone:", self.ls_antideadzone, self.rs_antideadzone)

        self.ls_sensitivity = self._double(0.1, 5.0, 1.0)
        self.rs_sensitivity = self._double(0.1, 5.0, 1.0)
        self._grid_row(grid, 4, "Sensitivity:", self.ls_sensitivity, self.rs_sensitivity)

        self.ls_curve = QComboBox()
        self.rs_curve = QComboBox()
        for combo in (self.ls_curve, self.rs_curve):
            combo.addItems(["Linear", "Exponential", "Quadratic"])
        self._grid_row(grid, 5, "Output Curve:", self.ls_curve, self.rs_curve)

        self.ls_square = QCheckBox()
        self.rs_square = QCheckBox()
        self._grid_row(grid, 6, "Square Stick:", self.ls_square, self.rs_square)

        self.ls_square_value = self._double(0.0, 50.0, 5.0, suffix=" %")
        self.rs_square_value = self._double(0.0, 50.0, 5.0, suffix=" %")
        self._grid_row(grid, 7, "Square Value:", self.ls_square_value, self.rs_square_value)

        self.ls_rotation = QSpinBox()
        self.rs_rotation = QSpinBox()
        for spin in (self.ls_rotation, self.rs_rotation):
            spin.setRange(-180, 180)
            spin.setSuffix(" °")
        self._grid_row(grid, 8, "Rotation:", self.ls_rotation, self.rs_rotation)

        self.ls_inverted = QCheckBox()
        self.rs_inverted = QCheckBox()
        self._grid_row(grid, 9, "Invertido:", self.ls_inverted, self.rs_inverted)
        layout.addWidget(sticks_group)

        triggers_group = QGroupBox("Gatilhos (L2 / R2)")
        tgrid = QGridLayout(triggers_group)
        tgrid.setHorizontalSpacing(10)
        tgrid.setVerticalSpacing(8)
        tgrid.addWidget(self._header_label(""), 0, 0)
        tgrid.addWidget(self._header_label("L2"), 0, 1)
        tgrid.addWidget(self._header_label("R2"), 0, 2)

        self.lt_deadzone = self._double(0.0, 0.99, 0.05)
        self.rt_deadzone = self._double(0.0, 0.99, 0.05)
        self._grid_row(tgrid, 1, "Dead Zone:", self.lt_deadzone, self.rt_deadzone)

        self.lt_maxzone = self._double(0.1, 1.0, 1.0)
        self.rt_maxzone = self._double(0.1, 1.0, 1.0)
        self._grid_row(tgrid, 2, "Max Zone:", self.lt_maxzone, self.rt_maxzone)

        self.lt_antideadzone = self._double(0.0, 0.99, 0.0)
        self.rt_antideadzone = self._double(0.0, 0.99, 0.0)
        self._grid_row(tgrid, 3, "Anti-dead Zone:", self.lt_antideadzone, self.rt_antideadzone)

        self.lt_sensitivity = self._double(0.1, 5.0, 1.0)
        self.rt_sensitivity = self._double(0.1, 5.0, 1.0)
        self._grid_row(tgrid, 4, "Sensitivity:", self.lt_sensitivity, self.rt_sensitivity)
        layout.addWidget(triggers_group)

        layout.addStretch()
        return page

    @staticmethod
    def _header_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("columnHeader")
        label.setAlignment(Qt.AlignCenter)
        return label

    @staticmethod
    def _double(lo, hi, value, suffix="", step=0.01) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        spin.setMaximumWidth(110)
        return spin

    @staticmethod
    def _grid_row(grid: QGridLayout, row: int, label: str, left, right):
        text = QLabel(label)
        grid.addWidget(text, row, 0)
        grid.addWidget(left, row, 1)
        grid.addWidget(right, row, 2)

    # ------------------------------------------------------------------
    def _build_lightbar_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        color_group = QGroupBox("Cor")
        color_layout = QVBoxLayout(color_group)
        color_layout.setSpacing(10)

        self.lightbar_preview = QLabel()
        self.lightbar_preview.setFixedHeight(42)
        self.lightbar_preview.setStyleSheet(
            "background:#00d4aa; border-radius:8px; border:1px solid #3a3a5c;"
        )
        color_layout.addWidget(self.lightbar_preview)

        self.lightbar_pick_btn = QPushButton("Escolher cor...")
        self.lightbar_pick_btn.clicked.connect(self._pick_lightbar_color)
        color_layout.addWidget(self.lightbar_pick_btn)

        presets = QGridLayout()
        self._preset_buttons = []
        for i, (name, rgb) in enumerate(LED_PRESETS):
            btn = QPushButton(name)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                f"QPushButton {{ background: rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                " color: #101018; font-weight: bold; border-radius: 6px; }"
            )
            btn.clicked.connect(lambda _c=False, c=rgb: self._set_led_color(c))
            presets.addWidget(btn, i // 4, i % 4)
            self._preset_buttons.append(btn)
        color_layout.addLayout(presets)
        layout.addWidget(color_group)

        brightness_group = QGroupBox("Brilho")
        brightness_layout = QVBoxLayout(brightness_group)
        row = QHBoxLayout()
        self.lightbar_brightness = QSlider(Qt.Horizontal)
        self.lightbar_brightness.setRange(0, 255)
        self.lightbar_brightness.setValue(255)
        self.lightbar_brightness_label = QLabel("255")
        self.lightbar_brightness.valueChanged.connect(
            lambda v: self.lightbar_brightness_label.setText(str(v))
        )
        row.addWidget(self.lightbar_brightness, 1)
        row.addWidget(self.lightbar_brightness_label)
        brightness_layout.addLayout(row)
        layout.addWidget(brightness_group)

        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    def _build_gyro_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        group = QGroupBox("Giroscópio")
        form = QFormLayout(group)
        form.setSpacing(8)
        self.gyro_enable = QCheckBox("Habilitar giroscópio")
        form.addRow(self.gyro_enable)
        self.gyro_mode = QComboBox()
        self.gyro_mode.addItems(["Desativado", "Mouse", "Mouse (só ao mirar)"])
        form.addRow("Modo:", self.gyro_mode)
        self.gyro_sensitivity = self._double(0.1, 10.0, 1.0)
        form.addRow("Sensibilidade:", self.gyro_sensitivity)
        self.gyro_calibrate_btn = QPushButton("Calibrar")
        form.addRow(self.gyro_calibrate_btn)
        layout.addWidget(group)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    def _build_other_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        led_group = QGroupBox("Comportamento do LED")
        led_layout = QFormLayout(led_group)
        led_layout.setSpacing(8)
        self.led_mode = QComboBox()
        self.led_mode.addItems([
            "Cor fixa do perfil",
            "Indicador de bateria",
            "Pulsar",
            "Arco-íris",
        ])
        led_layout.addRow("Modo:", self.led_mode)
        layout.addWidget(led_group)

        conn_group = QGroupBox("Conexão")
        conn_layout = QFormLayout(conn_group)
        conn_layout.setSpacing(8)
        self.auto_reconnect = QCheckBox("Reconectar automaticamente")
        self.auto_reconnect.setChecked(True)
        conn_layout.addRow(self.auto_reconnect)
        self.poll_rate = QComboBox()
        self._poll_values = [1, 2, 4, 10]
        self.poll_rate.addItems([
            "1 ms (1000 Hz)", "2 ms (500 Hz)", "4 ms (250 Hz)", "10 ms (100 Hz)",
        ])
        conn_layout.addRow("Polling:", self.poll_rate)
        layout.addWidget(conn_group)

        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.device_type_combo.currentIndexChanged.connect(self._on_device_type_changed)
        self.lightbar_brightness.valueChanged.connect(self._on_lightbar_brightness)
        self.gyro_calibrate_btn.clicked.connect(
            lambda: QMessageBox.information(self, "Gyro", "Calibração registrada.")
        )
        worker = self.slot.worker if self.slot is not None else None
        if worker is not None:
            try:
                worker.raw_event.connect(self._on_raw_event)
                self._raw_worker = worker
            except Exception:
                logger.debug("Could not connect worker.raw_event", exc_info=True)

    # ------------------------------------------------------------------
    # Profile load/save
    # ------------------------------------------------------------------
    def _load_current_profile(self):
        name = self.profile_manager.get_current_profile_name() or "Default"
        self._current_profile = self.profile_manager.load_profile(name)
        if not self._current_profile:
            self._current_profile = ProfileConfig(name="Default")
        self.profile_name_edit.setText(self._current_profile.name)
        self._apply_profile_to_ui()

    def _apply_profile_to_ui(self):
        profile = self._current_profile
        if not profile:
            return

        # Keep the combo quiet while we sync it
        self.device_type_combo.blockSignals(True)
        idx = self.device_type_combo.findData(profile.device_type)
        if idx >= 0:
            self.device_type_combo.setCurrentIndex(idx)
        self.device_type_combo.blockSignals(False)

        self.mapping_tab.set_device_type(profile.device_type)
        self.mapping_tab.set_mappings(profile.button_maps)

        self._fill_axis_widgets(profile.left_stick, self.ls_deadzone, self.ls_maxzone,
                                self.ls_antideadzone, self.ls_sensitivity, self.ls_curve,
                                self.ls_square, self.ls_square_value, self.ls_rotation,
                                self.ls_inverted)
        self._fill_axis_widgets(profile.right_stick, self.rs_deadzone, self.rs_maxzone,
                                self.rs_antideadzone, self.rs_sensitivity, self.rs_curve,
                                self.rs_square, self.rs_square_value, self.rs_rotation,
                                self.rs_inverted)
        self._fill_trigger_widgets(profile.left_trigger, self.lt_deadzone, self.lt_maxzone,
                                   self.lt_antideadzone, self.lt_sensitivity)
        self._fill_trigger_widgets(profile.right_trigger, self.rt_deadzone, self.rt_maxzone,
                                   self.rt_antideadzone, self.rt_sensitivity)

        self._set_led_color(profile.led_color, update_profile=False)
        self.lightbar_brightness.setValue(profile.led_brightness)
        poll_index = self._poll_values.index(profile.poll_rate_ms) \
            if profile.poll_rate_ms in self._poll_values else len(self._poll_values) - 1
        self.poll_rate.setCurrentIndex(poll_index)

        self._update_status_label()

    @staticmethod
    def _fill_axis_widgets(cfg: AxisConfig, deadzone, maxzone, antideadzone,
                           sensitivity, curve, square, square_value, rotation, inverted):
        deadzone.setValue(cfg.deadzone)
        maxzone.setValue(cfg.max_zone)
        antideadzone.setValue(cfg.anti_deadzone)
        sensitivity.setValue(cfg.sensitivity)
        index = curve.findText(cfg.output_curve)
        curve.setCurrentIndex(index if index >= 0 else 0)
        square.setChecked(cfg.square_stick)
        square_value.setValue(cfg.square_stick_value)
        rotation.setValue(cfg.rotation)
        inverted.setChecked(cfg.inverted)

    @staticmethod
    def _fill_trigger_widgets(cfg: TriggerConfig, deadzone, maxzone, antideadzone, sensitivity):
        deadzone.setValue(cfg.deadzone)
        maxzone.setValue(cfg.max_zone)
        antideadzone.setValue(cfg.anti_deadzone)
        sensitivity.setValue(cfg.sensitivity)

    def _save_profile(self):
        name = self.profile_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nome vazio", "Informe um nome para o perfil.")
            return

        profile = self._current_profile or ProfileConfig(name=name)
        profile.name = name
        profile.device_type = self.device_type_combo.currentData() or VDT.XBOX
        profile.button_maps = self.mapping_tab.get_mappings()

        profile.left_stick = AxisConfig(
            deadzone=self.ls_deadzone.value(),
            max_zone=self.ls_maxzone.value(),
            anti_deadzone=self.ls_antideadzone.value(),
            sensitivity=self.ls_sensitivity.value(),
            output_curve=self.ls_curve.currentText(),
            square_stick=self.ls_square.isChecked(),
            square_stick_value=self.ls_square_value.value(),
            rotation=self.ls_rotation.value(),
            inverted=self.ls_inverted.isChecked(),
        )
        profile.right_stick = AxisConfig(
            deadzone=self.rs_deadzone.value(),
            max_zone=self.rs_maxzone.value(),
            anti_deadzone=self.rs_antideadzone.value(),
            sensitivity=self.rs_sensitivity.value(),
            output_curve=self.rs_curve.currentText(),
            square_stick=self.rs_square.isChecked(),
            square_stick_value=self.rs_square_value.value(),
            rotation=self.rs_rotation.value(),
            inverted=self.rs_inverted.isChecked(),
        )
        profile.left_trigger = TriggerConfig(
            deadzone=self.lt_deadzone.value(),
            max_zone=self.lt_maxzone.value(),
            anti_deadzone=self.lt_antideadzone.value(),
            sensitivity=self.lt_sensitivity.value(),
        )
        profile.right_trigger = TriggerConfig(
            deadzone=self.rt_deadzone.value(),
            max_zone=self.rt_maxzone.value(),
            anti_deadzone=self.rt_antideadzone.value(),
            sensitivity=self.rt_sensitivity.value(),
        )
        profile.led_brightness = self.lightbar_brightness.value()
        profile.poll_rate_ms = self._poll_values[self.poll_rate.currentIndex()]
        self._current_profile = profile

        if not self.profile_manager.save_profile(name, profile):
            QMessageBox.critical(self, "Erro", "Não foi possível salvar o perfil.")
            return

        if self.slot is not None:
            self.slot.set_profile(profile)

        self.profile_saved.emit(name)
        self.save_requested.emit()
        self._update_status_label()
        logger.info("Profile saved: %s", name)

    def _cancel_profile(self):
        self._load_current_profile()
        logger.info("Profile edit cancelled")

    def _on_device_type_changed(self):
        device_type = self.device_type_combo.currentData()
        if not device_type:
            return
        self.mapping_tab.set_device_type(device_type)
        if self.slot is not None and self.slot.virtual_device is not None:
            self.slot.virtual_device.set_device_type(device_type)

    def _set_led_color(self, rgb, update_profile=True):
        color = QColor(*rgb)
        self.lightbar_preview.setStyleSheet(
            f"background:{color.name()}; border-radius:8px; border:1px solid #3a3a5c;"
        )
        if update_profile and self._current_profile:
            self._current_profile.led_color = (color.red(), color.green(), color.blue())
        if self.slot is not None and hasattr(self.slot, "set_led_color"):
            try:
                self.slot.set_led_color(color.red(), color.green(), color.blue())
            except Exception:
                logger.debug("Failed to push LED color to slot", exc_info=True)

    def _pick_lightbar_color(self):
        current = QColor(*(self._current_profile.led_color if self._current_profile else (0, 212, 170)))
        color = ColorDialog.get_color_static(current, self)
        if color.isValid():
            self._set_led_color((color.red(), color.green(), color.blue()))

    def _on_lightbar_brightness(self, value: int):
        if self._current_profile:
            self._current_profile.led_brightness = value

    # ------------------------------------------------------------------
    # Live readings
    # ------------------------------------------------------------------
    def _on_raw_event(self, event_type: int, code: int, value: int):
        from evdev import ecodes as e

        if event_type == e.EV_KEY:
            ds4_code = {
                e.BTN_SOUTH: DS4Btn.SOUTH, e.BTN_EAST: DS4Btn.EAST,
                e.BTN_NORTH: DS4Btn.NORTH, e.BTN_WEST: DS4Btn.WEST,
                e.BTN_TL: DS4Btn.TL, e.BTN_TR: DS4Btn.TR,
                e.BTN_THUMBL: DS4Btn.THUMBL, e.BTN_THUMBR: DS4Btn.THUMBR,
                e.BTN_START: DS4Btn.START, e.BTN_SELECT: DS4Btn.SELECT,
                e.BTN_MODE: DS4Btn.PS,
                e.BTN_TOUCH: DS4Btn.TOUCHPAD,
                e.BTN_DPAD_UP: DS4Btn.DPAD_UP, e.BTN_DPAD_DOWN: DS4Btn.DPAD_DOWN,
                e.BTN_DPAD_LEFT: DS4Btn.DPAD_LEFT, e.BTN_DPAD_RIGHT: DS4Btn.DPAD_RIGHT,
            }.get(code)
            if ds4_code is not None:
                self._set_button_state(ds4_code, value == 1)

        elif event_type == e.EV_ABS:
            if code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                if code == e.ABS_HAT0X:
                    self._hat_x = value
                else:
                    self._hat_y = value
                self._set_button_state(DS4Btn.DPAD_LEFT, self._hat_x < 0)
                self._set_button_state(DS4Btn.DPAD_RIGHT, self._hat_x > 0)
                self._set_button_state(DS4Btn.DPAD_UP, self._hat_y < 0)
                self._set_button_state(DS4Btn.DPAD_DOWN, self._hat_y > 0)
                return

            bars = {
                e.ABS_X: self.ls_x_bar, e.ABS_Y: self.ls_y_bar,
                e.ABS_RX: self.rs_x_bar, e.ABS_RY: self.rs_y_bar,
                e.ABS_Z: self.l2_bar, e.ABS_RZ: self.r2_bar,
            }
            bar = bars.get(code)
            if bar is not None:
                if code in (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY) and -255 <= value <= 255:
                    value = int((value - 128) * 258)
                bar.setValue(max(bar.minimum(), min(bar.maximum(), value)))

    _hat_x = 0
    _hat_y = 0

    def _set_button_state(self, code: int, pressed: bool):
        label = self.btn_states.get(code)
        if label is None:
            return
        label.setText("●" if pressed else "○")
        label.setStyleSheet(
            "font-size:14px; color:#00d4aa;" if pressed
            else "font-size:14px; color:#5a5f73;"
        )

    def set_connected(self, connected: bool, device_name: str = ""):
        if connected:
            self.connection_status.setText(f"Conectado: {device_name or 'controle'}")
            self.connection_status.setStyleSheet("color:#6bff6b; font-weight:bold;")
        else:
            self.connection_status.setText("Conectado: nenhum controle")
            self.connection_status.setStyleSheet("color:#ff6b6b; font-weight:bold;")

    def _update_status_label(self):
        name = self._current_profile.name if self._current_profile else "?"
        self.status_label.setText(
            f"Controle {self.slot_id + 1} usando o perfil \"{name}\""
        )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _test_rumble(self):
        if self.slot is not None and self.slot.physical_device is not None:
            try:
                from evdev import ecodes as e
                self.slot.physical_device.write(e.EV_FF, 0x50, 0xFFFF)
                self.slot.physical_device.syn()
                QMessageBox.information(self, "Vibração", "Teste enviado ao controle.")
                return
            except Exception as ex:
                logger.debug("Rumble test failed: %s", ex)
        QMessageBox.information(self, "Vibração", "Controle não conectado.")

    def _stop_controller(self):
        if self.slot is None:
            return
        try:
            self.slot.stop_worker()
        except Exception:
            logger.debug("stop_worker failed", exc_info=True)
        self.status_label.setText(f"Controle {self.slot_id + 1} parado.")

    def closeEvent(self, event):
        # Drop the worker.raw_event connection so closing the editor doesn't
        # leave a dangling slot on a long-lived ControllerSlot worker.
        raw_worker = getattr(self, "_raw_worker", None)
        if raw_worker is not None:
            try:
                raw_worker.raw_event.disconnect(self._on_raw_event)
            except (RuntimeError, TypeError):
                pass
            self._raw_worker = None

        if self.keep_size_cb.isChecked():
            self._settings.setValue("profile_editor/geometry", self.saveGeometry())
        else:
            self._settings.remove("profile_editor/geometry")
        super().closeEvent(event)


class ProfileTabWidget(ProfileEditorWindow):
    """Backwards-compatible alias."""
    pass
