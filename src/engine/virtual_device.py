from __future__ import annotations

import logging
import os
from collections.abc import Callable
from enum import Enum

from evdev import AbsInfo, UInput
from evdev import ecodes as e

from ..constants import MAX_AXIS_VALUE, MAX_TRIGGER_VALUE

logger = logging.getLogger(__name__)


class VirtualDeviceType(Enum):
    XBOX = "xbox"
    PS4 = "ps4"


class VirtualDevice:
    def __init__(self, device_type: VirtualDeviceType = VirtualDeviceType.XBOX, slot_id: int = 0):
        self._slot_id = slot_id
        logger.debug("Slot %s: initializing virtual device type=%s", slot_id, device_type.value)
        self.device_type = device_type
        self._uinput: UInput | None = None
        self._event_fd: int = -1
        self._event_fd_cached: bool = False
        self._event_observer: Callable[[int, int, int], None] | None = None
        self._caps, self._name, self._vendor, self._product, self._version = self._build_capabilities()

    @staticmethod
    def supported_button_codes(device_type: VirtualDeviceType) -> tuple[int, ...]:
        common = (
            e.BTN_GAMEPAD,
            e.BTN_TL,
            e.BTN_TR,
            e.BTN_TL2,
            e.BTN_TR2,
            e.BTN_THUMBL,
            e.BTN_THUMBR,
            e.BTN_START,
            e.BTN_SELECT,
            e.BTN_MODE,
            e.BTN_TOUCH,
            e.BTN_DPAD_UP,
            e.BTN_DPAD_DOWN,
            e.BTN_DPAD_LEFT,
            e.BTN_DPAD_RIGHT,
        )
        if device_type == VirtualDeviceType.XBOX:
            return common + (e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y)
        return common + (
            e.BTN_SOUTH,
            e.BTN_EAST,
            e.BTN_NORTH,
            e.BTN_WEST,
            e.BTN_TRIGGER_HAPPY1,
            e.BTN_TRIGGER_HAPPY2,
        )

    def _build_capabilities(self) -> tuple[dict[int, list], str, int, int, int]:
        logger.debug("Slot %s: building virtual capabilities type=%s", self._slot_id, self.device_type.value)
        caps = {
            e.EV_KEY: [],
            e.EV_ABS: [],
            e.EV_FF: [e.FF_RUMBLE],
        }

        if self.device_type == VirtualDeviceType.XBOX:
            caps[e.EV_KEY] = list(self.supported_button_codes(self.device_type))
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
            vendor, product, version = 0x045E, 0x028E, 0x0114

        else:  # PS4 / DS4
            caps[e.EV_KEY] = list(self.supported_button_codes(self.device_type))
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
            vendor, product, version = 0x054C, 0x09CC, 0x0100

        logger.debug("Slot %s: virtual identity %s (%04x:%04x)", self._slot_id, name, vendor, product)
        return caps, name, vendor, product, version

    def create(self) -> bool:
        if self.is_active():
            logger.debug("Slot %s: virtual device already active", self._slot_id)
            return True
        try:
            self._uinput = UInput(
                self._caps,
                name=self._name,
                vendor=self._vendor,
                product=self._product,
                version=self._version,
                bustype=0x03,
                phys=f"ds4linux-uinput-{self._slot_id}",
                max_effects=4,
            )
            logger.info("Slot %s: created virtual %s device", self._slot_id, self.device_type.value)
            self._event_fd = -1
            self._event_fd_cached = False
            return True
        except Exception as ex:
            logger.exception("Slot %s: failed to create virtual input device: %s", self._slot_id, ex)
            self._uinput = None
            return False

    def destroy(self):
        if self._uinput:
            try:
                self._uinput.close()
                logger.info("Slot %s: closed virtual device", self._slot_id)
            except Exception as ex:
                logger.warning(
                    "Slot %s: failed to close virtual device: %s", self._slot_id, ex, exc_info=True
                )
            finally:
                self._uinput = None
        if self._event_fd >= 0:
            try:
                os.close(self._event_fd)
            except OSError:
                logger.debug("Slot %s: cached virtual event fd close failed", self._slot_id, exc_info=True)
            self._event_fd = -1
            self._event_fd_cached = False

    def write_event(self, ev_type: int, code: int, value: int):
        if self._uinput:
            result = self._uinput.write(ev_type, code, value)
            if self._event_observer is not None:
                try:
                    self._event_observer(ev_type, code, value)
                except Exception:
                    logger.debug("Virtual event observer failed", exc_info=True)
            return result

    def set_event_observer(self, observer: Callable[[int, int, int], None] | None) -> None:
        """Observe successful writes from workers and asynchronous macros."""
        self._event_observer = observer

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
    def uinput(self):
        """The underlying evdev UInput device (None while inactive).

        Exposed for the worker's FF handshake loop: ``uinput.read()``
        yields EV_UINPUT events (UI_FF_UPLOAD / UI_FF_ERASE) written by
        the kernel when a game uploads or erases a force-feedback effect.
        """
        return self._uinput

    @property
    def event_device_path(self) -> str | None:
        """Path of the event device created by uinput (e.g. /dev/input/event21).

        Games write force-feedback (EV_FF) events to this node; the worker
        keeps a reader open on it to forward rumble to the physical pad.
        """
        if self._uinput is None:
            return None
        try:
            return self._uinput.device.path
        except Exception:
            logger.debug("event_device_path: uinput device has no path", exc_info=True)
            return None

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
                logger.debug("Slot %s: virtual event path is not available", self._slot_id)
                return -1
            fd = os.open(event_path, os.O_RDWR | os.O_NONBLOCK)
            logger.debug("Slot %s: opened virtual event node %s", self._slot_id, event_path)
            self._event_fd = fd
            self._event_fd_cached = True
            return fd
        except Exception as ex:
            logger.warning(
                "Slot %s: could not open virtual event node %s: %s",
                self._slot_id,
                locals().get("event_path"),
                ex,
            )
            return -1

    def close_event_fd(self):
        """Close the cached event_fd to prevent leaks."""
        if self._event_fd >= 0:
            try:
                os.close(self._event_fd)
            except OSError:
                logger.debug("Slot %s: cached virtual event fd close failed", self._slot_id, exc_info=True)
            self._event_fd = -1
            self._event_fd_cached = False

    def set_device_type(self, device_type: VirtualDeviceType):
        """Switch virtual identity transactionally, restoring the old one on failure."""
        if device_type == self.device_type:
            return True

        old_type = self.device_type
        old_config = (self._caps, self._name, self._vendor, self._product, self._version)
        was_active = self.is_active()
        logger.info(
            "Slot %s: switching virtual type %s -> %s", self._slot_id, old_type.value, device_type.value
        )

        if was_active:
            self.destroy()
        self.device_type = device_type
        self._caps, self._name, self._vendor, self._product, self._version = self._build_capabilities()

        if not was_active or self.create():
            logger.info("Slot %s: virtual type is now %s", self._slot_id, device_type.value)
            return True

        logger.error("Could not create virtual device as %s; restoring %s", device_type.value, old_type.value)
        self.device_type = old_type
        (self._caps, self._name, self._vendor, self._product, self._version) = old_config
        if not self.create():
            logger.critical("Could not recreate prior virtual device type %s", old_type.value)
        return False
