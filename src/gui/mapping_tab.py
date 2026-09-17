from __future__ import annotations
import logging
from typing import Optional, Dict, Tuple, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QDialogButtonBox, QMessageBox, QProgressBar,
    QListWidget, QListWidgetItem, QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen, QBrush

from ..constants import DS4Btn, XboxBtn, PS4Btn

logger = logging.getLogger(__name__)

# Coordinates defined for overlay
BUTTON_DEFS: List[Tuple[int, str, float, float, float, float]] = [
    (DS4Btn.NORTH, "△", 0.72, 0.22, 0.06, 0.06),
    (DS4Btn.EAST, "○", 0.78, 0.40, 0.06, 0.06),
    (DS4Btn.SOUTH, "×", 0.72, 0.58, 0.06, 0.06),
    (DS4Btn.WEST, "□", 0.66, 0.40, 0.06, 0.06),
]

class ControllerOverlayWidget(QWidget):
    button_clicked = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._button_widgets = {}
        self.setMinimumSize(400, 300)
        self._setup_buttons()

    def _setup_buttons(self):
        for ds4_code, label, rx, ry, rw, rh in BUTTON_DEFS:
            btn = QPushButton(label, self)
            btn.setStyleSheet("background: rgba(50, 50, 70, 0.8); color: white; border-radius: 5px;")
            btn.clicked.connect(lambda _, c=ds4_code: self.button_clicked.emit(c))
            self._button_widgets[ds4_code] = btn

    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        for ds4_code, _, rx, ry, rw, rh in BUTTON_DEFS:
            btn = self._button_widgets.get(ds4_code)
            if btn: btn.setGeometry(int(rx*w), int(ry*h), int(rw*w), int(rh*h))

    def highlight_button(self, ds4_code: int):
        btn = self._button_widgets.get(ds4_code)
        if btn: btn.setStyleSheet("background: rgba(0, 212, 170, 0.9); color: black; font-weight: bold; border-radius: 5px;")

    def unhighlight_button(self, ds4_code: int):
        btn = self._button_widgets.get(ds4_code)
        if btn: btn.setStyleSheet("background: rgba(50, 50, 70, 0.8); color: white; border-radius: 5px;")

class MappingTabWidget(QWidget):
    def __init__(self, parent=None, worker=None):
        super().__init__(parent)
        self.worker = worker
        layout = QVBoxLayout(self)
        self.overlay = ControllerOverlayWidget(self)
        layout.addWidget(self.overlay)
        
        if self.worker:
            self.worker.raw_event.connect(self._on_raw_event)

    def _on_raw_event(self, event_type: int, code: int, value: int):
        from evdev import ecodes as e
        if event_type == e.EV_KEY:
            if value == 1: self.overlay.highlight_button(code)
            elif value == 0: self.overlay.unhighlight_button(code)

class ListenDialog(QDialog):
    result = Signal(int, int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aguardando entrada...")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Pressione um botão no controle físico"))
    
    def capture_event(self, event_type, code, value):
        from evdev import ecodes as e
        if event_type == e.EV_KEY and value == 1:
            self.result.emit(code, value)
            self.accept()
