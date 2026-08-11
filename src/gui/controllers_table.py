from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QPushButton,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class ControllersTableWidget(QWidget):
    """
    DS4Windows-style controllers table.
    Columns: #, ID, Status, Ex, Battery, Link Profile ☑, Selected Profile ▼, Color █, Editar
    """
    controller_edit = Signal(int)  # slot_id

    def __init__(self, multi_manager, parent=None):
        super().__init__(parent)
        self.multi_manager = multi_manager
        self._setup_ui()
        self._connect_signals()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "#", "ID", "Status", "Ex", "Battery",
            "Link Profile", "Selected Profile", "Color", ""
        ])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for col in range(8):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.Fixed)
        header.resizeSection(8, 80)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

    def _connect_signals(self):
        for slot in self.multi_manager.get_all_slots():
            slot.status_changed.connect(
                lambda s, sid=slot.slot_id: self._on_slot_status_changed(sid)
            )
            slot.device_connected.connect(self._refresh)
            slot.device_disconnected.connect(self._refresh)
            slot.battery_update.connect(
                lambda pct, sid=slot.slot_id: self._on_battery_changed(sid, pct)
            )
            slot.log_message.connect(self._on_slot_log)

    def _on_slot_status_changed(self, slot_id: int):
        self._refresh_row(slot_id)

    def _on_battery_changed(self, slot_id: int, pct: int):
        self._refresh_row(slot_id)

    def _on_slot_log(self, msg: str):
        pass

    def refresh(self):
        self._refresh()

    def _refresh(self):
        self.table.setRowCount(0)
        slots = self.multi_manager.get_all_slots()
        for i, slot in enumerate(slots):
            self._insert_row(i, slot)
        self.table.resizeRowsToContents()

    def _refresh_row(self, slot_id: int):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and int(item.text()) == slot_id + 1:
                slot = self.multi_manager.get_slot(slot_id)
                if not slot:
                    continue
                status_item = self.table.item(r, 2)
                if slot.is_connected:
                    dev = slot.device
                    phys = dev.phys or "" if dev else ""
                    if "uinput" in phys.lower():
                        status_item.setText("● Virtual")
                        status_item.setForeground(QColor("#5dabff"))
                    elif dev and dev.uniq:
                        status_item.setText("● Bluetooth")
                        status_item.setForeground(QColor("#6bff6b"))
                    elif dev:
                        status_item.setText("● USB")
                        status_item.setForeground(QColor("#6bff6b"))
                    else:
                        status_item.setText("● Connected")
                        status_item.setForeground(QColor("#6bff6b"))
                    ex_item = self.table.item(r, 3)
                    if ex_item:
                        ex_item.setText("🔑")
                        ex_item.setToolTip("Device Grabber Active")
                    bat_item = self.table.item(r, 4)
                    if bat_item:
                        bat_item.setText(f"{slot.battery_level}%")
                    self._set_led_color_cell(r, slot)
                else:
                    status_item.setText("○ Disconnected")
                    status_item.setForeground(QColor("#ff6b6b"))
                    ex_item = self.table.item(r, 3)
                    if ex_item:
                        ex_item.setText("")
                    bat_item = self.table.item(r, 4)
                    if bat_item:
                        bat_item.setText("--")
                break

    def _insert_row(self, row: int, slot):
        self.table.insertRow(row)

        idx_item = QTableWidgetItem(str(row + 1))
        idx_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, idx_item)

        if slot.is_connected and slot.device:
            dev = slot.device
            # Show device name + Bluetooth address if available
            dev_id = dev.name
            if dev.uniq:
                dev_id = f"{dev.name} ({dev.uniq})"
        else:
            dev_id = "No controller"
        self.table.setItem(row, 1, QTableWidgetItem(dev_id))

        status_item = QTableWidgetItem()
        if slot.is_connected:
            dev = slot.device
            if dev and "uinput" in (dev.phys or "").lower():
                status_item.setText("● Virtual")
                status_item.setForeground(QColor("#5dabff"))
            elif dev and dev.uniq:
                status_item.setText("● Bluetooth")
                status_item.setForeground(QColor("#6bff6b"))
            elif dev:
                status_item.setText("● USB")
                status_item.setForeground(QColor("#6bff6b"))
            else:
                status_item.setText("● Connected")
                status_item.setForeground(QColor("#6bff6b"))
        else:
            status_item.setText("○ Disconnected")
            status_item.setForeground(QColor("#ff6b6b"))
        self.table.setItem(row, 2, status_item)

        ex_item = QTableWidgetItem()
        if slot.is_connected:
            ex_item.setText("🔑")
            ex_item.setToolTip("Device Grabber Active")
            ex_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, ex_item)

        bat_item = QTableWidgetItem()
        if slot.is_connected:
            bat_item.setText(f"{slot.battery_level}%")
        else:
            bat_item.setText("--")
        self.table.setItem(row, 4, bat_item)

        link_chk = QCheckBox()
        link_chk.setChecked(True)
        link_chk.setStyleSheet("margin-left: 40%; margin-right: 40%;")
        self.table.setCellWidget(row, 5, link_chk)

        profile_combo = QComboBox()
        pm = self.multi_manager._profile_manager
        profile_combo.addItems(pm.list_profiles())
        if slot.profile:
            idx = profile_combo.findText(slot.profile.name)
            if idx >= 0:
                profile_combo.setCurrentIndex(idx)
        profile_combo.currentTextChanged.connect(
            lambda txt, sid=slot.slot_id: self._on_profile_changed(sid, txt)
        )
        self.table.setCellWidget(row, 6, profile_combo)

        self._set_led_color_cell(row, slot)

        edit_btn = QPushButton("Editar")
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda _, sid=slot.slot_id: self.controller_edit.emit(sid))
        self.table.setCellWidget(row, 8, edit_btn)

    def _set_led_color_cell(self, row: int, slot):
        color = slot.get_led_color()
        color_item = QTableWidgetItem()
        color_item.setBackground(QColor(*color))
        self.table.setItem(row, 7, color_item)

    def _on_profile_changed(self, slot_id: int, profile_name: str):
        slot = self.multi_manager.get_slot(slot_id)
        if not slot:
            return
        pm = self.multi_manager._profile_manager
        profile = pm.load_profile(profile_name)
        slot.set_profile(profile)