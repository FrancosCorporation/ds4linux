from __future__ import annotations

import copy
import logging

from PySide6.QtCore import QObject, Signal

from ..config.profile_manager import ProfileManager
from ..constants import MAX_CONTROLLERS
from .controller_slot import ControllerSlot
from .device_monitor import DeviceMonitor

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
        self._slots: dict[int, ControllerSlot] = {}
        self._profile_manager = ProfileManager()
        self._device_paths_in_use: set = set()
        self._slot_paths: dict[int, str] = {}

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

    @staticmethod
    def scan_and_assign(mgr: MultiDeviceManager) -> None:
        """Static method to scan for devices and assign them.
        Called from main thread after Qt event loop starts."""
        import evdev
        paths = []
        for p in evdev.list_devices():
            dm = DeviceMonitor()
            if dm._is_real_ds4(p):
                paths.append(p)
        if paths:
            mgr._on_scan_finished(paths)

    def _on_scan_finished(self, paths: list):
        """Handle initial scan or periodic rescan."""
        for path in paths:
            if path in self._device_paths_in_use:
                continue
            # Reattach a returning controller to its former slot when its
            # stable HID unique ID is available.
            uniq = None
            try:
                from evdev import InputDevice
                dev = InputDevice(path)
                uniq = dev.uniq or None
                dev.close()
            except Exception:
                logger.debug("Could not read unique id for %s", path, exc_info=True)

            if uniq:
                previous_slot = next((
                    slot for slot in self._slots.values()
                    if not slot.is_connected and slot._last_device_uniq == uniq
                ), None)
                if previous_slot is not None:
                    logger.info("Reconnecting device %s to slot %s", uniq, previous_slot.slot_id)
                    if previous_slot.attach_device(path):
                        self._device_paths_in_use.add(path)
                        self._slot_paths[previous_slot.slot_id] = path
                        previous_slot.start_worker()
                    else:
                        self._device_paths_in_use.discard(path)
                    continue
            # Normal new device
            if path not in self._device_paths_in_use:
                self._try_assign_device(path)

    def _on_device_added(self, path: str):
        if path not in self._device_paths_in_use:
            self._try_assign_device(path)

    def _on_device_removed(self, path: str):
        for sid, slot in list(self._slots.items()):
            if slot.device_path == path:
                if not slot.detach_device():
                    logger.warning("Could not detach slot %s after device removal", sid)
                    continue
                self._device_paths_in_use.discard(path)
                self._slot_paths.pop(sid, None)
                self.device_disconnected_signal.emit(sid)
                logger.info(f"Removed controller at {path} from slot {sid}")

    def _on_slot_device_connected(self, device):
        """Forward slot device_connected signal for GUI updates."""
        # Find which slot this is
        for sid, slot in self._slots.items():
            if slot.device is device:
                self.device_connected_signal.emit(sid, slot.device_path or "")

    def _on_slot_device_disconnected(self):
        """Drop reservations when the worker detects a device loss itself."""
        sender = self.sender()
        slot_id = getattr(sender, "slot_id", None)
        if slot_id is None:
            return
        path = self._slot_paths.pop(slot_id, None)
        if path:
            self._device_paths_in_use.discard(path)

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
        if not slot.set_profile(copy.deepcopy(profile)):
            logger.warning("Could not apply profile to slot %s", slot.slot_id)
            return False

        if slot.attach_device(path):
            self._device_paths_in_use.add(path)
            self._slot_paths[slot.slot_id] = path
            slot.start_worker()
            logger.info(f"Assigned {path} to slot {slot.slot_id}")
            return True
        return False

    # ------------------------------------------------------------------
    # Slot management
    # ------------------------------------------------------------------
    def get_slot(self, slot_id: int) -> ControllerSlot | None:
        return self._slots.get(slot_id)

    def get_all_slots(self) -> list[ControllerSlot]:
        return list(self._slots.values())

    def get_connected_slots(self) -> list[ControllerSlot]:
        return [s for s in self._slots.values() if s.is_connected]

    def get_available_slot(self) -> ControllerSlot | None:
        for slot in self._slots.values():
            if not slot.is_connected:
                return slot
        return None

    def _get_available_slot(self) -> ControllerSlot | None:
        return self.get_available_slot()

    def get_slot_by_device_path(self, device_path: str) -> ControllerSlot | None:
        for slot in self._slots.values():
            if slot.device_path == device_path:
                return slot
        return None

    def connect_slot_to_device(self, slot_id: int, device_path: str) -> bool:
        slot = self.get_slot(slot_id)
        if not slot:
            return False

        if slot.is_connected and slot.device_path == device_path:
            return True

        if device_path in self._device_paths_in_use:
            other_slot = self.get_slot_by_device_path(device_path)
            if other_slot is not None and other_slot != slot:
                logger.warning("Device %s is already assigned to slot %s",
                               device_path, other_slot.slot_id)
                return False
            if other_slot is None:
                logger.warning("Dropping stale reservation for %s", device_path)
                self._device_paths_in_use.discard(device_path)

        if slot.is_connected:
            if slot.device_path == device_path:
                return True
            old_path = slot.device_path
            if not slot.detach_device():
                return False
            if old_path:
                self._device_paths_in_use.discard(old_path)
            self._slot_paths.pop(slot_id, None)

        profile = self._profile_manager.load_profile(
            self._profile_manager.get_current_profile_name() or "Default"
        )
        if not slot.set_profile(copy.deepcopy(profile)):
            return False

        if slot.attach_device(device_path):
            self._device_paths_in_use.add(device_path)
            self._slot_paths[slot_id] = device_path
            slot.start_worker()
            return True
        return False

    def disconnect_slot(self, slot_id: int):
        slot = self.get_slot(slot_id)
        if slot and slot.is_connected:
            if not slot.stop_worker():
                return False
            old_path = slot.device_path
            if not slot.detach_device():
                return False
            if old_path:
                self._device_paths_in_use.discard(old_path)
            self._slot_paths.pop(slot_id, None)
            self.device_disconnected_signal.emit(slot_id)
            return True
        return False

    def disconnect_all(self):
        for slot in list(self._slots.values()):
            if slot.is_connected:
                if not slot.stop_worker():
                    logger.error("Could not stop slot %s during disconnect_all", slot.slot_id)
                    continue
                old_path = slot.device_path
                if slot.detach_device():
                    if old_path:
                        self._device_paths_in_use.discard(old_path)
                    self._slot_paths.pop(slot.slot_id, None)
                    self.device_disconnected_signal.emit(slot.slot_id)

    def apply_profile_to_all(self, profile_name: str) -> bool:
        """Apply a named profile to every connected slot (auto-profile support).

        The profile is loaded fresh from disk so edits made in the GUI are
        picked up. Returns True if at least one slot got the profile.
        """
        if not profile_name:
            return False
        known_profiles = {name.casefold() for name in self._profile_manager.list_profiles()}
        if profile_name.casefold() not in known_profiles:
            logger.warning("apply_profile_to_all: profile '%s' does not exist", profile_name)
            return False
        profile = self._profile_manager.load_profile(profile_name, remember=False)
        if not profile:
            logger.warning(f"apply_profile_to_all: profile '{profile_name}' not found")
            return False

        applied = False
        for slot in self._slots.values():
            if slot.is_connected:
                if slot.set_profile(copy.deepcopy(profile)):
                    applied = True
                    logger.info(f"Slot {slot.slot_id} -> profile '{profile_name}'")
                else:
                    logger.warning("Slot %s rejected profile '%s' safely",
                                   slot.slot_id, profile_name)
        return applied

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
