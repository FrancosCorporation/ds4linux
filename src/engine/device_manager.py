"""Device helper utilities (legacy DeviceManager simplified)."""

from pathlib import Path
from typing import Optional
import os

from evdev import InputDevice


class DeviceManager:
    """
    Legacy single-device manager kept for backward compatibility.
    New code should use :class:`~src.engine.multi_device_manager.MultiDeviceManager`
    + :class:`~src.engine.device_monitor.DeviceMonitor` for dynamic hot-plug.
    """

    def __init__(self):
        self._device: Optional[InputDevice] = None
        self._grabbed = False

    @staticmethod
    def get_led_path(device: InputDevice) -> Optional[Path]:
        from ..constants import SYS_LEDS_BASE

        name = device.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        led_dir = SYS_LEDS_BASE / f"{name}::kbd_backlight"
        if led_dir.exists():
            return led_dir

        for led in SYS_LEDS_BASE.glob(f"*{name}*"):
            if led.is_dir():
                return led
        return None

    @staticmethod
    def get_hid_device() -> Optional[int]:
        """
        Returns the HID device file descriptor (int) for the currently
        connected DS4 controller (hidraw3), or None if no DS4 controller
        is available.
        """
        from ..constants import HIDRAW_BASE
        import glob

        # Check for DS4 via HIDRAW path — there should be only one DS4 HIDRAW device
        for p in glob.glob(f"{HIDRAW_BASE}*/device/uevent"):
            try:
                with open(p, "r") as f:
                    content = f.read()
                if "HID_NAME=Wireless Controller" in content and \
                   "HID_UNIQ=f0:f7:9e:95:76:a0" in content:
                    hidraw_path = Path(p).parent
                    hidraw_fd = os.open(str(hidraw_path), os.O_RDWR)
                    return hidraw_fd
            except (OSError, IOError, IndexError):
                continue
        return None