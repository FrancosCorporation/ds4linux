from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import os

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
        print(f"[VDEV] __init__ slot={slot_id} type={device_type.value}")
        self.device_type = device_type
        self._slot_id = slot_id
        self._uinput: Optional[UInput] = None
        self._event_fd: int = -1
        self._event_fd_cached: bool = False
        self._caps, self._name, self._vendor, self._product, self._version = \
            self._build_capabilities()

    def _build_capabilities(self) -> Tuple[Dict[int, list], str, int, int, int]:
        print(f"[VDEV] _build_capabilities type={self.device_type.value}")
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

        print(f"[VDEV] _build_capabilities done: name={name} vendor=0x{vendor:04x} product=0x{product:04x}")
        return caps, name, vendor, product, version

    def create(self) -> bool:
        print(f"[VDEV] create() called slot={self._slot_id} active={self.is_active()}")
        if self.is_active():
            print(f"[VDEV] create() skipped: already active (fd={self._uinput.fd})")
            return True
        try:
            print(f"[VDEV] Calling UInput() constructor...")
            print(f"[VDEV]   caps EV_KEY count: {len(self._caps[e.EV_KEY])}")
            print(f"[VDEV]   caps EV_ABS count: {len(self._caps[e.EV_ABS])}")
            print(f"[VDEV]   caps EV_FF count: {len(self._caps[e.EV_FF])}")
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
            print(f"[VDEV] UInput created successfully! fd={self._uinput.fd}")
            print(f"[VDEV]   device.path={getattr(self._uinput.device, 'path', 'N/A')}")
            self._event_fd = -1
            self._event_fd_cached = False
            return True
        except Exception as ex:
            print(f"[VDEV] FAILED to create UInput: {type(ex).__name__}: {ex}")
            import traceback
            traceback.print_exc()
            return False

    def destroy(self):
        print(f"[VDEV] destroy() called active={self.is_active()}")
        if self._uinput:
            try:
                print(f"[VDEV] Closing UInput fd={self._uinput.fd}")
                self._uinput.close()
                print(f"[VDEV] UInput closed")
            except Exception as ex:
                print(f"[VDEV] Error closing UInput: {ex}")
            finally:
                self._uinput = None
        if self._event_fd >= 0:
            try:
                os.close(self._event_fd)
                print(f"[VDEV] Closed cached event_fd={self._event_fd}")
            except Exception:
                pass
            self._event_fd = -1
            self._event_fd_cached = False

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
        The UInput fd is write-only; events from games go to the event device.
        Cached to prevent file descriptor leak."""
        if not self._uinput:
            return -1
        if self._event_fd_cached and self._event_fd >= 0:
            return self._event_fd
        try:
            event_path = self._uinput.device.path
            if not event_path:
                print(f"[VDEV] event_fd: device.path is None")
                return -1
            fd = os.open(event_path, os.O_RDWR | os.O_NONBLOCK)
            print(f"[VDEV] event_fd: opened {event_path} -> fd={fd}")
            self._event_fd = fd
            self._event_fd_cached = True
            return fd
        except Exception as ex:
            print(f"[VDEV] event_fd: FAILED to open {event_path}: {ex}")
            return -1

    def close_event_fd(self):
        """Close the cached event_fd to prevent leaks."""
        if self._event_fd >= 0:
            try:
                os.close(self._event_fd)
                print(f"[VDEV] event_fd: closed fd={self._event_fd}")
            except Exception:
                pass
            self._event_fd = -1
            self._event_fd_cached = False

    def set_device_type(self, device_type: VirtualDeviceType):
        """Update device type without destroying the virtual device."""
        if device_type == self.device_type:
            return

        old_type = self.device_type
        print(f"[VDEV] set_device_type: {old_type.value} -> {device_type.value}")

        self.device_type = device_type
        self._caps, self._name, self._vendor, self._product, self._version = \
            self._build_capabilities()

        if self.is_active():
            self.destroy()
            self.create()
            print(f"[VDEV] set_device_type: recreated device as {device_type.value}")
