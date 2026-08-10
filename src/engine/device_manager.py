"""Device helper utilities (legacy DeviceManager simplified)."""

from pathlib import Path
from typing import Optional

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