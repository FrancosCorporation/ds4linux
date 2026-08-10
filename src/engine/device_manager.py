import evdev
from evdev import InputDevice, ecodes
from pathlib import Path
from typing import Optional, List, Callable
import logging

from ..constants import (
    DS4_VID, DS4_PID, DS4_PID_DONGLE,
    UINPUT_PATH, SYS_LEDS_BASE
)

logger = logging.getLogger(__name__)


class DeviceManager:
    def __init__(self):
        self._device: Optional[InputDevice] = None
        self._device_path: Optional[str] = None
        self._grabbed = False
        self._on_device_found: Optional[Callable[[InputDevice], None]] = None
        self._on_device_lost: Optional[Callable[[], None]] = None

    def set_callbacks(self, on_found: Callable[[InputDevice], None], on_lost: Callable[[], None]):
        self._on_device_found = on_found
        self._on_device_lost = on_lost

    def find_ds4(self) -> Optional[InputDevice]:
        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                if dev.info.vendor == DS4_VID and dev.info.product in (DS4_PID, DS4_PID_DONGLE):
                    logger.info(f"Found DS4 at {path}: {dev.name}")
                    return dev
            except (OSError, PermissionError) as e:
                logger.debug(f"Cannot access {path}: {e}")
        return None

    def open_device(self, path: str) -> bool:
        try:
            self._device = InputDevice(path)
            self._device.grab()
            self._grabbed = True
            self._device_path = path
            logger.info(f"Grabbed DS4 at {path}")
            if self._on_device_found:
                self._on_device_found(self._device)
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to grab device {path}: {e}")
            return False

    def close_device(self):
        if self._device and self._grabbed:
            try:
                self._device.ungrab()
            except OSError:
                pass
            self._grabbed = False
        self._device = None
        self._device_path = None
        if self._on_device_lost:
            self._on_device_lost()

    def get_device(self) -> Optional[InputDevice]:
        return self._device

    def is_grabbed(self) -> bool:
        return self._grabbed

    def get_device_path(self) -> Optional[str]:
        return self._device_path

    def list_ds4_devices(self) -> List[InputDevice]:
        devices = []
        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                if dev.info.vendor == DS4_VID and dev.info.product in (DS4_PID, DS4_PID_DONGLE):
                    devices.append(dev)
            except (OSError, PermissionError):
                pass
        return devices

    @staticmethod
    def get_led_path(device: InputDevice) -> Optional[Path]:
        name = device.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        led_dir = SYS_LEDS_BASE / f"{name}::kbd_backlight"
        if led_dir.exists():
            return led_dir
        for led in SYS_LEDS_BASE.glob(f"*{name}*"):
            if led.is_dir():
                return led
        return None