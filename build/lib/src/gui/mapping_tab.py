from __future__ import annotations

import logging

from evdev import ecodes as e
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    DS4_TO_PS4_BTN_MAP,
    DS4_TO_XBOX_BTN_MAP,
    DS4Btn,
)
from ..engine.virtual_device import VirtualDeviceType
from ..resource_paths import resource_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Friendly (Portuguese) names for evdev codes
# ---------------------------------------------------------------------------
FRIENDLY_NAMES: dict[int, str] = {
    e.BTN_SOUTH: "✕ Cross",
    e.BTN_EAST: "○ Circle",
    e.BTN_NORTH: "△ Triangle",
    e.BTN_WEST: "□ Square",
    e.BTN_TL: "L1",
    e.BTN_TR: "R1",
    e.BTN_TL2: "L2",
    e.BTN_TR2: "R2",
    e.BTN_SELECT: "Share",
    e.BTN_START: "Options",
    e.BTN_MODE: "PS",
    e.BTN_THUMBL: "L3",
    e.BTN_THUMBR: "R3",
    e.BTN_DPAD_UP: "Seta ↑",
    e.BTN_DPAD_DOWN: "Seta ↓",
    e.BTN_DPAD_LEFT: "Seta ←",
    e.BTN_DPAD_RIGHT: "Seta →",
    e.BTN_TOUCH: "Touchpad (toque)",
    e.ABS_HAT0X: "Eixo D-Pad X",
    e.ABS_HAT0Y: "Eixo D-Pad Y",
}

XBOX_TARGET_NAMES: dict[int, str] = {
    e.BTN_A: "A", e.BTN_B: "B", e.BTN_X: "X", e.BTN_Y: "Y",
    e.BTN_TL: "LB", e.BTN_TR: "RB", e.BTN_TL2: "LT", e.BTN_TR2: "RT",
    e.BTN_SELECT: "Back", e.BTN_START: "Start", e.BTN_MODE: "Guide",
    e.BTN_THUMBL: "L3", e.BTN_THUMBR: "R3", e.BTN_TOUCH: "Touchpad",
    e.BTN_DPAD_UP: "D-Up", e.BTN_DPAD_DOWN: "D-Down",
    e.BTN_DPAD_LEFT: "D-Left", e.BTN_DPAD_RIGHT: "D-Right",
}

PS4_TARGET_NAMES: dict[int, str] = {
    e.BTN_SOUTH: "Cross", e.BTN_EAST: "Circle", e.BTN_NORTH: "Triangle",
    e.BTN_WEST: "Square", e.BTN_TL: "L1", e.BTN_TR: "R1",
    e.BTN_TL2: "L2", e.BTN_TR2: "R2", e.BTN_SELECT: "Share",
    e.BTN_START: "Options", e.BTN_MODE: "PS", e.BTN_THUMBL: "L3",
    e.BTN_THUMBR: "R3", e.BTN_TOUCH: "Touchpad",
    e.BTN_DPAD_UP: "D-Up", e.BTN_DPAD_DOWN: "D-Down",
    e.BTN_DPAD_LEFT: "D-Left", e.BTN_DPAD_RIGHT: "D-Right",
}


def physical_name(code: int) -> str:
    """Name of a physical DS4 input (Cross, Circle, Seta ↑...)."""
    return FRIENDLY_NAMES.get(code) or e.KEY.get(code) or e.BTN.get(code) \
        or e.ABS.get(code) or f"0x{code:03X}"


def target_name(code: int, device_type: VirtualDeviceType = VirtualDeviceType.XBOX) -> str:
    """Name of a virtual output on the emulated device (A, B, D-Up...)."""
    names = XBOX_TARGET_NAMES if device_type == VirtualDeviceType.XBOX else PS4_TARGET_NAMES
    return names.get(code) or physical_name(code)


