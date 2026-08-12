from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPushButton, QLabel, QCheckBox,
    QGroupBox, QFormLayout, QComboBox, QDialog, QDialogButtonBox,
    QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ..engine.auto_profile import AutoProfileManager, AutoProfileRule

logger = logging.getLogger(__name__)


class _RuleDialog(QDialog):
    """Add / edit a single auto-profile rule."""

    def __init__(self, profile_manager, rule: AutoProfileRule | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Editar Regra" if rule else "Nova Regra")
        self.setMinimumWidth(400)
        self._pm = profile_manager
        self._rule = rule

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(rule.name if rule else "")
        self.name_edit.setPlaceholderText("Ex: God of War (PC)")
        form.addRow("Nome:", self.name_edit)

        self.program_edit = QLineEdit(rule.program if rule else "")
        self.program_edit.setPlaceholderText("Ex: godowar, heroic, wine (parcial, case-insensitive)")
        form.addRow("Programa:", self.program_edit)

        self.title_edit = QLineEdit(rule.title if rule else "")
        self.title_edit.setPlaceholderText("Ex: God of War (parcial, case-insensitive)")
        form.addRow("Título Janela:", self.title_edit)

        self.profile_combo = QComboBox()
        profiles = self._pm.list_profiles()
        self.profile_combo.addItems(profiles)
        if rule and rule.profile:
            idx = self.profile_combo.findText(rule.profile)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        form.addRow("Perfil:", self.profile_combo)

        self.enabled_check = QCheckBox()
        self.enabled_check.setChecked(rule.enabled if rule else True)
        form.addRow("Ativo:", self.enabled_check)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_rule(self) -> AutoProfileRule:
        return AutoProfileRule(
            name=self.name_edit.text().strip(),
            program=self.program_edit.text().strip(),
            title=self.title_edit.text().strip(),
            profile=self.profile_combo.currentText(),
            enabled=self.enabled_check.isChecked(),
        )

    def list_profiles(self):
        return [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())]


class AutoProfilesTab(QWidget):
    """DS4Windows-style Auto Profiles tab.

    Rules: when a matching foreground window is detected, the specified profile
    is automatically applied to all connected controllers.
    """

    log_message = Signal(str)

    def __init__(self, auto_profile: AutoProfileManager,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._ap = auto_profile
        self._profile_manager = auto_profile._profile_manager
        self._setup_ui()
        self._connect_signals()
        self._refresh_table()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ── Controls ──────────────────────────────────────────
        ctrl_group = QGroupBox("Controle Geral")
        ctrl_layout = QHBoxLayout(ctrl_group)

        self.enable_check = QCheckBox("Auto-Profile Ativo")
        self.enable_check.setChecked(self._ap.is_enabled())
        ctrl_layout.addWidget(self.enable_check)

        ctrl_layout.addSpacing(20)

        ctrl_layout.addWidget(QLabel("Perfil padrão (quando nenhum jogo detectado):"))
        self.default_combo = QComboBox()
        self.default_combo.addItems([""] + _list_profiles(self._ap))
        self.default_combo.setCurrentText(self._ap.get_default_profile())
        self.default_combo.setMinimumWidth(180)
        ctrl_layout.addWidget(self.default_combo)

        self.revert_check = QCheckBox("Reverter ao perfil padrão ao sair do jogo")
        self.revert_check.setChecked(self._ap.get_revert_to_default())
        ctrl_layout.addWidget(self.revert_check)

        ctrl_layout.addStretch()
        layout.addWidget(ctrl_group)

        # ── Rules table ───────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Ativo", "Nome", "Programa", "Título", "Perfil"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # ── Action buttons ────────────────────────────────────
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("Adicionar Regra")
        self.add_btn.setObjectName("primaryButton")
        self.add_btn.clicked.connect(self._on_add_rule)

        self.edit_btn = QPushButton("Editar")
        self.edit_btn.clicked.connect(self._on_edit_rule)

        self.delete_btn = QPushButton("Excluir")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.clicked.connect(self._on_delete_rule)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()

        self.status_label = QLabel("Detectando janela ativa...")
        self.status_label.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        btn_layout.addWidget(self.status_label)

        layout.addLayout(btn_layout)

    def _connect_signals(self):
        self.enable_check.toggled.connect(self._ap.set_enabled)
        self.default_combo.currentTextChanged.connect(self._on_default_changed)
        self.revert_check.toggled.connect(self._ap.set_revert_to_default)
        self._ap.active_profile_changed.connect(self._on_active_profile_changed)
        self._ap.detection_state_changed.connect(self._on_detection_state)
        self._ap.rules_changed.connect(self._refresh_table)

    # ── Table ─────────────────────────────────────────────────
    def _refresh_table(self):
        rules = self._ap.rules()
        self.table.setRowCount(len(rules))
        for i, r in enumerate(rules):
            en = QTableWidgetItem("✓" if r.enabled else "✗")
            en.setTextAlignment(Qt.AlignCenter)
            if r.enabled:
                en.setForeground(QColor("#6bff6b"))
            else:
                en.setForeground(QColor("#ff6b6b"))
            self.table.setItem(i, 0, en)
            self.table.setItem(i, 1, QTableWidgetItem(r.name))
            self.table.setItem(i, 2, QTableWidgetItem(r.program))
            self.table.setItem(i, 3, QTableWidgetItem(r.title))
            self.table.setItem(i, 4, QTableWidgetItem(r.profile))
        self.table.resizeRowsToContents()

    # ── Actions ───────────────────────────────────────────────
    def _on_add_rule(self):
        dlg = _RuleDialog(self._profile_manager, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._ap.add_rule(dlg.get_rule())
            self._refresh_table()

    def _on_edit_rule(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount():
            QMessageBox.information(self, "Selecionar", "Selecione uma regra na tabela.")
            return
        rule = self._ap.rules()[row]
        dlg = _RuleDialog(self._profile_manager, rule=rule, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._ap.update_rule(row, dlg.get_rule())
            self._refresh_table()

    def _on_delete_rule(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount():
            QMessageBox.information(self, "Selecionar", "Selecione uma regra na tabela.")
            return
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Excluir a regra \"{self._ap.rules()[row].name}\"?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._ap.remove_rule(row)
            self._refresh_table()

    def _on_default_changed(self, name: str):
        self._ap.set_default_profile(name)

    def _on_active_profile_changed(self, profile: str):
        self.log_message.emit(f"[Auto Profile] Perfil ativo: {profile}")

    def _on_detection_state(self, state: str):
        self.status_label.setText(f"Ativo: {state}")


def _list_profiles(ap: AutoProfileManager) -> list:
    if ap._profile_manager:
        return ap._profile_manager.list_profiles()
    return []
