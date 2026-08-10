from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QGridLayout, QSlider, QSpinBox, QColorDialog
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPixmap, QPainter, QLinearGradient, QBrush, QCursor

from .styles import get_stylesheet


class ColorPreview(QWidget):
    def __init__(self, color: QColor = None):
        super().__init__()
        self._color = color or QColor(0, 0, 255)
        self.setFixedSize(60, 60)

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def get_color(self) -> QColor:
        return self._color

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 8, 8)


class HSVColorWheel(QWidget):
    color_changed = Signal(QColor)

    def __init__(self):
        super().__init__()
        self.setFixedSize(200, 200)
        self._color = QColor(0, 0, 255)
        self._hue = 240
        self._sat = 1.0
        self._val = 1.0
        self._drag_pos = None
        self.setMouseTracking(True)

    def set_color(self, color: QColor):
        self._color = color
        self._hue = color.hueF() * 360
        self._sat = color.saturationF()
        self._val = color.valueF()
        self.update()

    def get_color(self) -> QColor:
        return QColor.fromHsvF(self._hue / 360.0, self._sat, self._val)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        radius = min(w, h) / 2 - 2

        for y in range(h):
            for x in range(w):
                dx = x - cx
                dy = y - cy
                dist = (dx * dx + dy * dy) ** 0.5
                if dist <= radius:
                    angle = (180 + int((dy < 0) * 180 + (dx >= 0) * 90 + (dx < 0 and dy < 0) * 180)) % 360
                    import math
                    angle = math.degrees(math.atan2(dy, dx))
                    if angle < 0:
                        angle += 360
                    hue = angle
                    sat = dist / radius
                    val = 1.0
                    color = QColor.fromHsvF(hue / 360.0, sat, val)
                    painter.setPen(color)
                    painter.drawPoint(x, y)

        sat = self._sat
        val = self._val
        x = cx + radius * sat * __import__('math').cos(__import__('math').radians(self._hue))
        y = cy + radius * sat * __import__('math').sin(__import__('math').radians(self._hue))

        painter.setPen(Qt.white)
        painter.drawEllipse(int(x) - 6, int(y) - 6, 12, 12)
        painter.setPen(Qt.black)
        painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._update_from_pos(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._update_from_pos(event.pos())

    def _update_from_pos(self, pos):
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        radius = min(w, h) / 2 - 2

        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = (dx * dx + dy * dy) ** 0.5

        if dist <= radius:
            import math
            angle = math.degrees(math.atan2(dy, dx))
            if angle < 0:
                angle += 360
            self._hue = angle
            self._sat = min(1.0, dist / radius)
            self._color = QColor.fromHsvF(self._hue / 360.0, self._sat, self._val)
            self.color_changed.emit(self._color)
            self.update()


class ValueSlider(QWidget):
    value_changed = Signal(float)

    def __init__(self, orientation=Qt.Horizontal):
        super().__init__()
        self._orientation = orientation
        self._value = 1.0
        self.setFixedHeight(20) if orientation == Qt.Horizontal else self.setFixedWidth(20)
        self.setMinimumSize(200, 20) if orientation == Qt.Horizontal else self.setMinimumSize(20, 200)

    def set_value(self, value: float):
        self._value = max(0.0, min(1.0, value))
        self.update()

    def get_value(self) -> float:
        return self._value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._orientation == Qt.Horizontal:
            w = self.width()
            h = self.height()
            for x in range(w):
                hue = self._value
                color = QColor.fromHsvF(0, 0, x / w)
                painter.setPen(color)
                painter.drawLine(x, 0, x, h)
            handle_x = int(self._value * w)
            painter.setPen(Qt.white)
            painter.drawLine(handle_x, 0, handle_x, h)
            painter.setPen(Qt.black)
            painter.drawLine(handle_x - 1, 0, handle_x - 1, h)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._update_from_pos(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._update_from_pos(event.pos())

    def _update_from_pos(self, pos):
        if self._orientation == Qt.Horizontal:
            self._value = max(0.0, min(1.0, pos.x() / self.width()))
        self.value_changed.emit(self._value)
        self.update()


class ColorDialog(QDialog):
    def __init__(self, initial_color: QColor = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LED Color")
        self.setModal(True)
        self.resize(420, 480)
        self.setStyleSheet(get_stylesheet())

        self._color = initial_color or QColor(0, 0, 255)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Choose LED Color")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #e0e0e0;")
        layout.addWidget(title)

        self._wheel = HSVColorWheel()
        self._wheel.set_color(self._color)
        self._wheel.color_changed.connect(self._on_wheel_color_changed)
        layout.addWidget(self._wheel, alignment=Qt.AlignCenter)

        self._value_slider = ValueSlider(Qt.Horizontal)
        self._value_slider.set_value(self._color.valueF())
        self._value_slider.value_changed.connect(self._on_value_changed)
        layout.addWidget(self._value_slider)

        rgb_layout = QGridLayout()
        rgb_layout.setSpacing(8)

        self._r_spin = self._create_spinbox()
        self._g_spin = self._create_spinbox()
        self._b_spin = self._create_spinbox()

        for i, (label, spin) in enumerate([("R", self._r_spin), ("G", self._g_spin), ("B", self._b_spin)]):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight: 600; color: #a0a0b0;")
            rgb_layout.addWidget(lbl, 0, i)
            rgb_layout.addWidget(spin, 1, i)

        self._r_spin.setValue(self._color.red())
        self._g_spin.setValue(self._color.green())
        self._b_spin.setValue(self._color.blue())

        self._r_spin.valueChanged.connect(self._on_rgb_changed)
        self._g_spin.valueChanged.connect(self._on_rgb_changed)
        self._b_spin.valueChanged.connect(self._on_rgb_changed)

        layout.addLayout(rgb_layout)

        hex_layout = QHBoxLayout()
        hex_label = QLabel("HEX:")
        hex_label.setStyleSheet("font-weight: 600; color: #a0a0b0;")
        self._hex_edit = QLineEdit()
        self._hex_edit.setPlaceholderText("#0000FF")
        self._hex_edit.setText(self._color.name().upper())
        self._hex_edit.textChanged.connect(self._on_hex_changed)
        hex_layout.addWidget(hex_label)
        hex_layout.addWidget(self._hex_edit)
        layout.addLayout(hex_layout)

        preset_layout = QHBoxLayout()
        presets = [
            ("#00D4AA", "Teal"),
            ("#FF6B6B", "Red"),
            ("#FFD93D", "Yellow"),
            ("#6BFF6B", "Green"),
            ("#A855F7", "Purple"),
            ("#FF8800", "Orange"),
            ("#0088FF", "Blue"),
            ("#FFFFFF", "White"),
        ]
        for hex_color, name in presets:
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setToolTip(name)
            btn.setStyleSheet(f"background-color: {hex_color}; border: 2px solid #3a3a5c; border-radius: 6px;")
            btn.clicked.connect(lambda checked, c=hex_color: self._on_preset_clicked(c))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("Apply")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _create_spinbox(self):
        from PySide6.QtWidgets import QSpinBox
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setFixedWidth(60)
        spin.setAlignment(Qt.AlignCenter)
        return spin

    def _on_wheel_color_changed(self, color: QColor):
        self._color = QColor.fromHsvF(color.hueF(), color.saturationF(), self._color.valueF())
        self._update_ui_from_color()

    def _on_value_changed(self, value: float):
        self._color = QColor.fromHsvF(self._color.hueF(), self._color.saturationF(), value)
        self._update_ui_from_color()

    def _on_rgb_changed(self):
        r = self._r_spin.value()
        g = self._g_spin.value()
        b = self._b_spin.value()
        self._color = QColor(r, g, b)
        self._update_ui_from_color()

    def _on_hex_changed(self, text: str):
        if text.startswith("#") and len(text) == 7:
            try:
                color = QColor(text)
                if color.isValid():
                    self._color = color
                    self._update_ui_from_color(sync_hex=False)
            except Exception:
                pass

    def _on_preset_clicked(self, hex_color: str):
        self._color = QColor(hex_color)
        self._update_ui_from_color()

    def _update_ui_from_color(self, sync_hex=True):
        self._wheel.set_color(self._color)
        self._value_slider.set_value(self._color.valueF())
        self._r_spin.blockSignals(True)
        self._g_spin.blockSignals(True)
        self._b_spin.blockSignals(True)
        self._r_spin.setValue(self._color.red())
        self._g_spin.setValue(self._color.green())
        self._b_spin.setValue(self._color.blue())
        self._r_spin.blockSignals(False)
        self._g_spin.blockSignals(False)
        self._b_spin.blockSignals(False)
        if sync_hex:
            self._hex_edit.blockSignals(True)
            self._hex_edit.setText(self._color.name().upper())
            self._hex_edit.blockSignals(False)

    def get_color(self) -> QColor:
        return self._color

    @staticmethod
    def get_color_static(initial_color: QColor = None, parent=None) -> QColor:
        dialog = ColorDialog(initial_color, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.get_color()
        return initial_color


from PySide6.QtWidgets import QLineEdit