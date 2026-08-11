from __future__ import annotations

from typing import List, Optional, Dict
from pathlib import Path
import logging

from evdev import InputDevice
from PySide6.QtCore import QObject, Signal

from .controller_slot import ControllerSlot, SlotStatus
from .device_monitor import DeviceMonitor
from ..constants import DS4_VID, DS4_PIDS, MAX_CONTROLLERS
from ..config.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


class MultiDeviceManager(QObject):
    """
    Manages multiple ControllerSlots, dynamically assigning devices
    detected by DeviceMonitor.
    
    Emits signals so the GUI can update dynamically without fixed slot assumptions.
    """

    device_connected_signal = Signal(int, str)   # slot_id, device_path
    device_disconnected_signal = Signal(int)     # slot_id
    profiles_changed = Signal()                  # Emitted when a new profile is created

    def __init__(self, max_slots: int = MAX_CONTROLLERS):
        super().__init__()
        self.max_slots = max_slots
        self._slots: Dict[int, ControllerSlot] = {}
        self._profile_manager = ProfileManager()
        self._device_paths_in_use: set = set()

        for i in range(max_slots):
            slot = ControllerSlot(i, profile_manager=self._profile_manager)
            slot.log_message.connect(self._on_slot_log)
            slot.device_connected.connect(self._on_slot_device_connected)
            slot.device_disconnected.connect(self._on_slot_device_disconnected)
            self._slots[i] = slot

        self._monitor = DeviceMonitor()
        self._monitor.device_added.connect(self._on_device_added)
        self._monitor.device_removed.connect(self._on_device_removed)
        self._monitor.scan_finished.connect(self._on_scan_finished)
        self._monitor.start()

    def _on_scan_finished(self, paths: list):
        """Handle initial scan or periodic rescan."""
        # Find currently connected devices by their unique ID
        connected_uniqs = set()
        for slot in self._slots.values():
            if slot.is_connected and slot.device:
                connected_uniqs.add(slot.device.uniq)

        for path in paths:
            if path in self._device_paths_in_use:
                continue
            # Check if this device was previously connected (reconnection)
            try:
                from evdev import InputDevice
                dev = InputDevice(path)
                if dev.uniq in connected_uniqs:
                    # This is a reconnection - find the slot and reconnect
                    for slot in self._slots.values():
                        if slot.device and slot.device.uniq == dev.uniq and not slot.is_connected:
                            logger.info(f"Reconnecting device {dev.uniq} to slot {slot.slot_id}")
                            self._device_paths_in_use.add(path)
                            slot._device_path = path
                            if slot.attach_device(path):
                                slot.start_worker()
                                self.device_connected_signal.emit(slot.slot_id, path)
                            return
            except Exception:
                pass
            # Normal new device
            if path not in self._device_paths_in_use:
                self._try_assign_device(path)

    def _on_device_added(self, path: str):
        if path not in self._device_paths_in_use:
            self._try_assign_device(path)

    def _on_device_removed(self, path: str):
        for sid, slot in list(self._slots.items()):
            if slot.device_path == path:
                self._device_paths_in_use.discard(path)
                slot.stop_worker()
                slot.detach_device()
                self.device_disconnected_signal.emit(sid)
                logger.info(f"Removed controller at {path} from slot {sid}")

    def _on_slot_device_connected(self, device):
        """Forward slot device_connected signal for GUI updates."""
        # Find which slot this is
        for sid, slot in self._slots.items():
            if slot.device is device:
                self.device_connected_signal.emit(sid, slot.device_path or "")

    def _on_slot_device_disconnected(self):
        """Forward slot device_disconnected signal for GUI updates."""
        for sid, slot in self._slots.items():
            if not slot.is_connected and slot.device_path is None:
                pass  # Already handled by _on_device_removed

    def _on_slot_log(self, msg: str):
        logger.info(msg)

    def _try_assign_device(self, path: str) -> bool:
        slot = self._get_available_slot()
        if not slot:
            logger.warning("All controller slots in use")
            return False

        profile = self._profile_manager.load_profile(
            self._profile_manager.get_current_profile_name() or "Default"
        )
        slot.set_profile(profile)

        if slot.attach_device(path):
            self._device_paths_in_use.add(path)
            slot.start_worker()
            self.device_connected_signal.emit(slot.slot_id, path)
            logger.info(f"Assigned {path} to slot {slot.slot_id}")
            return True
        return False

    # ------------------------------------------------------------------
    # Slot management
    # ------------------------------------------------------------------
    def get_slot(self, slot_id: int) -> Optional[ControllerSlot]:
        return self._slots.get(slot_id)

    def get_all_slots(self) -> List[ControllerSlot]:
        return list(self._slots.values())

    def get_connected_slots(self) -> List[ControllerSlot]:
        return [s for s in self._slots.values() if s.is_connected]

    def get_available_slot(self) -> Optional[ControllerSlot]:
        for slot in self._slots.values():
            if not slot.is_connected:
                return slot
        return None

    def _get_available_slot(self) -> Optional[ControllerSlot]:
        return self.get_available_slot()

    def get_slot_by_device_path(self, device_path: str) -> Optional[ControllerSlot]:
        for slot in self._slots.values():
            if slot.device_path == device_path:
                return slot
        return None

    def connect_slot_to_device(self, slot_id: int, device_path: str) -> bool:
        slot = self.get_slot(slot_id)
        if not slot:
            return False

        if slot.is_connected:
            if slot.device_path == device_path:
                return True
            slot.detach_device()
            if slot.device_path:
                self._device_paths_in_use.discard(slot.device_path)

        if device_path in self._device_paths_in_use:
            other_slot = self.get_slot_by_device_path(device_path)
            if other_slot and other_slot != slot:
                other_slot.detach_device()

        profile = self._profile_manager.load_profile(
            self._profile_manager.get_current_profile_name() or "Default"
        )
        slot.set_profile(profile)

        if slot.attach_device(device_path):
            self._device_paths_in_use.add(device_path)
            slot.start_worker()
            self.device_connected_signal.emit(slot.slot_id, device_path)
            return True
        return False

    def disconnect_slot(self, slot_id: int):
        slot = self.get_slot(slot_id)
        if slot and slot.is_connected:
            slot.stop_worker()
            if slot.device_path:
                self._device_paths_in_use.discard(slot.device_path)
            slot.detach_device()
            self.device_disconnected_signal.emit(slot_id)

    def disconnect_all(self):
        for slot in list(self._slots.values()):
            if slot.is_connected:
                slot.stop_worker()
                if slot.device_path:
                    self._device_paths_in_use.discard(slot.device_path)
                slot.detach_device()
                self.device_disconnected_signal.emit(slot.slot_id)

    def cleanup(self):
        """Properly clean up all resources - called on app close."""
        self._monitor.stop()
        self.disconnect_all()
        # Give threads time to finish
        for slot in self._slots.values():
            slot.cleanup()

    def reload_profiles(self):
        """Reload available profiles and emit signal for GUI update."""
        self.profiles_changed.emit()