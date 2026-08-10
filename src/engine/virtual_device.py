from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import struct
import fcntl
import os
import logging

from evdev import UInput, AbsInfo, ecodes as e

from ..constants import (
    UINPUT_PATH,
    XboxBtn, PS4Btn, XboxAbs, DS4Abs,
    MAX_AXIS_VALUE, MAX_TRIGGER_VALUE,
    VIRTUAL_DEVICE_TYPES
)

logger = logging.getLogger(__name__)


class VirtualDeviceType(Enum):
    XBOX = "xbox"
    PS4 = "ps4"


class VirtualDevice:
    UI_DEV_CREATE = 0x5501
    UI_DEV_DESTROY = 0x5502
    UI_SET_EVBIT = 0x40045564
    UI_SET_KEYBIT = 0x40045565
    UI_SET_ABSBIT = 0x40045567

    def __init__(self, device_type: VirtualDeviceType = VirtualDeviceType.XBOX):
        self.device_type = device_type
        self._uinput: Optional[UInput] = None
        self._fd: Optional[int] = None
        self._capabilities = self._build_capabilities()

    def _build_capabilities(self) -> Dict[int, List[Tuple]]:
        caps = {
            e.EV_KEY: [],
            e.EV_ABS: [],
        }
        if self.device_type == VirtualDeviceType.XBOX:
            caps[e.EV_KEY].extend([
                (e.BTN_A, 1), (e.BTN_B, 1), (e.BTN_X, 1), (e.BTN_Y, 1),
                (e.BTN_TL, 1), (e.BTN_TR, 1),
                (e.BTN_THUMBL, 1), (e.BTN_THUMBR, 1),
                (e.BTN_START, 1), (e.BTN_SELECT, 1),
                (e.BTN_MODE, 1),
                (e.BTN_DPAD_UP, 1), (e.BTN_DPAD_DOWN, 1),
                (e.BTN_DPAD_LEFT, 1), (e.BTN_DPAD_RIGHT, 1),
            ])
            caps[e.EV_ABS].extend([
                (e.ABS_X, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Y, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RX, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RY, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Z, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_RZ, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)),
                (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
            ])
            name = "Xbox 360 Controller (DS4Linux)"
            vendor, product, version = 0x045e, 0x028e, 0x0110
        else:
            caps[e.EV_KEY].extend([
                (e.BTN_SOUTH, 1), (e.BTN_EAST, 1), (e.BTN_NORTH, 1), (e.BTN_WEST, 1),
                (e.BTN_TL, 1), (e.BTN_TR, 1),
                (e.BTN_THUMBL, 1), (e.BTN_THUMBR, 1),
                (e.BTN_START, 1), (e.BTN_SELECT, 1),
                (e.BTN_MODE, 1),
                (e.BTN_DPAD_UP, 1), (e.BTN_DPAD_DOWN, 1),
                (e.BTN_DPAD_LEFT, 1), (e.BTN_DPAD_RIGHT, 1),
                (e.BTN_TRIGGER_HAPPY1, 1), (e.BTN_TRIGGER_HAPPY2, 1),
            ])
            caps[e.EV_ABS].extend([
                (e.ABS_X, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Y, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RX, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_RY, AbsInfo(0, -MAX_AXIS_VALUE, MAX_AXIS_VALUE, 0, 0, 0)),
                (e.ABS_Z, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_RZ, AbsInfo(0, 0, MAX_TRIGGER_VALUE, 0, 0, 0)),
                (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)),
                (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
            ])
            name = "Wireless Controller (DS4Linux)"
            vendor, product, version = 0x054c, 0x09cc, 0x0100

        return {"caps": caps, "name": name, "vendor": vendor, "product": product, "version": version}

    def create(self) -> bool:
        try:
            caps = self._capabilities["caps"]
            self._uinput = UInput(
                caps,
                name=self._capabilities["name"],
                vendor=self._capabilities["vendor"],
                product=self._capabilities["product"],
                version=self._capabilities["version"],
            )
            logger.info(f"Created virtual device: {self._capabilities['name']}")
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

    def set_device_type(self, device_type: VirtualDeviceType):
        if device_type != self.device_type:
            was_active = self.is_active()
            self.destroy()
            self.device_type = device_type
            self._capabilities = self._build_capabilities()
            if was_active:
                self.create()