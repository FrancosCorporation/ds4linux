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
    QScrollArea, QStyle, QMessageBox, QButtonGroup, QProgressBar,
    QSpacerItem, QSizePolicy
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


class ProfileEditorWindow(QWidget):
    """
    Full profile editor window mirroring DS4Windows layout.
    
    Structure:
    - FIXED HEADER: Profile name, Save/Cancel buttons
    - QTabWidget: Controls | Shift Modifier | Controller Readings
    - CONTROLS tab: 3 panels (Visual | Mapping List | Quick Settings)
    - READINGS tab: Live axis/buttons visualization
    """

    save_requested = Signal()
    profile_saved = Signal(str)

    def __init__(self, slot_id: int, slot, profile_manager, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.slot = slot
        self.profile_manager = profile_manager or ProfileManager()
        self._current_profile: Optional[ProfileConfig] = None
        self._raw_event_callback = None
        self._setup_ui()
        self._connect_signals()
        self._load_current_profile()
        self._connect_raw_events()

    # ------------------------------------------------------------------
    # UI SETUP
    # ------------------------------------------------------------------
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ==================== 1. CABEÇALHO FIXO (Topo) ====================
        header = QHBoxLayout()
        header.setSpacing(8)

        header.addWidget(QLabel("Profile Name:"))
        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.setPlaceholderText("Enter profile name...")
        self.profile_name_edit.setMinimumWidth(200)
        header.addWidget(self.profile_name_edit)

        self.save_btn = QPushButton("Save Profile")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._save_profile)
        header.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_profile)
        header.addWidget(self.cancel_btn)

        header.addStretch()
        main_layout.addLayout(header)

        # ==================== 2. QTabWidget (Coração da interface) ====================
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        main_layout.addWidget(self.main_tabs, 1)

        # ---- ABA CONTROLS ----
        self._create_controls_tab()

        # ---- ABA SHIFT MODIFIER ----
        shift_widget = QWidget()
        shift_layout = QVBoxLayout(shift_widget)
        shift_layout.setContentsMargins(20, 20, 20, 20)
        shift_label = QLabel("Shift Modifier — Advanced remapping with offsets\n\n"
                             "Map buttons with directional offsets for combo inputs.")
        shift_label.setWordWrap(True)
        shift_layout.addWidget(shift_label)
        shift_layout.addStretch()
        self.main_tabs.addTab(shift_widget, "Shift Modifier")

        # ---- ABA CONTROLLER READINGS ----
        self._create_readings_tab()

    # ------------------------------------------------------------------
    def _create_controls_tab(self):
        """Create the 3-panel CONTROLS tab."""
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.setSpacing(12)

        # ==================== PAINEL ESQUERDO: Visual ====================
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        # Controller image
        self.controller_image_label = QLabel()
        self.controller_image_label.setFixedSize(320, 380)
        self.controller_image_label.setAlignment(Qt.AlignCenter)
        self._load_controller_image()
        left_panel.addWidget(self.controller_image_label)

        # Gyro buttons below image
        gyro_group = QGroupBox("Gyro Controls")
        gyro_layout = QGridLayout(gyro_group)
        gyro_layout.setSpacing(4)

        gyro_labels = [
            ("Tilt Up", -1, 0), ("Tilt Down", 1, 0),
            ("Tilt Left", 0, -1), ("Tilt Right", 0, 1),
        ]
        self.gyro_btns = {}
        for i, (label, dx, dy) in enumerate(gyro_labels):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda checked, d=(dx, dy): self._test_gyro(d))
            self.gyro_btns[label] = btn
            row = abs(dy) if dy != 0 else 1
            col = abs(dx) if dx != 0 else 1
            gyro_layout.addWidget(btn, row, col)

        left_panel.addWidget(gyro_group)

        controls_layout.addLayout(left_panel, 1)

        # ==================== PAINEL CENTRAL: Mapeamento ====================
        center_panel = QVBoxLayout()
        center_panel.setSpacing(8)

        center_header = QHBoxLayout()
        center_header.addWidget(QLabel("Button Mappings"))
        center_header.addStretch()

        self.clear_mappings_btn = QPushButton("Clear All")
        self.clear_mappings_btn.clicked.connect(self._clear_mappings)
        center_header.addWidget(self.clear_mappings_btn)

        center_panel.addLayout(center_header)

        self.mapping_list = QListWidget()
        self.mapping_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.mapping_list.itemDoubleClicked.connect(self._on_mapping_double_click)
        self.mapping_list.setStyleSheet("""
            QListWidget {
                background: #1e1e2e;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #00d4aa;
                color: #1e1e2e;
            }
        """)
        center_panel.addWidget(self.mapping_list)

        # Quick map button
        self.quick_map_btn = QPushButton("⚡ Quick Map Remaining")
        self.quick_map_btn.setObjectName("primaryButton")
        self.quick_map_btn.clicked.connect(self._start_quick_map)
        center_panel.addWidget(self.quick_map_btn)

        controls_layout.addLayout(center_panel, 1)

        # ==================== PAINEL DIREITO: Configurações Rápidas ====================
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(10)

        # --- GroupBox: Rumble ---
        rumble_group = QGroupBox("Rumble")
        rumble_layout = QFormLayout(rumble_group)
        rumble_layout.setSpacing(8)

        self.rumble_enable = QCheckBox("Enable Rumble")
        self.rumble_enable.setChecked(True)
        rumble_layout.addRow(self.rumble_enable)

        self.rumble_intensity = QSpinBox()
        self.rumble_intensity.setRange(0, 100)
        self.rumble_intensity.setValue(100)
        self.rumble_intensity.setSuffix("%")
        rumble_layout.addRow("Intensity:", self.rumble_intensity)

        self.rumble_test_btn = QPushButton("Test Rumble")
        self.rumble_test_btn.clicked.connect(self._test_rumble)
        rumble_layout.addRow(self.rumble_test_btn)

        right_layout.addWidget(rumble_group)

        # --- GroupBox: Lightbar ---
        lightbar_group = QGroupBox("Lightbar")
        lightbar_layout = QFormLayout(lightbar_group)
        lightbar_layout.setSpacing(8)

        self.lightbar_preview = QLabel("●")
        self.lightbar_preview.setFixedSize(40, 30)
        self.lightbar_preview.setStyleSheet("background: #00d4aa; border-radius: 4px;")
        lightbar_layout.addRow("Color:", self.lightbar_preview)

        self.lightbar_pick_btn = QPushButton("Choose Color")
        self.lightbar_pick_btn.clicked.connect(self._pick_lightbar_color)
        lightbar_layout.addRow(self.lightbar_pick_btn)

        self.lightbar_brightness = QSpinBox()
        self.lightbar_brightness.setRange(0, 255)
        self.lightbar_brightness.setValue(255)
        lightbar_layout.addRow("Brightness:", self.lightbar_brightness)

        right_layout.addWidget(lightbar_group)

        # --- GroupBox: Touchpad ---
        touchpad_group = QGroupBox("Touchpad")
        touchpad_layout = QFormLayout(touchpad_group)
        touchpad_layout.setSpacing(8)

        self.touchpad_jitter = QDoubleSpinBox()
        self.touchpad_jitter.setRange(0.0, 1.0)
        self.touchpad_jitter.setSingleStep(0.05)
        self.touchpad_jitter.setValue(0.0)
        self.touchpad_jitter.setSuffix("")
        touchpad_layout.addRow("Jitter Compensation:", self.touchpad_jitter)

        self.touchpad_mode = QComboBox()
        self.touchpad_mode.addItems(["Disabled", "Mouse Mode", "Controls Mode"])
        touchpad_layout.addRow("Mode:", self.touchpad_mode)

        right_layout.addWidget(touchpad_group)

        # --- GroupBox: Axis Config (LS/RS) ---
        axis_group = QGroupBox("Stick Config")
        axis_layout = QFormLayout(axis_group)
        axis_layout.setSpacing(8)

        self.ls_deadzone = QDoubleSpinBox()
        self.ls_deadzone.setRange(0.0, 0.5)
        self.ls_deadzone.setSingleStep(0.01)
        self.ls_deadzone.setValue(0.15)
        self.ls_deadzone.setDecimals(2)
        axis_layout.addRow("LS Deadzone:", self.ls_deadzone)

        self.rs_deadzone = QDoubleSpinBox()
        self.rs_deadzone.setRange(0.0, 0.5)
        self.rs_deadzone.setSingleStep(0.01)
        self.rs_deadzone.setValue(0.15)
        self.rs_deadzone.setDecimals(2)
        axis_layout.addRow("RS Deadzone:", self.rs_deadzone)

        self.ls_sensitivity = QDoubleSpinBox()
        self.ls_sensitivity.setRange(0.1, 3.0)
        self.ls_sensitivity.setSingleStep(0.1)
        self.ls_sensitivity.setValue(1.0)
        axis_layout.addRow("LS Sensitivity:", self.ls_sensitivity)

        self.rs_sensitivity = QDoubleSpinBox()
        self.rs_sensitivity.setRange(0.1, 3.0)
        self.rs_sensitivity.setSingleStep(0.1)
        self.rs_sensitivity.setValue(1.0)
        axis_layout.addRow("RS Sensitivity:", self.rs_sensitivity)

        right_layout.addWidget(axis_group)

        # --- GroupBox: Trigger Config ---
        trigger_group = QGroupBox("Trigger Config")
        trigger_layout = QFormLayout(trigger_group)
        trigger_layout.setSpacing(8)

        self.lt_deadzone = QDoubleSpinBox()
        self.lt_deadzone.setRange(0.0, 0.5)
        self.lt_deadzone.setSingleStep(0.01)
        self.lt_deadzone.setValue(0.05)
        self.lt_deadzone.setDecimals(2)
        trigger_layout.addRow("L2 Deadzone:", self.lt_deadzone)

        self.rt_deadzone = QDoubleSpinBox()
        self.rt_deadzone.setRange(0.0, 0.5)
        self.rt_deadzone.setSingleStep(0.01)
        self.rt_deadzone.setValue(0.05)
        self.rt_deadzone.setDecimals(2)
        trigger_layout.addRow("R2 Deadzone:", self.rt_deadzone)

        right_layout.addWidget(trigger_group)

        right_layout.addStretch()
        right_scroll.setWidget(right_content)
        controls_layout.addWidget(right_scroll, 1)

        self.main_tabs.addTab(controls_widget, "Controls")

    # ------------------------------------------------------------------
    def _create_readings_tab(self):
        """Create the CONTROLLER READINGS tab with live visualization."""
        readings_widget = QWidget()
        readings_layout = QVBoxLayout(readings_widget)
        readings_layout.setContentsMargins(20, 20, 20, 20)
        readings_layout.setSpacing(12)

        readings_layout.addWidget(QLabel("<b>Controller Readings — Live Input Test</b>"))
        readings_layout.addWidget(QLabel("Press buttons and move sticks to verify input."))

        # --- Stick axes ---
        sticks_group = QGroupBox("Analog Sticks")
        sticks_layout = QFormLayout(sticks_group)
        sticks_layout.setSpacing(10)

        self.ls_x_bar = QProgressBar()
        self.ls_x_bar.setRange(-32768, 32767)
        self.ls_x_bar.setValue(0)
        self.ls_x_bar.setTextVisible(False)
        self.ls_x_bar.setFormat("")

        self.ls_y_bar = QProgressBar()
        self.ls_y_bar.setRange(-32768, 32767)
        self.ls_y_bar.setValue(0)
        self.ls_y_bar.setTextVisible(False)

        self.rs_x_bar = QProgressBar()
        self.rs_x_bar.setRange(-32768, 32767)
        self.rs_x_bar.setValue(0)
        self.rs_x_bar.setTextVisible(False)

        self.rs_y_bar = QProgressBar()
        self.rs_y_bar.setRange(-32768, 32767)
        self.rs_y_bar.setValue(0)
        self.rs_y_bar.setTextVisible(False)

        sticks_layout.addRow("Left Stick X:", self.ls_x_bar)
        sticks_layout.addRow("Left Stick Y:", self.ls_y_bar)
        sticks_layout.addRow("Right Stick X:", self.rs_x_bar)
        sticks_layout.addRow("Right Stick Y:", self.rs_y_bar)

        readings_layout.addWidget(sticks_group)

        # --- Triggers ---
        triggers_group = QGroupBox("Triggers (L2 / R2)")
        triggers_layout = QFormLayout(triggers_group)
        triggers_layout.setSpacing(10)

        self.l2_bar = QProgressBar()
        self.l2_bar.setRange(0, 255)
        self.l2_bar.setValue(0)

        self.r2_bar = QProgressBar()
        self.r2_bar.setRange(0, 255)
        self.r2_bar.setValue(0)

        triggers_layout.addRow("L2:", self.l2_bar)
        triggers_layout.addRow("R2:", self.r2_bar)

        readings_layout.addWidget(triggers_group)

        # --- Buttons status ---
        buttons_group = QGroupBox("Button States")
        buttons_layout = QGridLayout(buttons_group)
        buttons_layout.setSpacing(6)

        self.btn_states = {}
        all_btns = [
            (DS4Btn.SOUTH, "Cross"), (DS4Btn.EAST, "Circle"),
            (DS4Btn.NORTH, "Triangle"), (DS4Btn.WEST, "Square"),
            (DS4Btn.TL, "L1"), (DS4Btn.TR, "R1"),
            (DS4Btn.TL2, "L2"), (DS4Btn.TR2, "R2"),
            (DS4Btn.SELECT, "Share"), (DS4Btn.START, "Options"),
            (DS4Btn.THUMBL, "L3"), (DS4Btn.THUMBR, "R3"),
            (DS4Btn.PS, "PS"), (DS4Btn.DPAD_UP, "D-Up"),
            (DS4Btn.DPAD_DOWN, "D-Down"), (DS4Btn.DPAD_LEFT, "D-Left"),
            (DS4Btn.DPAD_RIGHT, "D-Right"),
        ]
        for i, (code, label) in enumerate(all_btns):
            row = i // 6
            col = i % 6
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #a0a0b0; font-size: 11px;")
            state_lbl = QLabel("○")
            state_lbl.setStyleSheet("font-size: 14px;")
            state_lbl.setAlignment(Qt.AlignCenter)
            self.btn_states[code] = state_lbl
            buttons_layout.addWidget(lbl, row, col * 2)
            buttons_layout.addWidget(state_lbl, row, col * 2 + 1)

        readings_layout.addWidget(buttons_group)

        # Connection label
        conn_lbl = QLabel("Connected: No controller")
        conn_lbl.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        readings_layout.addWidget(conn_lbl)
        self.connection_status = conn_lbl

        readings_layout.addStretch()

        self.main_tabs.addTab(readings_widget, "Controller Readings")

    # ------------------------------------------------------------------
    # IMAGE LOADING
    # ------------------------------------------------------------------
    def _load_controller_image(self):
        """Load the controller image for the visual panel."""
        image_paths = [
            Path(__file__).parent.parent.parent / "assets" / "joystick.png",
            Path(__file__).parent.parent.parent / "assets" / "controller.png",
            Path("/home/servidor/Git/Ds4linux/assets/joystick.png"),
        ]
        loaded = False
        for path in image_paths:
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    self.controller_image_label.setPixmap(
                        pixmap.scaled(320, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    loaded = True
                    logger.info(f"Loaded controller image: {path}")
                    break
        if not loaded:
            # Draw fallback
            pixmap = QPixmap(320, 380)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#555560"), 2))
            painter.setBrush(QBrush(QColor("#2a2a3e")))
            painter.drawRoundedRect(40, 30, 240, 300, 40, 40)
            painter.end()
            self.controller_image_label.setPixmap(pixmap)

    # ------------------------------------------------------------------
    # SIGNALS
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.lightbar_brightness.valueChanged.connect(self._on_lightbar_brightness)
        self.touchpad_jitter.valueChanged.connect(self._on_touchpad_jitter)
        self.touchpad_mode.currentIndexChanged.connect(self._on_touchpad_mode)
        self.rumble_intensity.valueChanged.connect(self._on_rumble_intensity)
        self.rumble_enable.toggled.connect(self._on_rumble_enable)

    def _connect_raw_events(self):
        """Connect to worker thread raw_event signal for live readings."""
        if hasattr(self.slot, '_worker') and self.slot._worker:
            self.slot._worker.raw_event.connect(self._on_raw_event)
            logger.info(f"Slot {self.slot_id}: Connected raw_event signal to readings")

    # ------------------------------------------------------------------
    # PROFILE LOADING / SAVING
    # ------------------------------------------------------------------
    def _load_current_profile(self):
        prof_name = self.profile_manager.get_current_profile_name() or "Default"
        self._current_profile = self.profile_manager.load_profile(prof_name)
        self.profile_name_edit.setText(prof_name)
        self._apply_profile_to_ui()

    def _apply_profile_to_ui(self):
        if not self._current_profile:
            return

        # Apply button mappings to list
        self._update_mapping_list()

        # Apply axis config
        ls, rs = self._current_profile.left_stick, self._current_profile.right_stick
        lt, rt = self._current_profile.left_trigger, self._current_profile.right_trigger
        self.ls_deadzone.setValue(ls.deadzone)
        self.rs_deadzone.setValue(rs.deadzone)
        self.ls_sensitivity.setValue(ls.sensitivity)
        self.rs_sensitivity.setValue(rs.sensitivity)
        self.lt_deadzone.setValue(lt.deadzone)
        self.rt_deadzone.setValue(rt.deadzone)

        # Apply lightbar
        color = QColor(*self._current_profile.led_color)
        self.lightbar_preview.setStyleSheet(
            f"background: {color.name()}; border-radius: 4px; border: 1px solid #3a3a5c;"
        )
        self.lightbar_brightness.setValue(self._current_profile.led_brightness)

        # Update rumble
        self.rumble_enable.setChecked(True)
        self.rumble_intensity.setValue(100)

        # Update touchpad
        self.touchpad_mode.setCurrentIndex(1)  # Mouse mode default
        self.touchpad_jitter.setValue(0.0)

    def _save_profile(self):
        name = self.profile_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Empty Name", "Please enter a profile name.")
            return

        # Build profile from UI values
        if not self._current_profile:
            self._current_profile = ProfileConfig(name=name)

        self._current_profile.name = name
        self._current_profile.device_type = VDT(
            self.slot._virtual_device.device_type.value if self.slot._virtual_device else "xbox"
        )

        # Collect mappings from list
        mappings = {}
        for i in range(self.mapping_list.count()):
            item = self.mapping_list.item(i)
            ds4_code = item.data(Qt.UserRole)
            if ds4_code is not None:
                # Extract virt code from text
                text = item.text()
                if "→" in text:
                    virt_name = text.split("→")[1].strip()
                    # Try to find virt code
                    for enum_cls in (XboxBtn, PS4Btn):
                        try:
                            mappings[ds4_code] = enum_cls[virt_name].value
                            break
                        except KeyError:
                            continue
        self._current_profile.button_maps = mappings

        # Axis config
        self._current_profile.left_stick = AxisConfig(
            deadzone=self.ls_deadzone.value(),
            sensitivity=self.ls_sensitivity.value(),
        )
        self._current_profile.right_stick = AxisConfig(
            deadzone=self.rs_deadzone.value(),
            sensitivity=self.rs_sensitivity.value(),
        )
        self._current_profile.left_trigger = TriggerConfig(
            deadzone=self.lt_deadzone.value(),
        )
        self._current_profile.right_trigger = TriggerConfig(
            deadzone=self.rt_deadzone.value(),
        )

        # LED
        self._current_profile.led_color = (
            self.lightbar_preview.styleSheet().split("#")[1][:6] if "#" in self.lightbar_preview.styleSheet()
            else (0, 212, 170)
        )
        self._current_profile.led_brightness = self.lightbar_brightness.value()

        # Save
        self.profile_manager.save_profile(name, self._current_profile)
        self.profile_saved.emit(name)
        self.save_requested.emit()
        logger.info(f"Profile saved: {name}")

    def _cancel_profile(self):
        self._load_current_profile()
        logger.info("Profile edit cancelled")

    # ------------------------------------------------------------------
    # MAPPING LIST
    # ------------------------------------------------------------------
    def _update_mapping_list(self):
        """Populate the mapping list from current profile."""
        self.mapping_list.clear()
        btn_names = {}
        for enum_cls in (DS4Btn, XboxBtn, PS4Btn):
            for member in enum_cls:
                btn_names[member.value] = member.name

        mappings = self._current_profile.button_maps if self._current_profile else {}
        for ds4_code, virt_code in sorted(mappings.items()):
            ds4_name = btn_names.get(ds4_code, f"0x{ds4_code:03X}")
            virt_name = btn_names.get(virt_code, f"0x{virt_code:03X}")
            item = QListWidgetItem(f"{ds4_name} → {virt_name}")
            item.setData(Qt.UserRole, ds4_code)
            self.mapping_list.addItem(item)

    def _on_mapping_double_click(self, item: QListWidgetItem):
        """Allow remapping by double-clicking."""
        ds4_code = item.data(Qt.UserRole)
        if ds4_code is None:
            return
        # Remove old
        self.mapping_list.takeItem(self.mapping_list.row(item))
        if self._current_profile and ds4_code in self._current_profile.button_maps:
            del self._current_profile.button_maps[ds4_code]
        logger.info(f"Removed mapping for {ds4_code}")

    def _clear_mappings(self):
        if self._current_profile:
            self._current_profile.button_maps.clear()
        self._update_mapping_list()
        logger.info("All mappings cleared")

    def _start_quick_map(self):
        """Start quick mapping for unmapped buttons."""
        if not self._current_profile:
            return
        all_codes = [btn_def[0] for btn_def in [
            (DS4Btn.SOUTH, "Cross"), (DS4Btn.EAST, "Circle"),
            (DS4Btn.NORTH, "Triangle"), (DS4Btn.WEST, "Square"),
            (DS4Btn.TL, "L1"), (DS4Btn.TR, "R1"),
            (DS4Btn.TL2, "L2"), (DS4Btn.TR2, "R2"),
            (DS4Btn.SELECT, "Share"), (DS4Btn.START, "Options"),
            (DS4Btn.THUMBL, "L3"), (DS4Btn.THUMBR, "R3"),
            (DS4Btn.PS, "PS"),
            (DS4Btn.DPAD_UP, "D-Up"), (DS4Btn.DPAD_DOWN, "D-Down"),
            (DS4Btn.DPAD_LEFT, "D-Left"), (DS4Btn.DPAD_RIGHT, "D-Right"),
        ]]
        unmapped = [c for c in all_codes if c not in (self._current_profile.button_maps or {})]
        if not unmapped:
            QMessageBox.information(self, "Complete", "All buttons already mapped!")
            return
        QMessageBox.information(self, "Quick Map",
            "Click on buttons in the controller visual to map them.\n"
            "Press each physical button when prompted.")

    # ------------------------------------------------------------------
    # LIVE READINGS
    # ------------------------------------------------------------------
    @staticmethod
    def update_readings(event_data: dict):
        """
        Static method to update readings from external sources.
        Called by WorkerThread via signal connection.
        
        event_data format:
        {
            'ls_x': int, 'ls_y': int,
            'rs_x': int, 'rs_y': int,
            'l2': int, 'r2': int,
            'buttons': {code: pressed}
        }
        """
        # This is called by the worker thread to update the readings tab
        pass

    def _on_raw_event(self, event_type: int, code: int, value: int):
        """Route raw events from worker thread to readings and mapping."""
        from evdev import ecodes as e

        # Update button states (always)
        if event_type == e.EV_KEY:
            ds4_codes = {
                e.BTN_SOUTH: DS4Btn.SOUTH, e.BTN_EAST: DS4Btn.EAST,
                e.BTN_NORTH: DS4Btn.NORTH, e.BTN_WEST: DS4Btn.WEST,
                e.BTN_TL: DS4Btn.TL, e.BTN_TR: DS4Btn.TR,
                e.BTN_THUMBL: DS4Btn.THUMBL, e.BTN_THUMBR: DS4Btn.THUMBR,
                e.BTN_START: DS4Btn.START, e.BTN_SELECT: DS4Btn.SELECT,
                e.BTN_MODE: DS4Btn.PS,
                e.BTN_DPAD_UP: DS4Btn.DPAD_UP, e.BTN_DPAD_DOWN: DS4Btn.DPAD_DOWN,
                e.BTN_DPAD_LEFT: DS4Btn.DPAD_LEFT, e.BTN_DPAD_RIGHT: DS4Btn.DPAD_RIGHT,
            }
            if code in ds4_codes:
                ds4_code = ds4_codes[code]
                if ds4_code in self.btn_states:
                    state_lbl = self.btn_states[ds4_code]
                    state_lbl.setText("●" if value == 1 else "○")
                    state_lbl.setStyleSheet(
                        "font-size: 14px; color: #00d4aa;" if value == 1 else "font-size: 14px;"
                    )

        # Update axis readings (only if readings tab is visible)
        if self.main_tabs.currentIndex() == 2:  # Controller Readings tab
            if event_type == e.EV_ABS:
                abs_map = {
                    e.ABS_X: (self.ls_x_bar, value),
                    e.ABS_Y: (self.ls_y_bar, value),
                    e.ABS_RX: (self.rs_x_bar, value),
                    e.ABS_RY: (self.rs_y_bar, value),
                    e.ABS_Z: (self.l2_bar, max(0, value)),
                    e.ABS_RZ: (self.r2_bar, max(0, value)),
                }
                for bar, val in abs_map.values():
                    bar.setValue(val)

    # ------------------------------------------------------------------
    # EVENT HANDLERS
    # ------------------------------------------------------------------
    def _pick_lightbar_color(self):
        color = ColorDialog.get_color_static(
            QColor(*self._current_profile.led_color) if self._current_profile else QColor(0, 212, 170),
            self
        )
        if color.isValid():
            self.lightbar_preview.setStyleSheet(
                f"background: {color.name()}; border-radius: 4px; border: 1px solid #3a3a5c;"
            )
            if self._current_profile:
                self._current_profile.led_color = (color.red(), color.green(), color.blue())

    def _on_lightbar_brightness(self, val: int):
        if self._current_profile:
            self._current_profile.led_brightness = val

    def _on_touchpad_jitter(self, val: float):
        if self._current_profile:
            pass  # Store for future use

    def _on_touchpad_mode(self, idx: int):
        if self._current_profile:
            pass  # Store for future use

    def _on_rumble_intensity(self, val: int):
        pass

    def _on_rumble_enable(self, checked: bool):
        pass

    def _test_rumble(self):
        if self.slot and self.slot._worker:
            # Trigger rumble via worker
            pass
        QMessageBox.information(self, "Test Rumble", "Rumble test triggered!")

    def _test_gyro(self, direction: tuple):
        QMessageBox.information(self, "Gyro Test", f"Gyro tilt: {direction}")

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        """Save geometry on close."""
        from PySide6.QtCore import QSettings
        settings = QSettings("DS4Linux", "DS4Linux")
        settings.setValue("profile_editor/geometry", self.saveGeometry())
        super().closeEvent(event)


class ProfileTabWidget(ProfileEditorWindow):
    """
    Alias for backward compatibility with existing code that imports ProfileTabWidget.
    """
    pass