# ---------------------------------------------------------------------------
# Overlay geometry (normalized to the controller image)
# code, symbol, x, y, w, h, kind
#   kind: "round" | "pill" | "pad"
# ---------------------------------------------------------------------------
OVERLAY_BUTTON_DEFS: list[tuple[int, str, float, float, float, float, str]] = [
    (DS4Btn.DPAD_UP,    "↑", 0.172, 0.350, 0.050, 0.050, "round"),
    (DS4Btn.DPAD_DOWN,  "↓", 0.172, 0.455, 0.050, 0.050, "round"),
    (DS4Btn.DPAD_LEFT,  "←", 0.120, 0.407, 0.050, 0.050, "round"),
    (DS4Btn.DPAD_RIGHT, "→", 0.220, 0.407, 0.050, 0.050, "round"),
    (DS4Btn.NORTH, "△", 0.770, 0.337, 0.060, 0.060, "round"),
    (DS4Btn.EAST,  "○", 0.835, 0.402, 0.060, 0.060, "round"),
    (DS4Btn.SOUTH, "✕", 0.770, 0.462, 0.060, 0.060, "round"),
    (DS4Btn.WEST,  "□", 0.702, 0.402, 0.060, 0.060, "round"),
    (DS4Btn.THUMBL, "L3", 0.270, 0.480, 0.150, 0.150, "round"),
    (DS4Btn.THUMBR, "R3", 0.580, 0.480, 0.150, 0.150, "round"),
    (DS4Btn.TOUCHPAD, "Touch", 0.345, 0.278, 0.310, 0.176, "pad"),
    (DS4Btn.SELECT, "Share", 0.291, 0.310, 0.030, 0.060, "pill"),
    (DS4Btn.START,  "Options", 0.680, 0.310, 0.030, 0.060, "pill"),
    (DS4Btn.PS,     "PS", 0.477, 0.466, 0.046, 0.040, "round"),
    (DS4Btn.TL,  "L1", 0.155, 0.260, 0.130, 0.050, "pill"),
    (DS4Btn.TR,  "R1", 0.715, 0.260, 0.130, 0.050, "pill"),
    (DS4Btn.TL2, "L2", 0.155, 0.205, 0.130, 0.050, "pill"),
    (DS4Btn.TR2, "R2", 0.715, 0.205, 0.130, 0.050, "pill"),
]

HAT_CODES = (e.ABS_HAT0X, e.ABS_HAT0Y)
STICK_AXIS_LAYOUT = {
    "left": (e.ABS_X, e.ABS_Y, 0.345, 0.555),
    "right": (e.ABS_RX, e.ABS_RY, 0.655, 0.555),
}
STICK_AXIS_CODES = {
    axis_code
    for x_code, y_code, *_center in STICK_AXIS_LAYOUT.values()
    for axis_code in (x_code, y_code)
}
STICK_BUTTON_SIDES = {
    int(DS4Btn.THUMBL): "left",
    int(DS4Btn.THUMBR): "right",
}
STICK_INDICATOR_RADIUS = 0.038


