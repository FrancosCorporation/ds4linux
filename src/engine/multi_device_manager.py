from __future__ import annotations

from typing import List, Optional, Dict
from pathlib import Path
import logging

from evdev import InputDevice

from .controller_slot import ControllerSlot, SlotStatus
from .device_monitor import DeviceMonitor
from ..constants import DS4_VID, DS4_PIDS, MAX_CONTROLLERS
from ..config.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


class MultiDeviceManager:
    def __init__(self, max_slots: int = MAX_CONTROLLERS):
        self.max_slots = max_slots
        self._slots: Dict[int, ControllerSlot] = {}
        self._profile_manager = ProfileManager()
        self._device_paths_in_use: set = set()

        # Create slots
        for i in range(max_slots):
            slot = ControllerSlot(i, profile_manager=self._profile_manager)
            slot.log_message.connect(self._on_slot_log)
            self._slots[i] = slot

        # Create device monitor in background thread
        self._monitor = DeviceMonitor()
        self._monitor.device_added.connect(self._on_device_added)
        self._monitor.device_removed.connect(self._on_device_removed)
        self._monitor.scan_finished.connect(self._on_scan_finished)
        self._monitor.start()

    # ------------------------------------------------------------------
    # Signal handlers for DeviceMonitor
    # ------------------------------------------------------------------
    def _on_scan_finished(self, paths: list):
        for path in paths:
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
                logger.info(f"Removed controller at {path} from slot {sid}")

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

        # Handle if device is already in use by another slot
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
            return True
        return False

    def disconnect_slot(self, slot_id: int):
        slot = self.get_slot(slot_id)
        if slot and slot.is_connected:
            slot.stop_worker()
            if slot.device_path:
                self._device_paths_in_use.discard(slot.device_path)
            slot.detach_device()

    def disconnect_all(self):
        for slot in self._slots.values():
            if slot.is_connected:
                slot.stop_worker()
                if slot.device_path:
                    self._device_paths_in_use.discard(slot.device_path)
                slot.detach_device()

    def cleanup(self):
        self._monitor.stop()
        self.disconnect_all()

    def _on_slot_log(self, msg: str):
        logger.info(msg)