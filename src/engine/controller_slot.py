from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
from pathlib import Path
import logging

from evdev import InputDevice
from PySide6.QtCore import QObject, Signal

from .device_manager import DeviceManager
from .led_controller import LEDController
from .virtual_device import VirtualDevice, VirtualDeviceType
from .input_mapper import InputMapper, ProfileConfig
from .worker_thread import WorkerThread
from ..constants import DS4_VID, DS4_PID, DS4_PID_DONGLE

logger = logging.getLogger(__name__)


class SlotStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ControllerSlot(QObject):
    slot_id: int
    status_changed = Signal(str)
    device_connected = Signal(object)
    device_disconnected = Signal()
    log_message = Signal(str)
    battery_update = Signal(int)

    def __post_init__(self):
        super().__init__()
        self._status = SlotStatus.DISCONNECTED
        self._device: Optional[InputDevice] = None
        self._device_path: Optional[str] = None
        self._profile: Optional[ProfileConfig] = None
        
        self._device_manager = DeviceManager()
        self._virtual_device = VirtualDevice(VirtualDeviceType.XBOX)
        self._input_mapper = InputMapper()
        self._led_controller = LEDController()
        self._worker = WorkerThread()
        
        self._setup_worker()
        self._device_manager.set_callbacks(
            on_found=self._on_device_found,
            on_lost=self._on_device_lost
        )

    def _setup_worker(self):
        self._worker.set_virtual_device(self._virtual_device)
        self._worker.set_input_mapper(self._input_mapper)
        self._worker.set_led_controller(self._led_controller)
        self._worker.device_connected.connect(self._on_worker_device_connected)
        self._worker.device_disconnected.connect(self._on_worker_device_disconnected)
        self._worker.log_message.connect(self.log_message.emit)
        self._worker.battery_update.connect(self.battery_update.emit)

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
        if self._led_controller and self._led_controller.is_available():
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
        return self._device is not None and self._device_manager.is_grabbed()

    def set_profile(self, profile: ProfileConfig):
        self.profile = profile

    def connect(self, device_path: str) -> bool:
        if self.is_connected:
            return True
        self.status = SlotStatus.CONNECTING
        self._device_path = device_path
        success = self._device_manager.open_device(device_path)
        if success:
            self._device = self._device_manager.get_device()
            self.status = SlotStatus.CONNECTED
            return True
        else:
            self.status = SlotStatus.ERROR
            return False

    def disconnect(self):
        if self.is_connected:
            self._device_manager.close_device()
            self._device = None
            self._device_path = None
            self.status = SlotStatus.DISCONNECTED

    def auto_connect(self) -> bool:
        device = self._device_manager.find_ds4()
        if device:
            return self.connect(device.path)
        return False

    def _on_device_found(self, device: InputDevice):
        self._device = device
        led_path = DeviceManager.get_led_path(device)
        if led_path:
            self._led_controller.set_led_path(led_path)
        self.device_connected.emit(device)
        self.log_message.emit(f"Slot {self.slot_id}: DS4 connected at {device.path}")

    def _on_device_lost(self):
        self._device = None
        self.device_disconnected.emit()
        self.log_message.emit(f"Slot {self.slot_id}: DS4 disconnected")
        if self.status == SlotStatus.CONNECTED:
            self.status = SlotStatus.DISCONNECTED

    def _on_worker_device_connected(self, device):
        pass

    def _on_worker_device_disconnected(self):
        pass

    def start_worker(self):
        if self.is_connected and not self._worker.isRunning():
            self._worker.start()

    def stop_worker(self):
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)

    def cleanup(self):
        self.stop_worker()
        self.disconnect()