class ControllerOverlayWidget(QWidget):
    """Interactive DS4 illustration with clickable buttons.

    Buttons glow when mapped, light up on live input and show a tooltip
    with the current mapping.  Clicking a button selects it so the
    mapping list can follow along.
    """

    button_clicked = Signal(int)   # DS4Btn / evdev code
    button_selected = Signal(int)  # same, for list sync

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._mappings: dict[int, int] = {}
        self._device_type = VirtualDeviceType.XBOX
        self._hovered: int | None = None
        self._selected: int | None = None
        self._pressed: dict[int, bool] = {}
        self._dpad_x = 0
        self._dpad_y = 0
        self._axis_values = {code: 127.5 for code in STICK_AXIS_CODES}

        for candidate in (
            resource_path("assets", "ds4_controller.png"),
            resource_path("assets", "joystick.png"),
        ):
            if candidate.exists():
                pm = QPixmap(str(candidate))
                if not pm.isNull():
                    self._pixmap = pm
                    logger.info("Overlay: loaded %s", candidate)
                    break

        self.setMinimumSize(320, 300)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    # Fit the whole perspective artwork, including the shoulder buttons,
    # inside the preview instead of zooming into the transparent margins.
    VIEW = QRectF(0.0, 0.05, 1.0, 0.90)
    MARGIN = 8

    def _image_rect(self) -> QRectF:
        """Rect where the *full* pixmap is drawn (may overflow the widget)."""
        if not self._pixmap or self._pixmap.isNull():
            return QRectF(0, 0, self.width(), self.height())
        pw, ph = self._pixmap.width(), self._pixmap.height()
        scale = min(
            (self.width() - 2 * self.MARGIN) / (self.VIEW.width() * pw),
            (self.height() - 2 * self.MARGIN) / (self.VIEW.height() * ph),
        )
        dw, dh = pw * scale, ph * scale
        return QRectF(
            self.MARGIN - self.VIEW.x() * dw,
            self.MARGIN - self.VIEW.y() * dh,
            dw, dh,
        )

    def _button_rect(self, rx, ry, rw, rh) -> QRectF:
        img = self._image_rect()
        return QRectF(
            img.x() + rx * img.width(),
            img.y() + ry * img.height(),
            rw * img.width(),
            rh * img.height(),
        )

    def _button_at(self, pos: QPointF) -> int | None:
        for code, _sym, rx, ry, rw, rh, _kind in OVERLAY_BUTTON_DEFS:
            if self._button_rect(rx, ry, rw, rh).contains(pos):
                return code
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_mappings(self, mappings: dict[int, int]):
        self._mappings = dict(mappings or {})
        self.update()

    def set_device_type(self, device_type: VirtualDeviceType):
        self._device_type = device_type
        self.update()

    def set_selected(self, code: int | None):
        self._selected = code
        self.update()

    def set_button_pressed(self, code: int, pressed: bool):
        if self._pressed.get(code) == pressed:
            return
        self._pressed[code] = pressed
        self.update()

    def handle_raw_event(self, event_type: int, code: int, value: int):
        """Map raw evdev events to overlay button states."""
        if event_type == e.EV_KEY:
            if code in self.pressed_codes():
                self.set_button_pressed(code, value == 1)
        elif event_type == e.EV_ABS:
            if code in HAT_CODES:
                if code == e.ABS_HAT0X:
                    self._dpad_x = value
                else:
                    self._dpad_y = value
                self._sync_dpad()
            elif code in STICK_AXIS_CODES:
                self._axis_values[code] = value
                self.update()

    @staticmethod
    def _axis_unit(value: float) -> float:
        """Normalize DS4 evdev stick values (0..255) around neutral."""
        return max(-1.0, min(1.0, (float(value) - 127.5) / 127.5))

    def stick_marker_position(self, side: str) -> QPointF:
        """Return the live stick marker position in widget coordinates."""
        x_code, y_code, center_x, center_y = STICK_AXIS_LAYOUT[side]
        x = center_x + self._axis_unit(self._axis_values[x_code]) * STICK_INDICATOR_RADIUS
        y = center_y + self._axis_unit(self._axis_values[y_code]) * STICK_INDICATOR_RADIUS
        img = self._image_rect()
        return QPointF(img.x() + x * img.width(), img.y() + y * img.height())

    @staticmethod
    def pressed_codes() -> set:
        return {code for code, *_rest in OVERLAY_BUTTON_DEFS}

    def _sync_dpad(self):
        self.set_button_pressed(DS4Btn.DPAD_LEFT, self._dpad_x < 0)
        self.set_button_pressed(DS4Btn.DPAD_RIGHT, self._dpad_x > 0)
        self.set_button_pressed(DS4Btn.DPAD_UP, self._dpad_y < 0)
        self.set_button_pressed(DS4Btn.DPAD_DOWN, self._dpad_y > 0)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        img = self._image_rect()
        if self._pixmap and not self._pixmap.isNull():
            p.drawPixmap(img, self._pixmap, QRectF(0, 0, self._pixmap.width(), self._pixmap.height()))
        else:
            p.setPen(QPen(QColor("#3a3a5c"), 2))
            p.setBrush(QBrush(QColor("#2a2a3e")))
            p.drawRoundedRect(QRectF(20, 30, self.width() - 40, self.height() - 80), 30, 30)

        accent = QColor("#00d4aa")
        for code, symbol, rx, ry, rw, rh, kind in OVERLAY_BUTTON_DEFS:
            rect = self._button_rect(rx, ry, rw, rh)
            mapped = code in self._mappings
            pressed = self._pressed.get(code, False)
            hovered = self._hovered == code
            selected = self._selected == code

            if pressed:
                outline = QColor("#ffffff")
                fill = QColor(accent)
                fill.setAlpha(220)
                text = QColor("#101018")
            elif mapped:
                outline = QColor(accent)
                fill = QColor(accent)
                fill.setAlpha(60)
                text = QColor("#e8fff9")
            else:
                outline = QColor(255, 255, 255, 55)
                fill = QColor(255, 255, 255, 12)
                text = QColor("#9aa0b4")

            pen = QPen(outline)
            pen.setWidth(3 if (pressed or selected) else 2)
            if hovered and not pressed:
                pen.setColor(QColor("#ffffff"))
                pen.setWidth(3)
            p.setPen(pen)
            p.setBrush(QBrush(fill))

            if kind == "round":
                p.drawEllipse(rect)
            else:
                p.drawRoundedRect(rect, min(rect.width(), rect.height()) * 0.28,
                                  min(rect.width(), rect.height()) * 0.28)

            font = QFont(self.font())
            font.setBold(mapped or pressed)
            font.setPointSizeF(max(7.0, min(12.0, rect.height() * (0.30 if code in STICK_BUTTON_SIDES else 0.42))))
            p.setFont(font)
            p.setPen(QPen(text))
            if code in STICK_BUTTON_SIDES:
                label_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.60,
                                    rect.width(), rect.height() * 0.34)
                p.drawText(label_rect, Qt.AlignCenter, symbol)
            else:
                p.drawText(rect, Qt.AlignCenter, symbol)

        # The analog-button rings remain selectable; this separate dot shows
        # the live X/Y position without covering the center of either stick.
        for side, (_x_code, _y_code, center_x, center_y) in STICK_AXIS_LAYOUT.items():
            img_center = QPointF(
                img.x() + center_x * img.width(),
                img.y() + center_y * img.height(),
            )
            track_radius = img.width() * STICK_INDICATOR_RADIUS
            track = QRectF(
                img_center.x() - track_radius,
                img_center.y() - track_radius,
                track_radius * 2,
                track_radius * 2,
            )
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 212, 170, 115), 1.5))
            p.drawEllipse(track)
            marker = self.stick_marker_position(side)
            marker_radius = max(3.0, img.width() * 0.009)
            p.setPen(QPen(QColor("#101018"), 1.3))
            p.setBrush(QBrush(accent))
            p.drawEllipse(QRectF(
                marker.x() - marker_radius,
                marker.y() - marker_radius,
                marker_radius * 2,
                marker_radius * 2,
            ))

        # Hover info bar (physical -> target)
        if self._hovered is not None:
            target = self._mappings.get(self._hovered)
            physical = physical_name(self._hovered)
            if target is not None:
                info = f"{physical}  →  {target_name(target, self._device_type)}"
            else:
                info = f"{physical}  →  (sem mapeamento)"
            font = QFont(self.font())
            font.setPointSizeF(10.5)
            p.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(info) + 24
            th = fm.height() + 12
            bar = QRectF((self.width() - tw) / 2, self.height() - th - 6, tw, th)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(16, 16, 28, 220))
            p.drawRoundedRect(bar, 8, 8)
            p.setPen(QPen(accent))
            p.drawText(bar, Qt.AlignCenter, info)

        p.end()

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, event):
        code = self._button_at(event.position())
        if code != self._hovered:
            self._hovered = code
            self.update()
        if code is not None:
            target = self._mappings.get(code)
            tip = physical_name(code)
            if target is not None:
                tip += f" → {target_name(target, self._device_type)}"
            self.setToolTip(tip)
        else:
            self.setToolTip("")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            code = self._button_at(event.position())
            if code is not None:
                self._selected = code
                self.button_selected.emit(code)
                self.button_clicked.emit(code)
                self.update()
                return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Listen dialog: waits for the next physical input
