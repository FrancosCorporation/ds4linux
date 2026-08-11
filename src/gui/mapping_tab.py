from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QDialogButtonBox, QMessageBox, QProgressBar,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal, Slot, QRectF, QTimer, QPoint
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen, QBrush, QFont, QMouseEvent

from ..constants import DS4Btn, XboxBtn, PS4Btn
from ..engine.input_mapper import ProfileConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Button definitions: (DS4Btn code, display label, relative position, size)
# Coordinates are relative to the controller image (0-1 range)
# ---------------------------------------------------------------------------
BUTTON_DEFS: List[Tuple[int, str, float, float, float, float]] = [
    # Face buttons (right side) — arranged in diamond pattern
    (DS4Btn.NORTH, "△ Triangle",  0.72, 0.22, 0.06, 0.06),
    (DS4Btn.EAST,  "○ Circle",    0.78, 0.40, 0.06, 0.06),
    (DS4Btn.SOUTH, "× Cross",     0.72, 0.58, 0.06, 0.06),
    (DS4Btn.WEST,  "□ Square",    0.66, 0.40, 0.06, 0.06),
    # D-Pad (left side)
    (DS4Btn.DPAD_UP,    "D-Pad Up",    0.28, 0.22, 0.06, 0.06),
    (DS4Btn.DPAD_DOWN,  "D-Pad Down",  0.28, 0.40, 0.06, 0.06),
    (DS4Btn.DPAD_LEFT,  "D-Pad Left",  0.18, 0.30, 0.06, 0.06),
    (DS4Btn.DPAD_RIGHT, "D-Pad Right", 0.38, 0.30, 0.06, 0.06),
    # Shoulders
    (DS4Btn.TL, "L1", 0.22, 0.10, 0.12, 0.05),
    (DS4Btn.TR, "R1", 0.62, 0.10, 0.12, 0.05),
    # Triggers
    (DS4Btn.TL2, "L2", 0.18, 0.03, 0.14, 0.05),
    (DS4Btn.TR2, "R2", 0.64, 0.03, 0.14, 0.05),
    # Center buttons
    (DS4Btn.SELECT, "Share",  0.35, 0.18, 0.05, 0.04),
    (DS4Btn.START,  "Options", 0.52, 0.18, 0.05, 0.04),
    (DS4Btn.PS,     "PS",      0.44, 0.12, 0.04, 0.04),
    # Sticks
    (DS4Btn.THUMBL, "LS (Click)",  0.25, 0.58, 0.07, 0.07),
    (DS4Btn.THUMBR, "RS (Click)",  0.60, 0.58, 0.07, 0.07),
    # Touchpad
    (DS4Btn.TOUCHPAD, "Touchpad", 0.44, 0.35, 0.16, 0.10),
]


def _btn_name(ds4_code: int) -> str:
    """Return human-readable button name from DS4Btn code."""
    try:
        return DS4Btn(ds4_code).name
    except ValueError:
        return f"0x{ds4_code:03X}"


def _btn_symbol(ds4_code: int) -> str:
    """Return display symbol for a DS4 button."""
    symbols = {
        DS4Btn.NORTH: "△",
        DS4Btn.EAST: "○",
        DS4Btn.SOUTH: "×",
        DS4Btn.WEST: "□",
        DS4Btn.TL: "L1",
        DS4Btn.TR: "R1",
        DS4Btn.TL2: "L2",
        DS4Btn.TR2: "R2",
        DS4Btn.SELECT: "Share",
        DS4Btn.START: "Options",
        DS4Btn.PS: "PS",
        DS4Btn.THUMBL: "L3",
        DS4Btn.THUMBR: "R3",
        DS4Btn.DPAD_UP: "↑",
        DS4Btn.DPAD_DOWN: "↓",
        DS4Btn.DPAD_LEFT: "←",
        DS4Btn.DPAD_RIGHT: "→",
        DS4Btn.TOUCHPAD: "Touch",
    }
    return symbols.get(ds4_code, _btn_name(ds4_code))


