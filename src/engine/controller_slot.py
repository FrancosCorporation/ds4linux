from __future__ import annotations

from typing import Optional
from enum import Enum
from pathlib import Path
import logging

from evdev import InputDevice
from PySide6.QtCore import QObject, Signal

from .led_controller import LEDController
from .virtual_device import VirtualDevice, VirtualDeviceType
from .input_mapper import InputMapper, ProfileConfig
from .worker_thread import WorkerThread
from .device_manager import DeviceManager
from ..constants import DS4_VID, DS4_PIDS

logger = logging.getLogger(__name__)


class SlotStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ControllerSlot(QObject):
    status_changed = Signal(str)
    device_connected = Signal(object)
    device_disconnected = Signal()
    log_message = Signal(str)
    battery_update = Signal(int)

    def __init__(self, slot_id: int, profile_manager=None, parent: QObject | None = None):
        super().__init__(parent)
        self._slot_id = slot_id
        self._status = SlotStatus.DISCONNECTED
        self._device: Optional[InputDevice] = None
        self._device_path: Optional[str] = None
        self._grabbed = False
        self._profile: Optional[ProfileConfig] = None
        self._profile_manager = profile_manager

        # Create a default profile
        from ..config.profile_manager import ProfileManager
        pm = profile_manager or ProfileManager()
        default_name = pm.get_current_profile_name() or "Default"
        self._profile = pm.load_profile(default_name)

        self._virtual_device = VirtualDevice(self._profile.device_type)
        self._input_mapper = InputMapper(self._profile)
        self._led_controller = LEDController()
        self._worker = WorkerThread()
        self._battery_level = 100

        self._setup_worker()

    @property
    def slot_id(self) -> int:
        return self._slot_id

    @property
    def status(self) -> SlotStatus:
        return self._status

    @status.setter
    def status(self, value: SlotStatus):
        self._status = value
        self.status_changed.emit(value.value)

    @property
    def profile(self) -> Optional[ProfileConfig]:
        return self._profile

    @profile.setter
    def profile(self, value: ProfileConfig):
        self._profile = value
        self._input_mapper.set_profile(value)
        self._virtual_device.set_device_type(value.device_type)
        if self._led_controller.is_available():
            self._led_controller.set_color(*value.led_color)
            self._led_controller.set_brightness(value.led_brightness)

    @property
    def device(self) -> Optional[InputDevice]:
        return self._device

    @property
    def device_path(self) -> Optional[str]:
        return self._device_path

    @property
    def is_connected(self) -> bool:
        return self._device is not None and self._grabbed

    @property
    def battery_level(self) -> int:
        return self._battery_level

    def set_profile(self, profile: ProfileConfig):
        self.profile = profile

    # ------------------------------------------------------------------
    # Dynamic attach / detach
    # ------------------------------------------------------------------
    def attach_device(self, device_path: str) -> bool:
        if self.is_connected:
            return True

        self.status = SlotStatus.CONNECTING
        try:
            self._device = InputDevice(device_path)
        except (OSError, PermissionError) as e:
            logger.error(f"Cannot open {device_path}: {e}")
            self.status = SlotStatus.ERROR
            return False

        try:
            self._device.grab()  # exclusive access
            self._grabbed = True
        except OSError as e:
            logger.warning(f"grab() failed for {device_path}: {e}")
            self.status = SlotStatus.ERROR
            return False

        # Create virtual device with the profile's device type
        if not self._virtual_device.is_active():
            self._virtual_device.create()

        self._device_path = device_path
        self.status = SlotStatus.CONNECTED
        self._battery_level = self._read_battery()

        # Set LED path
        led_path = DeviceManager.get_led_path(self._device)
        if led_path:
            self._led_controller.set_led_path(led_path)
            if self._profile:
                self._led_controller.set_color(*self._profile.led_color)
                self._led_controller.set_brightness(self._profile.led_brightness)

        self.device_connected.emit(self._device)
        self.log_message.emit(f"Slot {self._slot_id}: DS4 connected at {device_path}")
        return True

    def detach_device(self):
        if self._device:
            try:
                self._device.ungrab()
            except OSError:
                pass
            self._grabbed = False

        was_connected = self.is_connected
        self._device = None
        self._device_path = None
        self.status = SlotStatus.DISCONNECTED

        if was_connected:
            self.device_disconnected.emit()
            self.log_message.emit(f"Slot {self._slot_id}: DS4 disconnected")

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------
    def _setup_worker(self):
        self._worker.set_input_mapper(self._input_mapper)
        self._worker.set_virtual_device(self._virtual_device)
        self._worker.set_led_controller(self._led_controller)
        self._worker.device_connected.connect(self._on_worker_connected)
        self._worker.device_disconnected.connect(self._on_worker_disconnected)
        self._worker.log_message.connect(self.log_message.emit)
        self._worker.battery_update.connect(self.battery_update.emit)

    def _on_worker_connected(self, device):
        pass

    def _on_worker_disconnected(self):
        pass

    def start_worker(self):
        if self.is_connected and self._input_mapper and not self._worker.isRunning():
            self._worker.set_device(self._device)
            self._worker.start()

    def stop_worker(self):
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)

    # ------------------------------------------------------------------
    # Battery helper
    # ------------------------------------------------------------------
    def _read_battery(self) -> int:
        if not self._device:
            return 0
        try:
            report = self._device.device.read_feature_report(0x02, 17)
            if report and len(report) >= 2:
                return min(100, round(report[1] / 255 * 100))
        except Exception:
            pass
        return 100

    def refresh_battery(self):
        if self.is_connected:
            level = self._read_battery()
            if level != self._battery_level:
                self._battery_level = level
                self.battery_update.emit(level)

    def get_led_color(self) -> tuple:
        if self._profile:
            return self._profile.led_color
        return (0, 0, 255)

    def cleanup(self):
        self.stop_worker()
        self.detach_device()