# ---------------------------------------------------------------------------
class ListenDialog(QDialog):
    captured = Signal(int, int)  # evdev code, value

    def __init__(self, parent=None, timeout_ms: int = 15000):
        super().__init__(parent)
        self.setWindowTitle("Ouvindo entrada...")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("🎮 Pressione uma tecla do controle")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #00d4aa;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Aguardando botão ou seta do controle físico...")
        hint.setStyleSheet("color: #a0a0b0;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        self._status = QLabel("⏳")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("font-size: 28px;")
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)
        self._timeout.start(timeout_ms)

        self._blink = QTimer(self)
        self._blink.timeout.connect(self._toggle)
        self._blink.start(500)
        self._state = False

    def _toggle(self):
        self._state = not self._state
        self._status.setText("👆" if self._state else "⏳")

    def _on_timeout(self):
        QMessageBox.warning(self, "Sem resposta", "Nenhuma entrada detectada.")
        self.reject()

    def capture_event(self, event_type: int, code: int, value: int):
        accept = False
        if event_type == e.EV_KEY and value == 1:
            accept = True
        elif event_type == e.EV_ABS and code in HAT_CODES and value != 0:
            accept = True
        if not accept:
            return
        self._timeout.stop()
        self._blink.stop()
        self.captured.emit(code, value)
        self.accept()

    def reject(self):
        self._timeout.stop()
        self._blink.stop()
        super().reject()


