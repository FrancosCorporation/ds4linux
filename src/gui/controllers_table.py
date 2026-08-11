from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QPushButton,
    QCheckBox, QColorDialog
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter

logger = logging.getLogger(__name__)

CREATE_NEW_TEXT = "➕ Criar Novo..."


class ControllersTableWidget(QWidget):
    """
    DS4Windows-style controllers table.
    Columns: #, ID, Status, Ex, Battery, Link Profile ☑, Selected Profile ▼, Color █, Editar
    
    Dynamically shows only connected controllers - starts empty.
    """
    controller_edit = Signal(int)  # slot_id
    profile_changed_signal = Signal(int, str)  # slot_id, profile_name

    def __init__(self, multi_manager, parent=None):
        super().__init__(parent)
        self.multi_manager = multi_manager
        self._setup_ui()
        self._connect_signals()
        # Start with empty table
        self.table.setRowCount(0)

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
        # Device add/remove signals
        self.multi_manager.device_connected_signal.connect(self._on_device_connected)
        self.multi_manager.device_disconnected_signal.connect(self._on_device_disconnected)
        self.multi_manager.profiles_changed.connect(self._on_profiles_changed)

        # Slot status/battery updates
        for slot in self.multi_manager.get_all_slots():
            slot.status_changed.connect(
                lambda s, sid=slot.slot_id: self._on_slot_status_changed(sid)
            )
            slot.battery_update.connect(
                lambda pct, sid=slot.slot_id: self._on_battery_changed(sid, pct)
            )

    def _on_device_connected(self, slot_id: int, device_path: str):
        """Add a new row when a device connects."""
        self._refresh()

    def _on_device_disconnected(self, slot_id: int):
        """Remove/refresh row when a device disconnects."""
        self._refresh()

    def _on_profiles_changed(self):
        """Refresh profile combos when profiles list changes."""
        self._refresh_profile_combos()

    def _refresh_profile_combos(self):
        """Update all profile combo boxes with latest profile list."""
        pm = self.multi_manager._profile_manager
        profile_names = pm.list_profiles()

        for r in range(self.table.rowCount()):
            combo = self.table.cellWidget(r, 6)
            if combo:
                current = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(profile_names)
                if current and profile_names:
                    idx = combo.findText(current)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        combo.setCurrentIndex(0)
                elif profile_names:
                    combo.setCurrentIndex(0)
                combo.addItem(CREATE_NEW_TEXT)
                combo.setCurrentIndex(min(combo.currentIndex(), combo.count() - 2))
                combo.blockSignals(False)

    def _on_slot_status_changed(self, slot_id: int):
        self._refresh_row(slot_id)

    def _on_battery_changed(self, slot_id: int, pct: int):
        self._refresh_row(slot_id)

    def refresh(self):
        self._refresh()

    def _refresh(self):
        """Rebuild the table from connected slots."""
        self.table.setRowCount(0)
        # Clear stale row-to-slot mapping
        if hasattr(self, '_row_to_slot'):
            self._row_to_slot.clear()
        slots = self.multi_manager.get_all_slots()
        row = 0
        for slot in slots:
            if not slot.is_connected:
                continue
            self._insert_row(row, slot)
            row += 1
        self.table.resizeRowsToContents()

    def _refresh_row(self, slot_id: int):
        """Refresh the row for a specific slot."""
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and int(item.text()) == slot_id + 1:
                slot = self.multi_manager.get_slot(slot_id)
                if not slot:
                    # Device disconnected - remove row
                    self.table.removeRow(r)
                    return
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
                    # Device disconnected
                    self.table.removeRow(r)
                break

    def _insert_row(self, row: int, slot):
        self.table.insertRow(row)

        # Column 0: Index
        idx_item = QTableWidgetItem(str(row + 1))
        idx_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, idx_item)

        # Column 1: Device ID (name + Bluetooth MAC)
        if slot.is_connected and slot.device:
            dev = slot.device
            dev_id = dev.name
            if dev.uniq:
                dev_id = f"{dev.name} ({dev.uniq})"
        else:
            dev_id = "No controller"
        self.table.setItem(row, 1, QTableWidgetItem(dev_id))

        # Column 2: Status
        status_item = QTableWidgetItem()
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
        else:
            status_item.setText("○ Disconnected")
            status_item.setForeground(QColor("#ff6b6b"))
        self.table.setItem(row, 2, status_item)

        # Column 3: Ex (grabber key icon)
        ex_item = QTableWidgetItem()
        if slot.is_connected:
            ex_item.setText("🔑")
            ex_item.setToolTip("Device Grabber Active")
            ex_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, ex_item)

        # Column 4: Battery
        bat_item = QTableWidgetItem()
        if slot.is_connected:
            bat_item.setText(f"{slot.battery_level}%")
        else:
            bat_item.setText("--")
        self.table.setItem(row, 4, bat_item)

        # Column 5: Link Profile checkbox
        link_chk = QCheckBox()
        link_chk.setChecked(True)
        link_chk.setStyleSheet("margin-left: 40%; margin-right: 40%;")
        self.table.setCellWidget(row, 5, link_chk)

        # Column 6: Profile combo box
        profile_combo = QComboBox()
        pm = self.multi_manager._profile_manager
        profile_names = pm.list_profiles()
        profile_combo.blockSignals(True)
        profile_combo.addItems(profile_names)
        if slot.profile:
            idx = profile_combo.findText(slot.profile.name)
            if idx >= 0:
                profile_combo.setCurrentIndex(idx)
        profile_combo.addItem(CREATE_NEW_TEXT)
        # Ensure we don't start on the "Create New" item
        if profile_combo.currentIndex() == profile_combo.count() - 1:
            profile_combo.setCurrentIndex(0)
        profile_combo.blockSignals(False)
        profile_combo.currentTextChanged.connect(
            lambda txt, sid=slot.slot_id: self._on_profile_changed(sid, txt)
        )
        self.table.setCellWidget(row, 6, profile_combo)

        # Column 7: Color cell (clickable)
        self._set_led_color_cell(row, slot)

        # Column 8: Edit button
        edit_btn = QPushButton("Editar")
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda _, sid=slot.slot_id: self.controller_edit.emit(sid))
        self.table.setCellWidget(row, 8, edit_btn)

    def _set_led_color_cell(self, row: int, slot):
        color = slot.get_led_color()
        color_item = QTableWidgetItem()
        color_item.setBackground(QColor(*color))
        color_item.setForeground(QColor(*color))
        color_item.setText(" ")
        self.table.setItem(row, 7, color_item)
        self.table.item(row, 7).setSizeHint(QSize(30, 20))

        # Store mapping of row to slot for click handler
        if not hasattr(self, '_row_to_slot'):
            self._row_to_slot = {}
        self._row_to_slot[row] = slot

        # Connect cellClicked signal once (use a flag to avoid duplicate connections)
        if not hasattr(self, '_color_cell_connected'):
            self.table.cellClicked.connect(self._on_color_cell_clicked)
            self._color_cell_connected = True

    def _on_color_cell_clicked(self, row: int, col: int):
        """Open color dialog when LED color cell is clicked."""
        if col != 7:
            return
        
        # Get the slot for this specific row
        slot = self._row_to_slot.get(row) if hasattr(self, '_row_to_slot') else None
        if not slot:
            return
        
        current_color = QColor(*slot.get_led_color())
        color = QColorDialog.getColor(current_color, self, "Selecione a cor do LED")
        if color.isValid():
            r, g, b = color.red(), color.green(), color.blue()
            slot.set_led_color(r, g, b)
            self._set_led_color_cell(row, slot)

    def _on_profile_changed(self, slot_id: int, profile_name: str):
        if profile_name == CREATE_NEW_TEXT:
            # Reset combo to previous selection
            combo = None
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and int(item.text()) == slot_id + 1:
                    combo = self.table.cellWidget(r, 6)
                    break
            if combo:
                combo.blockSignals(True)
                combo.setCurrentIndex(max(0, combo.count() - 2))
                combo.blockSignals(False)
            self._create_new_profile(slot_id)
            return

        slot = self.multi_manager.get_slot(slot_id)
        if not slot:
            return
        pm = self.multi_manager._profile_manager
        profile = pm.load_profile(profile_name)
        if profile:
            slot.set_profile(profile)

    def _create_new_profile(self, slot_id: int):
        """Create a new profile via input dialog."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self, "Novo Perfil",
            "Nome do perfil:"
        )
        if ok and name.strip():
            name = name.strip()
            pm = self.multi_manager._profile_manager
            if name in pm.list_profiles():
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Erro", f"Perfil '{name}' já existe.")
                return
            pm.create_profile(name)
            self._refresh_profile_combos()

            # Set the new profile on the slot
            slot = self.multi_manager.get_slot(slot_id)
            if slot:
                profile = pm.load_profile(name)
                if profile:
                    slot.set_profile(profile)

            # Update combo to show the new profile
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and int(item.text()) == slot_id + 1:
                    combo = self.table.cellWidget(r, 6)
                    if combo:
                        idx = combo.findText(name)
                        if idx >= 0:
                            combo.blockSignals(True)
                            combo.setCurrentIndex(idx)
                            combo.blockSignals(False)