class ControllerOverlayWidget(QWidget):
    """
    Displays the DS4 controller image with interactive button overlays.
    Each button is a transparent QPushButton positioned over the image.
    Hover shows edit icon; click opens ListenDialog.
    """

    button_clicked = Signal(int)  # DS4Btn code
    button_pressed = Signal(int)  # DS4Btn code (held)
    button_released = Signal(int)  # DS4Btn code (released)

    def __init__(self, image_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._mapped_buttons: Dict[int, int] = {}  # ds4_code -> xbox/ps4_code
        self._button_widgets: Dict[int, QPushButton] = {}
        self._hovered_button: Optional[int] = None
        self._edit_overlay: Optional[QLabel] = None

        # Try to load the controller image
        if image_path and image_path.exists():
            self._load_image(image_path)
        else:
            # Fallback: try common paths
            for candidate in [
                Path(__file__).parent.parent.parent / "assets" / "joystick.png",
                Path(__file__).parent.parent.parent / "assets" / "controller.png",
                Path("/home/servidor/Git/Ds4linux/assets/joystick.png"),
            ]:
                if candidate.exists():
                    self._load_image(candidate)
                    break

        self.setMinimumSize(300, 360)
        self._create_edit_overlay()
        self._create_button_widgets()
        self._setup_style()

    def _load_image(self, path: Path):
        self._pixmap = QPixmap(str(path))
        if not self._pixmap.isNull():
            logger.info(f"Loaded controller image from {path}")
        else:
            logger.warning(f"Failed to load controller image from {path}")

    def _create_edit_overlay(self):
        """Create a floating label that shows edit icon on hover."""
        self._edit_overlay = QLabel("✏️", self)
        self._edit_overlay.setStyleSheet(
            "background: rgba(0, 212, 170, 0.85); color: #1e1e2e; "
            "border-radius: 8px; font-size: 14px; font-weight: bold; "
            "padding: 4px 8px;"
        )
        self._edit_overlay.setVisible(False)
        self._edit_overlay.setPixmap(QPixmap(32, 32))

    def _create_button_widgets(self):
        """Create transparent QPushButton overlays for each button."""
        for ds4_code, label, rx, ry, rw, rh in BUTTON_DEFS:
            btn = QPushButton(self)
            btn.setProperty("ds4_code", ds4_code)
            btn.setProperty("label", label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 2px solid transparent;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    border: 2px solid #00d4aa;
                    background: rgba(0, 212, 170, 0.15);
                }
                QPushButton:pressed {
                    background: rgba(0, 212, 170, 0.4);
                }
            """)
            btn.setToolTip(f"{label}\nClique para mapear")
            btn.clicked.connect(lambda checked, code=ds4_code: self.button_clicked.emit(code))
            btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)

            self._button_widgets[ds4_code] = btn

        self._update_button_positions()

    def _update_button_positions(self):
        """Position button overlays based on current widget size and image."""
        if not self._pixmap:
            return

        label_size = self.size()
        pixmap_size = self._pixmap.size()

        # Scale to fit while maintaining aspect ratio
        scale_x = label_size.width() / pixmap_size.width()
        scale_y = label_size.height() / pixmap_size.height()
        scale = min(scale_x, scale_y)

        # Center the image
        img_w = pixmap_size.width() * scale
        img_h = pixmap_size.height() * scale
        img_x = (label_size.width() - img_w) // 2
        img_y = (label_size.height() - img_h) // 2

        # Update each button position
        for ds4_code, label, rx, ry, rw, rh in BUTTON_DEFS:
            btn = self._button_widgets.get(ds4_code)
            if not btn:
                continue

            # Map relative coordinates to image coordinates, then to widget coordinates
            x = img_x + rx * img_w
            y = img_y + ry * img_h
            w = rw * img_w
            h = rh * img_h

            btn.setGeometry(int(x), int(y), int(w), int(h))
            btn.setToolTip(f"{label} — Clique para mapear")

    def set_mappings(self, mappings: Dict[int, int]):
        """Update button visuals based on current mappings."""
        self._mapped_buttons = mappings
        for ds4_code, btn in self._button_widgets.items():
            if ds4_code in mappings:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(0, 212, 170, 0.25);
                        border: 2px solid #00d4aa;
                        border-radius: 6px;
                        color: #00d4aa;
                        font-weight: bold;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background: rgba(0, 212, 170, 0.4);
                        border: 2px solid #00e8bb;
                    }
                """)
                # Show mapped code on button
                virt_code = mappings[ds4_code]
                try:
                    virt_name = XboxBtn(virt_code).name
                except ValueError:
                    try:
                        virt_name = PS4Btn(virt_code).name
                    except ValueError:
                        virt_name = f"0x{virt_code:03X}"
                btn.setText(f"{_btn_symbol(ds4_code)}→{virt_name[:3]}")
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: 2px solid transparent;
                        border-radius: 6px;
                    }
                    QPushButton:hover {
                        border: 2px solid #00d4aa;
                        background: rgba(0, 212, 170, 0.15);
                    }
                """)
                btn.setText(_btn_symbol(ds4_code))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._pixmap and not self._pixmap.isNull():
            # Draw scaled controller image
            label_size = self.size()
            pixmap_size = self._pixmap.size()

            scale_x = label_size.width() / pixmap_size.width()
            scale_y = label_size.height() / pixmap_size.height()
            scale = min(scale_x, scale_y)

            img_w = pixmap_size.width() * scale
            img_h = pixmap_size.height() * scale
            img_x = (label_size.width() - img_w) // 2
            img_y = (label_size.height() - img_h) // 2

            painter.drawImage(
                QRectF(img_x, img_y, img_w, img_h),
                self._pixmap.toImage()
            )
        else:
            # Fallback: draw abstract controller outline
            self._draw_fallback_controller(painter)

        painter.end()

    def _draw_fallback_controller(self, painter: QPainter):
        """Draw a simple DS4 outline when no image is available."""
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        painter.setPen(QPen(QColor("#555560"), 2))
        painter.setBrush(QBrush(QColor("#2a2a3e")))
        painter.drawRoundedRect(20, 15, w - 40, h - 60, 35, 35)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_positions()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._edit_overlay.setVisible(True)
        self._edit_overlay.move(self.width() - 50, 10)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._edit_overlay.setVisible(False)


class ListenDialog(QDialog):
    """
    Modal dialog that waits for the next raw input event from the device.
    Shows "Aguardando entrada de botão..." while listening.
    """

    result = Signal(int, int)  # (ds4_code, value)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aguardando Entrada")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMinimumSize(280, 120)
        self._setup_ui()
        self._listening = False
        self._captured_code: Optional[int] = None
        self._captured_value: int = 0

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("🎮 Aguardando entrada...")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00d4aa;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Instruction
        instr = QLabel("Pressione o botão no controle físico")
        instr.setStyleSheet("color: #a0a0b0; font-size: 12px;")
        instr.setAlignment(Qt.AlignCenter)
        layout.addWidget(instr)

        # Pulse animation label
        self._pulse_label = QLabel("⏳")
        self._pulse_label.setStyleSheet("font-size: 24px;")
        self._pulse_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._pulse_label)

        # Timer for timeout
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)
        self._timeout_timer.start(30000)  # 30 second timeout

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # Pulse animation
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._on_pulse)
        self._pulse_timer.start(500)
        self._pulse_state = 0

    def _on_pulse(self):
        self._pulse_state = 1 - self._pulse_state
        self._pulse_label.setText("⏳" if self._pulse_state else "👆")

    def _on_timeout(self):
        QMessageBox.warning(self, "Timeout", "Nenhuma entrada detectada em 30 segundos.")
        self.reject()

    def start_listening(self, raw_event_callback):
        """
        Start listening for raw events.
        raw_event_callback: function(type, code, value) -> None
        """
        self._listening = True
        self._captured_code = None
        self._timeout_timer.start(30000)
        self.raw_event_callback = raw_event_callback
        # Connect the callback
        self._connect_callback()

    def _connect_callback(self):
        """Connect to the worker thread's raw_event signal."""
        from ..engine.worker_thread import WorkerThread
        # We need to find the running worker thread for this slot
        # The callback is set by the parent MappingTabWidget
        pass

    def capture_event(self, event_type: int, code: int, value: int):
        """Called by parent when a raw event is received."""
        if not self._listening:
            return
        self._timeout_timer.stop()
        self._pulse_timer.stop()

        # Filter: only accept KEY events (buttons), not ABS (sticks)
        from evdev import ecodes as e
        if event_type != e.EV_KEY:
            return

        self._captured_code = code
        self._captured_value = value
        self.result.emit(code, value)
        self.accept()

    def reject(self):
        self._listening = False
        self._timeout_timer.stop()
        self._pulse_timer.stop()
        super().reject()

    def closeEvent(self, event):
        self._listening = False
        self._timeout_timer.stop()
        self._pulse_timer.stop()
        super().closeEvent(event)


