"""Battery level discovery for DS4 controllers.

Two sources, tried in order:

1. **Kernel power supply**: ``/sys/class/hidraw/<dev>/device/power_supply/*/
   capacity`` — created by hid-sony/hid-playstation for the controller.
   Works in both evdev and HIDRAW modes and needs no report parsing.
2. **DS4 status byte** from an input report (hid-playstation layout:
   capacity 0..11 in bits 0..3 of ``status[0]``) — available to the HIDRAW
   reader, which sees reports every frame anyway.

The previous implementation called ``InputDevice.device.read_feature_report``
which does not exist on evdev devices: every read raised ``AttributeError``
and the GUI battery column never updated from its initial ``--``.
"""

from __future__ import annotations

from pathlib import Path

_SYSFS_HIDRAW = Path("/sys/class/hidraw")
_STATUS_CAPACITY_LEVELS = 11  # DS4 status byte: capacity 0..11 (11 = full)


def battery_percent_from_sysfs(hidraw_path: str | None) -> int:
    """Battery 0-100 from the kernel power supply; 0 means unknown."""
    if not hidraw_path:
        return 0
    try:
        psy_dir = (
            _SYSFS_HIDRAW / Path(hidraw_path).name / "device" / "power_supply"
        )
        for entry in sorted(psy_dir.iterdir()):
            capacity = entry / "capacity"
            if capacity.is_file():
                return max(0, min(100, int(capacity.read_text().strip())))
    except (OSError, ValueError):
        pass
    return 0


def battery_percent_from_status(status0: int) -> int:
    """Battery 0-100 from a DS4 status byte (capacity 0..11, saturated)."""
    capacity = status0 & 0x0F
    if capacity > _STATUS_CAPACITY_LEVELS:
        capacity = _STATUS_CAPACITY_LEVELS
    return round(capacity * 100 / _STATUS_CAPACITY_LEVELS)