# ---------------------------------------------------------------------------
# Target picker: choose the virtual button for a physical input
# ---------------------------------------------------------------------------
class TargetPickerDialog(QDialog):
    def __init__(self, physical_code: int, current: int | None,
                 device_type: VirtualDeviceType, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escolher destino")
        self.setMinimumWidth(320)
        self._device_type = device_type

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Entrada física:", QLabel(physical_name(physical_code)))

        self._combo = QComboBox()
        names = XBOX_TARGET_NAMES if device_type == VirtualDeviceType.XBOX else PS4_TARGET_NAMES
        for code, name in names.items():
            self._combo.addItem(name, code)
        if current is not None:
            idx = self._combo.findData(current)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        form.addRow("Destino:", self._combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_code(self) -> int | None:
        return self._combo.currentData()


# ---------------------------------------------------------------------------
# Main mapping widget (left "Controls" panel)
# ---------------------------------------------------------------------------
class MappingTabWidget(QWidget):
    """Controller overlay + mapping list with listen/edit/remove support."""

    mappings_changed = Signal(object)

    def __init__(self, parent=None, worker=None):
        super().__init__(parent)
        self._worker = worker
        self._mappings: dict[int, int] = {}
        self._macros: dict[int, list] = {}
        self._device_type = VirtualDeviceType.XBOX
        self._listen_dialog: ListenDialog | None = None
        self._listen_for: int | None = None

        self._setup_ui()
        if worker is not None:
            try:
                worker.raw_event.connect(self._on_raw_event)
            except Exception:
                logger.debug("MappingTabWidget: worker has no raw_event signal")

    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.overlay = ControllerOverlayWidget(self)
        self.overlay.button_selected.connect(self._select_in_list)
        layout.addWidget(self.overlay, 3)

        header = QHBoxLayout()
        title = QLabel("Mapeamentos")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self.listen_btn = QPushButton("Ouvir")
        self.listen_btn.setToolTip("Pressione uma tecla física para adicionar/selecionar")
        self.listen_btn.clicked.connect(self._start_listen)
        header.addWidget(self.listen_btn)

        self.edit_btn = QPushButton("Alterar")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_selected)
        header.addWidget(self.edit_btn)

        self.remove_btn = QPushButton("Remover")
        self.remove_btn.setObjectName("dangerButton")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._remove_selected)
        header.addWidget(self.remove_btn)
        layout.addLayout(header)

        self.mapping_list = QListWidget()
        self.mapping_list.setAlternatingRowColors(True)
        self.mapping_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.mapping_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mapping_list.customContextMenuRequested.connect(self._show_context_menu)
        self.mapping_list.itemDoubleClicked.connect(lambda _i: self._edit_selected())
        self.mapping_list.itemSelectionChanged.connect(self._on_list_selection)
        layout.addWidget(self.mapping_list, 2)

        footer = QHBoxLayout()
        self.reset_btn = QPushButton("Restaurar padrão")
        self.reset_btn.clicked.connect(self._reset_defaults)
        footer.addWidget(self.reset_btn)
        footer.addStretch()
        self.count_label = QLabel("")
        self.count_label.setObjectName("dimLabel")
        footer.addWidget(self.count_label)
        layout.addLayout(footer)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def set_device_type(self, device_type: VirtualDeviceType):
        self._device_type = device_type
        self.overlay.set_device_type(device_type)
        self._refresh_list()

    def set_mappings(self, mappings: dict[int, int]):
        self._mappings = {int(k): int(v) for k, v in (mappings or {}).items()}
        self._refresh_list()
        self.overlay.set_mappings(self._mappings)

    def get_mappings(self) -> dict[int, int]:
        return dict(self._mappings)

    # ------------------------------------------------------------------
    # Macros (bind a recorded sequence to a physical button)
    # ------------------------------------------------------------------
    def set_macros(self, macros: dict[int, list]):
        self._macros = {int(k): list(v) for k, v in (macros or {}).items()}
        self._refresh_list()

    def get_macros(self) -> dict[int, list]:
        return {k: list(v) for k, v in self._macros.items()}

    def _edit_macro(self, physical: int):
        from .macro_dialog import MacroEditorDialog
        dlg = MacroEditorDialog(
            physical, self._macros.get(physical), self._worker, self
        )
        if dlg.exec() == QDialog.Accepted:
            actions = dlg.get_actions()
            if actions:
                self._macros[int(physical)] = actions
            else:
                self._macros.pop(int(physical), None)
            self._refresh_list()
        # The editor is recreated on every click — destroy the C++ object too
        # so repeated edits don't accumulate hidden dialogs (leak).
        dlg.deleteLater()

    def clear(self):
        self._mappings.clear()
        self._refresh_list()
        self.overlay.set_mappings(self._mappings)
        self.mappings_changed.emit(self.get_mappings())

    def _reset_defaults(self):
        defaults = (DS4_TO_XBOX_BTN_MAP if self._device_type == VirtualDeviceType.XBOX
                    else DS4_TO_PS4_BTN_MAP)
        self._mappings = {int(k): int(v) for k, v in defaults.items()}
        self._refresh_list()
        self.overlay.set_mappings(self._mappings)
        self.mappings_changed.emit(self.get_mappings())

    def _set_mapping(self, physical: int, target: int):
        self._mappings[int(physical)] = int(target)
        self._refresh_list()
        self.overlay.set_mappings(self._mappings)
        self.mappings_changed.emit(self.get_mappings())

    def _remove_mapping(self, physical: int):
        self._mappings.pop(int(physical), None)
        self._refresh_list()
        self.overlay.set_mappings(self._mappings)
        self.mappings_changed.emit(self.get_mappings())

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def _refresh_list(self):
        selected = self._selected_code()
        self.mapping_list.blockSignals(True)
        self.mapping_list.clear()
        # Union of mapped codes and macro-only codes: a button whose mapping
        # was removed keeps its macro, and the row must stay visible so the
        # user can see (and remove) it — otherwise the orphan macro keeps
        # firing with no UI to reach it.
        for physical in sorted(set(self._mappings) | set(self._macros)):
            target = self._mappings.get(physical)
            macro_tag = "  [macro]" if int(physical) in self._macros else ""
            if target is None:
                label = f"{physical_name(physical)}   →   (sem mapeamento){macro_tag}"
            else:
                label = (
                    f"{physical_name(physical)}   →   "
                    f"{target_name(target, self._device_type)}{macro_tag}"
                )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, physical)
            item.setData(Qt.UserRole + 1, target)
            self.mapping_list.addItem(item)
        self.mapping_list.blockSignals(False)

        self.count_label.setText(f"{len(self._mappings)} teclas mapeadas")
        if selected is not None:
            self._select_in_list(selected)

    def _selected_code(self) -> int | None:
        items = self.mapping_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.UserRole)

    def _select_in_list(self, code: int):
        for row in range(self.mapping_list.count()):
            item = self.mapping_list.item(row)
            if item.data(Qt.UserRole) == code:
                self.mapping_list.blockSignals(True)
                self.mapping_list.setCurrentItem(item)
                self.mapping_list.blockSignals(False)
                self.mapping_list.scrollToItem(item)
                self.overlay.set_selected(code)
                self.edit_btn.setEnabled(True)
                self.remove_btn.setEnabled(True)
                return
        self.overlay.set_selected(code)

    def _on_list_selection(self):
        code = self._selected_code()
        self.edit_btn.setEnabled(code is not None)
        self.remove_btn.setEnabled(code is not None)
        self.overlay.set_selected(code)

    def _show_context_menu(self, pos):
        item = self.mapping_list.itemAt(pos)
        if not item:
            return
        code = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Alterar destino...", lambda: self._edit_mapping(code))
        macro_label = ("Editar macro..." if code in self._macros
                       else "Gravar macro...")
        menu.addAction(macro_label, lambda: self._edit_macro(code))
        if code in self._macros:
            menu.addAction("Remover macro", lambda: self._remove_macro(code))
        if code in self._mappings:
            menu.addAction("Remover mapeamento", lambda: self._remove_mapping(code))
        menu.addSeparator()
        menu.addAction("Ouvir tecla física...", self._start_listen)
        menu.exec(self.mapping_list.mapToGlobal(pos))

    def _remove_macro(self, physical: int):
        self._macros.pop(int(physical), None)
        self._refresh_list()

    def _edit_selected(self):
        code = self._selected_code()
        if code is not None:
            self._edit_mapping(code)

    def _remove_selected(self):
        code = self._selected_code()
        if code is not None:
            self._remove_mapping(code)

    def _edit_mapping(self, physical: int):
        current = self._mappings.get(physical)
        dlg = TargetPickerDialog(physical, current, self._device_type, self)
        if dlg.exec() == QDialog.Accepted:
            target = dlg.selected_code()
            if target is not None:
                self._set_mapping(physical, target)

    # ------------------------------------------------------------------
    # Listen mode
    # ------------------------------------------------------------------
    def _start_listen(self, _checked=False, for_code: int | None = None):
        self._listen_for = for_code
        self._listen_dialog = ListenDialog(self)
        self._listen_dialog.captured.connect(self._on_listen_captured)
        # open() keeps the main event loop running, so worker.raw_event
        # keeps flowing into capture_event while the dialog is visible.
        self._listen_dialog.open()

    def _on_listen_captured(self, code: int, value: int):
        physical = self._listen_for if self._listen_for is not None else code
        if physical == e.ABS_HAT0X:
            physical = DS4Btn.DPAD_LEFT if value < 0 else DS4Btn.DPAD_RIGHT
        elif physical == e.ABS_HAT0Y:
            physical = DS4Btn.DPAD_UP if value < 0 else DS4Btn.DPAD_DOWN
        self._listen_for = None

        if physical in self._mappings:
            self._select_in_list(int(physical))
            return

        # New button: map it to itself, then let the user pick a target
        self._mappings[int(physical)] = int(physical)
        self._refresh_list()
        self.overlay.set_mappings(self._mappings)
        self._select_in_list(int(physical))
        self._edit_mapping(int(physical))

    def _on_raw_event(self, event_type: int, code: int, value: int):
        if self._listen_dialog is not None and self._listen_dialog.isVisible():
            self._listen_dialog.capture_event(event_type, code, value)
        self.overlay.handle_raw_event(event_type, code, value)
