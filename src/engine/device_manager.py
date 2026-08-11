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

        # Method 1: Search via sysfs hidraw devices
        hidraw_sysfs = Path("/sys/bus/hid/devices")
        if hidraw_sysfs.exists():
            for device_dir in hidraw_sysfs.iterdir():
                if not device_dir.is_dir():
                    continue
                uevent_file = device_dir / "uevent"
                if not uevent_file.exists():
                    continue
                try:
                    content = uevent_file.read_text()
                    if "HID_NAME=Wireless Controller" in content and \
                       "HID_UNIQ=f0:f7:9e:95:76:a0" in content:
                        # Found DS4, now find corresponding hidraw
                        hidraw_dir = device_dir / "hidraw"
                        if hidraw_dir.exists():
                            for hidraw_dev in hidraw_dir.iterdir():
                                if hidraw_dev.is_dir():
                                    # Get the hidraw device name (e.g., "hidraw3")
                                    hidraw_name = hidraw_dev.name
                                    hidraw_path = Path(f"/dev/{hidraw_name}")
                                    if hidraw_path.exists():
                                        try:
                                            return os.open(str(hidraw_path), os.O_RDWR)
                                        except (OSError, PermissionError):
                                            continue
                except (OSError, IOError):
                    continue

        # Method 2: Direct search in /dev/hidraw*
        for hidraw_dev in Path("/dev").glob("hidraw*"):
            if not hidraw_dev.is_char_device():
                continue
            try:
                # Get the sysfs path for this hidraw device
                sysfs_link = Path(f"/sys/class/hidraw/{hidraw_dev.name}/device")
                if sysfs_link.exists():
                    uevent_file = sysfs_link.resolve() / "uevent"
                    if uevent_file.exists():
                        content = uevent_file.read_text()
                        if "HID_NAME=Wireless Controller" in content and \
                           "HID_UNIQ=f0:f7:9e:95:76:a0" in content:
                            return os.open(str(hidraw_dev), os.O_RDWR)
            except (OSError, IOError):
                continue

        return None