class MappingWizardDialog(QDialog):
    """
    Wizard that guides the user through mapping all buttons one by one.
    Highlights each button on the overlay, waits for physical press,
    then advances to the next.
    """

    finished = Signal(dict)  # {ds4_code: virt_code}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mapeamento Rápido")
        self.setModal(True)
        self.setMinimumSize(400, 300)
        self._buttons_to_map: List[int] = []
        self._current_index = 0
        self._captures: Dict[int, int] = {}
        self._progress = 0
        self._total = 0
        self._listen_dialog: Optional[ListenDialog] = None
        self._current_ds4_code: Optional[int] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("🎯 Mapeamento Rápido")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d4aa;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Progress
        self._progress_label = QLabel("Passo 0 de 0")
        self._progress_label.setStyleSheet("color: #a0a0b0;")
        self._progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        layout.addWidget(self._progress_bar)

        # Instruction
        self._instr_label = QLabel("Pressione o botão destacado no controle")
        self._instr_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self._instr_label.setAlignment(Qt.AlignCenter)
        self._instr_label.setWordWrap(True)
        layout.addWidget(self._instr_label)

        # Current button display
        self._current_btn_label = QLabel("")
        self._current_btn_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #00d4aa; "
            "background: #2a2a3e; border-radius: 8px; padding: 10px;"
        )
        self._current_btn_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._current_btn_label)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btn_box.button(QDialogButtonBox.Ok).setText("Concluir")
        btn_box.button(QDialogButtonBox.Cancel).setText("Cancelar")
        btn_box.accepted.connect(self._on_finish)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def start(self, all_ds4_codes: List[int], raw_event_callback):
        """
        Start the wizard with a list of DS4 button codes to map.
        raw_event_callback: function(type, code, value) -> None
        """
        self._buttons_to_map = all_ds4_codes
        self._current_index = 0
        self._captures.clear()
        self._total = len(all_ds4_codes)
        self._progress = 0
        self._raw_event_callback = raw_event_callback
        self._progress_bar.setMaximum(self._total)
        self._progress_bar.setValue(0)
        self._update_instruction()
        self.show()

    def _update_instruction(self):
        if self._current_index >= self._total:
            self._instr_label.setText("✅ Mapeamento completo!")
            self._current_btn_label.setText("Concluído!")
            return

        ds4_code = self._buttons_to_map[self._current_index]
        self._current_ds4_code = ds4_code
        self._current_btn_label.setText(
            f"{_btn_symbol(ds4_code)} {_btn_name(ds4_code)}"
        )
        self._progress_label.setText(
            f"Passo {self._current_index + 1} de {self._total}"
        )
        self._instr_label.setText("Pressione o botão destacado no controle")

    def capture_event(self, event_type: int, code: int, value: int):
        """Called by parent when a raw event is received during wizard."""
        from evdev import ecodes as e
        if event_type != e.EV_KEY:
            return
        if value != 1:  # Only on press, not release
            return

        # Check if this matches the current button
        if code == self._current_ds4_code:
            self._captures[self._current_ds4_code] = code
            self._current_index += 1
            self._progress = self._current_index
            self._progress_bar.setValue(self._progress)

            if self._current_index >= self._total:
                self._instr_label.setText("✅ Mapeamento completo!")
                self._current_btn_label.setText("Concluído!")
                QTimer.singleShot(1000, self._on_finish)
            else:
                self._update_instruction()
        else:
            # Wrong button — show feedback
            self._instr_label.setText(
                f"❌ Esperando {_btn_name(self._current_ds4_code)}, "
                f"pressionou {_btn_name(code)}"
            )
            self._instr_label.setStyleSheet("color: #ff6b6b; font-size: 13px;")
            QTimer.singleShot(1500, self._reset_instr_style)

    def _reset_instr_style(self):
        self._instr_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")

    def _on_finish(self):
        self.finished.emit(self._captures)
        self.accept()

    def reject(self):
        self.finished.emit(self._captures)
        super().reject()


