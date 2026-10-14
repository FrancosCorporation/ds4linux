"""Macro editor dialog — record and edit button sequences (DS4Windows-style).

A macro is a list of MacroAction ('key' press/release or 'wait') triggered
when a physical button is pressed. Recording listens to raw events from the
slot's worker thread (already emitted for GUI highlight); if no worker is
available, steps can be added manually.

The dialog edits a single button's macro. The result is a
``list[MacroAction]`` assigned to ``profile.macros[ds4_code]`` and persisted
by ProfileManager.
"""
from __future__ import annotations

import logging

from evdev import ecodes as e
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..constants import DS4Btn
from ..engine.input_mapper import MacroAction
from .mapping_tab import physical_name

logger = logging.getLogger(__name__)


def button_label(code: int) -> str:
    """Human name for a physical DS4 button code."""
    try:
        return DS4Btn(code).name.replace("_", " ").title()
    except ValueError:
        pass
    return physical_name(code) or f"0x{code:03X}"


class MacroEditorDialog(QDialog):
    """Record / edit the macro bound to one physical DS4 button."""

    def __init__(self, ds4_code: int, actions: list[MacroAction] | None = None,
                 worker=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Macro — {button_label(ds4_code)}")
        self.setMinimumWidth(480)
        self._ds4_code = ds4_code
        self._actions: list[MacroAction] = list(actions or [])
        self._recording = False
        self._last_press_code: int | None = None
        self._worker = None

        self._build_ui(worker)
        self._refresh_list()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self, worker):
        layout = QVBoxLayout(self)

        hint = QLabel(
            "Grave uma sequência: pressione Gravar e aperte os botões do controle "
            "na ordem desejada. Cada botão gera press + release; a gravação "
            "adiciona uma pausa entre passos automaticamente."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget()
        layout.addWidget(self._list, 1)

        rec_row = QHBoxLayout()
        self._rec_btn = QPushButton("● Gravar")
        self._rec_btn.setCheckable(True)
        self._rec_btn.toggled.connect(self._toggle_recording)
        rec_row.addWidget(self._rec_btn)

        self._stop_btn = QPushButton("Parar")
        self._stop_btn.clicked.connect(lambda: self._rec_btn.setChecked(False))
        rec_row.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("Limpar")
        self._clear_btn.clicked.connect(self._clear)
        rec_row.addWidget(self._clear_btn)
        rec_row.addStretch()
        layout.addLayout(rec_row)

        manual_row = QHBoxLayout()
        self._type_combo = QComboBox()
        self._type_combo.addItems(["key", "wait"])
        manual_row.addWidget(QLabel("Passo manual:"))
        manual_row.addWidget(self._type_combo)
        self._code_spin = QComboBox()
        for btn in DS4Btn:
            self._code_spin.addItem(button_label(int(btn)), int(btn))
        self._code_spin.setEnabled(False)
        self._type_combo.currentTextChanged.connect(
            lambda t: self._code_spin.setEnabled(t == "key")
        )
        manual_row.addWidget(self._code_spin)
        self._delay_spin = QDoubleSpinBox()
        self._delay_spin.setRange(0.0, 10.0)
        self._delay_spin.setSingleStep(0.05)
        self._delay_spin.setValue(0.05)
        self._delay_spin.setSuffix(" s")
        manual_row.addWidget(self._delay_spin)
        add_btn = QPushButton("Adicionar")
        add_btn.clicked.connect(self._add_manual)
        manual_row.addWidget(add_btn)
        layout.addLayout(manual_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Live capture from the slot worker (raw events already flow for the
        # GUI highlight feature; connect if a worker exists).
        self._worker = worker
        if worker is not None:
            try:
                worker.raw_event.connect(self._on_raw_event)
            except Exception:
                logger.debug("Macro editor: could not connect worker", exc_info=True)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _toggle_recording(self, on: bool):
        self._recording = on
        self._rec_btn.setText("■ Gravando..." if on else "● Gravar")
        self._last_press_code = None

    def _on_raw_event(self, event_type: int, code: int, value: int):
        """Capture EV_KEY presses/releases while recording."""
        if not self._recording or event_type != e.EV_KEY:
            return
        try:
            DS4Btn(code)
        except ValueError:
            return  # only physical DS4 buttons

        if value == 1:
            self._append_step(MacroAction("key", code, 1))
            self._last_press_code = code
        elif value == 0 and self._last_press_code == code:
            self._append_step(MacroAction("key", code, 0))
            self._last_press_code = None
            # Small pause between key pairs, recorded as an explicit wait
            self._append_step(MacroAction("wait", 0, 0, 0.05))

    def _append_step(self, action: MacroAction):
        self._actions.append(action)
        self._refresh_list()

    def _add_manual(self):
        kind = self._type_combo.currentText()
        if kind == "key":
            code = self._code_spin.currentData()
            if code is None:
                return
            self._append_step(MacroAction("key", int(code), 1))
            self._append_step(MacroAction("key", int(code), 0, self._delay_spin.value()))
        else:
            self._append_step(MacroAction("wait", 0, 0, self._delay_spin.value()))
        self._refresh_list()

    def _clear(self):
        self._actions.clear()
        self._refresh_list()

    # ------------------------------------------------------------------
    # List rendering / item ops
    # ------------------------------------------------------------------
    def _describe(self, a: MacroAction) -> str:
        if a.action_type == "wait":
            return f"esperar {a.delay:.2f}s"
        name = button_label(a.code)
        return f"{name} {'pressionar' if a.value == 1 else 'soltar'}"

    def _refresh_list(self):
        self._list.clear()
        for i, a in enumerate(self._actions):
            item = QListWidgetItem(f"{i + 1}. {self._describe(a)}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)

    def _remove_selected(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._actions):
            del self._actions[row]
            self._refresh_list()

    def _move(self, delta: int):
        row = self._list.currentRow()
        if not 0 <= row < len(self._actions):
            return
        new = row + delta
        if not 0 <= new < len(self._actions):
            return
        self._actions[row], self._actions[new] = self._actions[new], self._actions[row]
        self._refresh_list()
        self._list.setCurrentRow(new)

    def keyPressEvent(self, event):  # noqa: N802 (Qt override)
        if event.key() == Qt.Key.Key_Delete:
            self._remove_selected()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------
    def get_actions(self) -> list[MacroAction]:
        return list(self._actions)

    def done(self, result: int):  # noqa: N802 (Qt override)
        # accept()/reject()/Esc/window-close all funnel through done(), so
        # dropping the worker hook here guarantees a closed editor never
        # keeps listening to the long-lived worker (leak + duplicate signal).
        self._disconnect_worker()
        super().done(result)

    def _disconnect_worker(self):
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        try:
            worker.raw_event.disconnect(self._on_raw_event)
        except (RuntimeError, TypeError):
            pass  # already disconnected / worker destroyed
