from typing import List, Optional, Dict
from pathlib import Path
import logging

from evdev import InputDevice, list_devices

from .device_manager import DeviceManager
from .controller_slot import ControllerSlot, SlotStatus
from ..constants import DS4_VID, DS4_PID, DS4_PID_DONGLE, MAX_CONTROLLERS

logger = logging.getLogger(__name__)


class MultiDeviceManager:
    def __init__(self, max_slots: int = 2):
        self.max_slots = max_slots
        self._slots: Dict[int, ControllerSlot] = {}
        self._device_paths_in_use: set = set()
        
        for i in range(max_slots):
            slot = ControllerSlot(i)
            self._slots[i] = slot

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

    def find_all_ds4_devices(self) -> List[InputDevice]:
        devices = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                if dev.info.vendor == DS4_VID and dev.info.product in (DS4_PID, DS4_PID_DONGLE):
                    if path not in self._device_paths_in_use:
                        devices.append(dev)
            except (OSError, PermissionError):
                pass
        return devices

    def auto_assign_devices(self) -> int:
        devices = self.find_all_ds4_devices()
        assigned = 0
        for device in devices:
            if assigned >= self.max_slots:
                break
            slot = self.get_available_slot()
            if slot:
                if slot.connect(device.path):
                    self._device_paths_in_use.add(device.path)
                    slot.start_worker()
                    assigned += 1
        return assigned

    def connect_slot_to_device(self, slot_id: int, device_path: str) -> bool:
        slot = self.get_slot(slot_id)
        if not slot:
            return False
        
        if slot.is_connected:
            if slot.device_path == device_path:
                return True
            slot.disconnect()
            if slot.device_path:
                self._device_paths_in_use.discard(slot.device_path)
        
        if device_path in self._device_paths_in_use:
            other_slot = self._find_slot_by_device_path(device_path)
            if other_slot and other_slot != slot:
                other_slot.disconnect()
        
        if slot.connect(device_path):
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
            slot.disconnect()

    def disconnect_all(self):
        for slot in self._slots.values():
            if slot.is_connected:
                slot.stop_worker()
                if slot.device_path:
                    self._device_paths_in_use.discard(slot.device_path)
                slot.disconnect()

    def _find_slot_by_device_path(self, device_path: str) -> Optional[ControllerSlot]:
        for slot in self._slots.values():
            if slot.device_path == device_path:
                return slot
        return None

    def cleanup(self):
        self.disconnect_all()