class MappingTabWidget(QWidget):
    """
    Main mapping tab widget combining the controller overlay,
    mapping list, and quick-map wizard.
    """

    mappings_changed = Signal(dict)  # {ds4_code: virt_code}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mappings: Dict[int, int] = {}
        self._raw_event_callback = None
        self._listen_dialog: Optional[ListenDialog] = None
        self._wizard_dialog: Optional[MappingWizardDialog] = None
        self._setup_ui()
        self._create_dialogs()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Left: Controller overlay
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)

        self.overlay = ControllerOverlayWidget()
        self.overlay.button_clicked.connect(self._on_button_clicked)
        left_layout.addWidget(self.overlay)

        # Quick map button
        self.wizard_btn = QPushButton("⚡ Mapeamento Rápido")
        self.wizard_btn.setObjectName("primaryButton")
        self.wizard_btn.clicked.connect(self._start_wizard)
        left_layout.addWidget(self.wizard_btn)

        layout.addLayout(left_layout, 1)

        # Right: Mapping list
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(QLabel("Mapeamentos"))
        header.addStretch()

        clear_btn = QPushButton("Limpar")
        clear_btn.clicked.connect(self._clear_mappings)
        header.addWidget(clear_btn)
        right_layout.addLayout(header)

        self.mapping_list = QListWidget()
        self.mapping_list.itemDoubleClicked.connect(self._on_mapping_double_click)
        right_layout.addWidget(self.mapping_list)

        right_layout.addStretch()
        layout.addLayout(right_layout, 1)

    def _create_dialogs(self):
        self._listen_dialog = ListenDialog(self)
        self._listen_dialog.result.connect(self._on_listen_result)

        self._wizard_dialog = MappingWizardDialog(self)
        self._wizard_dialog.finished.connect(self._on_wizard_finished)

    def set_raw_event_callback(self, callback):
        """Set the callback for raw events from WorkerThread."""
        self._raw_event_callback = callback
        # Wire up dialogs to receive events
        if self._listen_dialog:
            self._listen_dialog.capture_event = lambda et, c, v: self._on_raw_event(et, c, v)
        if self._wizard_dialog:
            self._wizard_dialog.capture_event = lambda et, c, v: self._on_raw_event(et, c, v)

    def _on_raw_event(self, event_type: int, code: int, value: int):
        """Route raw events to active dialog."""
        if self._listen_dialog and self._listen_dialog.isVisible():
            self._listen_dialog.capture_event(event_type, code, value)
        if self._wizard_dialog and self._wizard_dialog.isVisible():
            self._wizard_dialog.capture_event(event_type, code, value)

    def _on_button_clicked(self, ds4_code: int):
        """Handle click on an overlay button — open listen dialog."""
        self._listen_dialog.open()
        # The ListenDialog will capture the next raw event
        # We need to signal that we're listening for this specific button
        self._listening_for_code = ds4_code

    def _on_listen_result(self, code: int, value: int):
        """Handle result from listen dialog."""
        ds4_code = getattr(self, '_listening_for_code', code)
        if ds4_code == code and value == 1:
            self._add_mapping(ds4_code, code)

    def _add_mapping(self, ds4_code: int, virt_code: int):
        """Add a button mapping."""
        self._current_mappings[ds4_code] = virt_code
        self._update_list()
        self._update_overlay()
        self.mappings_changed.emit(self._current_mappings)

    def _clear_mappings(self):
        """Clear all mappings."""
        self._current_mappings.clear()
        self._update_list()
        self._update_overlay()
        self.mappings_changed.emit({})

    def _on_mapping_double_click(self, item: QListWidgetItem):
        """Allow remapping by double-clicking a list item."""
        ds4_code = item.data(Qt.UserRole)
        if ds4_code is None:
            return
        # Remove old mapping
        self._current_mappings.pop(ds4_code, None)
        self._update_list()
        self._update_overlay()
        # Open listen dialog for this button
        self._listening_for_code = ds4_code
        self._listen_dialog.open()

    def _update_list(self):
        """Update the mapping list widget."""
        self.mapping_list.clear()
        btn_names = {}
        for enum_cls in (DS4Btn, XboxBtn, PS4Btn):
            for member in enum_cls:
                btn_names[member.value] = member.name

        for ds4_code, virt_code in sorted(self._current_mappings.items()):
            ds4_name = btn_names.get(ds4_code, f"0x{ds4_code:03X}")
            virt_name = btn_names.get(virt_code, f"0x{virt_code:03X}")
            item = QListWidgetItem(f"{ds4_name} → {virt_name}")
            item.setData(Qt.UserRole, ds4_code)
            self.mapping_list.addItem(item)

    def _update_overlay(self):
        """Update the controller overlay with current mappings."""
        self.overlay.set_mappings(self._current_mappings)

    def _start_wizard(self):
        """Start the quick mapping wizard."""
        # Collect all DS4 button codes that aren't yet mapped
        all_codes = [btn_def[0] for btn_def in BUTTON_DEFS]
        unmapped = [c for c in all_codes if c not in self._current_mappings]

        if not unmapped:
            QMessageBox.information(self, "Completo", "Todos os botões já estão mapeados!")
            return

        self._wizard_dialog.start(unmapped, self._on_raw_event)

    def get_mappings(self) -> Dict[int, int]:
        return self._current_mappings.copy()

    def set_mappings(self, mappings: Dict[int, int]):
        """Load mappings from a profile."""
        self._current_mappings = dict(mappings)
        self._update_list()
        self._update_overlay()
