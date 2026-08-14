from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

from evdev import UInput, AbsInfo, ecodes as e

from ..constants import (
    MAX_AXIS_VALUE, MAX_TRIGGER_VALUE
)

logger = logging.getLogger(__name__)

INPUT_PROP_GAMEPAD = 0x05


class VirtualDeviceType(Enum):
    XBOX = "xbox"
    PS4 = "ps4"


class VirtualDevice:
    def __init__(self, device_type: VirtualDeviceType = VirtualDeviceType.XBOX, slot_id: int = 0):
        self.device_type = device_type
        self._slot_id = slot_id
        self._uinput: Optional[UInput] = None
        self._caps, self._name, self._vendor, self._product, self._version = \
            self._build_capabilities()

    def _build_capabilities(self) -> Tuple[Dict[int, list], str, int, int, int]:
        caps = {
            e.EV_KEY: [],
            e.EV_ABS: [],
            e.EV_FF: [e.FF_RUMBLE],
        }

        if self.device_type == VirtualDeviceType.XBOX:
            caps[e.EV_KEY] = [
                e.BTN_GAMEPAD,
                e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y,
                e.BTN_TL, e.BTN_TR,
                e.BTN_THUMBL, e.BTN_THUMBR,
                e.BTN_START, e.BTN_SELECT,
                e.BTN_MODE,
                e.BTN_DPAD_UP, e.BTN_DPAD_DOWN,
                e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT,
            ]
            caps[e.EV_ABS] = [
                (e.ABS_X, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Y, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RX, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RY, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Z, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_RZ, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)),
                (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
            ]
            name = "Microsoft X-Box 360 pad"
            vendor, product, version = 0x045e, 0x028e, 0x0114

        else:  # PS4 / DS4
            caps[e.EV_KEY] = [
                e.BTN_GAMEPAD,
                e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST,
                e.BTN_TL, e.BTN_TR,
                e.BTN_THUMBL, e.BTN_THUMBR,
                e.BTN_START, e.BTN_SELECT,
                e.BTN_MODE,
                e.BTN_DPAD_UP, e.BTN_DPAD_DOWN,
                e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT,
                e.BTN_TRIGGER_HAPPY1, e.BTN_TRIGGER_HAPPY2,
            ]
            caps[e.EV_ABS] = [
                (e.ABS_X, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Y, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RX, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RY, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Z, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_RZ, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)),
                (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
            ]
            name = "Sony Interactive Entertainment Wireless Controller"
            vendor, product, version = 0x054c, 0x09cc, 0x0100

        return caps, name, vendor, product, version

    def create(self) -> bool:
        try:
            self._uinput = UInput(
                self._caps,
                name=self._name,
                vendor=self._vendor,
                product=self._product,
                version=self._version,
                bustype=0x03,
                phys=f"ds4linux-uinput-{self._slot_id}",
                input_props=[INPUT_PROP_GAMEPAD],
                max_effects=4,
            )
            logger.info(f"Created virtual device: {self._name} (bustype=USB, phys=ds4linux-uinput-{self._slot_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to create virtual device: {e}")
            return False

    def destroy(self):
        if self._uinput:
            try:
                self._uinput.close()
            except Exception:
                pass
            self._uinput = None

    def write_event(self, ev_type: int, code: int, value: int):
        if self._uinput:
            self._uinput.write(ev_type, code, value)

    def sync(self):
        if self._uinput:
            self._uinput.syn()

    def emit_click(self, btn_code: int):
        if self._uinput:
            self._uinput.write(e.EV_KEY, btn_code, 1)
            self._uinput.write(e.EV_KEY, btn_code, 0)
            self._uinput.syn()

    def emit_axis(self, axis_code: int, value: int):
        if self._uinput:
            self._uinput.write(e.EV_ABS, axis_code, value)
            self._uinput.syn()

    def is_active(self) -> bool:
        return self._uinput is not None

    @property
    def uinput_fd(self) -> int:
        if self._uinput:
            return self._uinput.fd
        return -1

    @property
    def event_fd(self) -> int:
        """Return the event device fd for reading game output events (rumble, etc).
        The UInput fd is write-only; events from games go to the event device."""
        if self._uinput and self._uinput.device:
            try:
                event_path = self._uinput.device.path
                import os
                return os.open(event_path, os.O_RDWR | os.O_NONBLOCK)
            except Exception:
                pass
        return -1

    def set_device_type(self, device_type: VirtualDeviceType):
        """Update device type without destroying the virtual device."""
        if device_type == self.device_type:
            return

        # Store old device type for logging
        old_type = self.device_type

        # Update type and capabilities
        self.device_type = device_type
        self._caps, self._name, self._vendor, self._product, self._version = \
            self._build_capabilities()

        # If device was active, destroy and recreate with new caps
        if self.is_active():
            was_active = True
            self.destroy()
            if was_active:
                self.create()
                logger.info(f"Updated virtual device from {old_type.value} to {device_type.value}")
