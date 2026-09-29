"""Frameless on-screen display (OSD) for connection/battery/profile notices.

Usage::

    osd = OSDOverlay()
    osd.notify("Controle 1 conectado")          # auto-hide after 2.5 s
    osd.notify("Bateria: 20%", level="low")     # colored border

The widget is a frameless, always-on-top, click-through toast anchored to the
bottom-right of the screen. It stacks up to a few messages and fades out.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

OSD_LEVEL_COLORS = {
    "info": "#00d4aa",
    "warn": "#ffb454",
    "error": "#ff5c5c",
    "low": "#ffb454",
}

MAX_VISIBLE = 4
DEFAULT_TIMEOUT_MS = 2500


class _OSDRow(QWidget):
    """One notification line with a colored left border."""

    def __init__(self, text: str, level: str, parent=None):
        super().__init__(parent)
        color = OSD_LEVEL_COLORS.get(level, OSD_LEVEL_COLORS["info"])

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: rgba(30, 30, 46, 235);"
            f"border-left: 3px solid {color};"
            f"border-radius: 4px;"
            f"padding: 6px 12px;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self.label = QLabel(text)
        self.label.setStyleSheet("color:#ffffff; border:none; background:transparent;")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.label.setFont(font)
        layout.addWidget(self.label)
        self.setFixedHeight(34)


class OSDOverlay(QWidget):
    """Bottom-right toast overlay. Call ``notify()`` from any thread via signal."""

    requested = Signal(str, str)  # text, level

    def __init__(self):
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Click-through: notifications must never steal focus from a game.
        # WindowTransparentForInput makes the window manager forward clicks
        # to whatever is underneath; the widget attribute alone would only
        # make Qt discard them (swallowing clicks for up to 2.5 s).
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._vbox = QVBoxLayout(self)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(6)
        self._rows: list[tuple[_OSDRow, QTimer]] = []

        self.requested.connect(self._on_requested)
        self._reposition()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def notify(self, text: str, level: str = "info"):
        """Show a notification (thread-safe: emits a queued signal)."""
        self.requested.emit(text, level)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _on_requested(self, text: str, level: str):
        row = _OSDRow(text, level, self)
        self._vbox.addWidget(row)

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._dismiss(row))
        timer.start(DEFAULT_TIMEOUT_MS)

        self._rows.append((row, timer))
        # Drop the oldest row beyond the visible limit (stop its timer first,
        # otherwise it fires later on an already-deleted row).
        while len(self._rows) > MAX_VISIBLE:
            old_row, old_timer = self._rows.pop(0)
            old_timer.stop()
            old_timer.deleteLater()
            old_row.setParent(None)
            old_row.deleteLater()

        self._reposition()
        self.show()

    def _dismiss(self, row: _OSDRow):
        entry = next((e for e in self._rows if e[0] is row), None)
        if entry is not None:
            _old_row, timer = entry
            self._rows.remove(entry)
            timer.stop()
            timer.deleteLater()
        try:
            if row.parent() is self:
                row.setParent(None)
            row.deleteLater()
        except RuntimeError:
            pass  # already deleted (defensive: double-dismiss)
        if not self._rows:
            self.hide()
        else:
            self._reposition()

    def _reposition(self):
        screen = self.screen() or (self.window().screen()
                                   if self.window() else None)
        geo = None
        if screen is not None:
            try:
                geo = screen.availableGeometry()
            except Exception:
                geo = None
        if geo is None:
            # No screen at all (headless/teardown): skip repositioning
            # rather than crashing on primaryScreen() being None.
            from PySide6.QtGui import QGuiApplication
            primary = QGuiApplication.primaryScreen()
            if primary is None:
                return
            geo = primary.availableGeometry()
        self.adjustSize()
        margin = 24
        self.move(geo.right() - self.width() - margin,
                  geo.bottom() - self.height() - margin)
