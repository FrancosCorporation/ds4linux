from __future__ import annotations

import logging
from enum import Enum

from evdev import InputDevice
from PySide6.QtCore import QObject, QTimer, Signal

from .battery import battery_percent_from_sysfs
from .device_manager import DeviceManager
from .input_mapper import InputMapper, ProfileConfig
from .led_controller import LEDController
from .macro_engine import MacroEngine
from .motion_source import (
    DS4MotionProvider,
    DS4MotionReader,
    detect_hid_transport,
    read_hid_uniq,
)
from .virtual_device import VirtualDevice
from .worker_thread import WorkerThread

logger = logging.getLogger(__name__)


class SlotStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ControllerSlot(QObject):
    status_changed = Signal(str)
    device_connected = Signal(object)
    device_disconnected = Signal()
    log_message = Signal(str)
    battery_update = Signal(int)

    def __init__(self, slot_id: int, profile_manager=None, parent: QObject | None = None):
        super().__init__(parent)
        self._slot_id = slot_id
        self._status = SlotStatus.DISCONNECTED
        self._device: InputDevice | None = None
        self._device_path: str | None = None
        self._last_device_uniq: str | None = None
        self._grabbed = False
        self._profile: ProfileConfig | None = None
        self._profile_manager = profile_manager

        from ..config.profile_manager import ProfileManager

        pm = profile_manager or ProfileManager()
        default_name = pm.get_current_profile_name() or "Default"
        self._profile = pm.load_profile(default_name)

        self._virtual_device = VirtualDevice(self._profile.device_type, slot_id=self._slot_id)
        self._macro_engine = MacroEngine(self._virtual_device)
        self._input_mapper = InputMapper(self._profile, macro_engine=self._macro_engine)
        self._led_controller = LEDController()
        self._worker = WorkerThread()
        self._battery_level: int | None = None
        self._motion_provider = DS4MotionProvider()
        self._motion_reader: DS4MotionReader | None = None
        self._dsu_rumble = [0, 0]  # [strong, weak] set by DSU clients

        self._setup_worker()

    @property
    def slot_id(self) -> int:
        return self._slot_id

    @property
    def status(self) -> SlotStatus:
        return self._status

    @status.setter
    def status(self, value: SlotStatus):
        self._status = value
        self.status_changed.emit(value.value)

    @property
    def profile(self) -> ProfileConfig | None:
        return self._profile

    @profile.setter
    def profile(self, value: ProfileConfig):
        self.apply_profile(value)

    def apply_profile(self, value: ProfileConfig) -> bool:
        was_running = self._worker.isRunning()
        if not self._macro_engine.pause_and_cancel(timeout=1.0):
            logger.warning("Slot %s: macro output did not stop; preserving current profile", self._slot_id)
            self._macro_engine.resume()
            return False
        if was_running:
            self._worker.stop(intentional=True)
            if self._worker.isRunning():
                self._worker.wait(3000)
            if self._worker.isRunning():
                logger.warning("Slot %s: worker did not exit; preserving current profile", self._slot_id)
                self._macro_engine.resume()
                return False

        applied = False
        try:
            if self._virtual_device.is_active():
                self._worker.release_stuck_buttons(
                    self._input_mapper,
                    self._virtual_device.write_event,
                    self._virtual_device.sync,
                )

            applied = self._virtual_device.set_device_type(value.device_type)
            if applied and self.is_connected and not self._virtual_device.is_active():
                applied = self._virtual_device.create()
            if not applied:
                logger.error("Slot %s: virtual device type switch failed; keeping old profile", self._slot_id)
                self._virtual_device.set_device_type(self._profile.device_type)
            else:
                self._profile = value
                self._input_mapper.set_profile(value)

            # Reconnect worker to new virtual device only after it has exited.
            self._worker.set_virtual_device(self._virtual_device)

            if applied and self._led_controller.is_available():
                self._led_controller.set_color(*value.led_color)
                self._led_controller.set_brightness(value.led_brightness)
        finally:
            self._macro_engine.resume()

        if was_running and self.is_connected:
            self.start_worker()
        return applied

    @property
    def device(self) -> InputDevice | None:
        return self._device

    @property
    def device_path(self) -> str | None:
        return self._device_path

    @property
    def is_connected(self) -> bool:
        return self._device is not None

    @property
    def input_grabbed(self) -> bool:
        """Whether evdev exclusively diverts this physical device's events."""
        return self._grabbed

    @property
    def battery_level(self) -> int | None:
        return self._battery_level

    @property
    def led_controller(self) -> LEDController:
        return self._led_controller

    @property
    def worker(self) -> WorkerThread:
        """The QThread reading this controller (public, read-only)."""
        return self._worker

    @property
    def physical_device(self):
        """The evdev InputDevice for the physical DS4 (None when detached)."""
        return self._device

    @property
    def virtual_device(self) -> VirtualDevice:
        """The uinput-backed virtual controller for this slot."""
        return self._virtual_device

    @property
    def motion_provider(self) -> DS4MotionProvider:
        """Latest motion sample for this slot (feeds the DSU server)."""
        return self._motion_provider

    def set_external_rumble(self, motor: int, intensity: int) -> None:
        """Rumble requested by a DSU (CemuHook) client.

        motor 0 = strong/left motor, motor 1 = weak/right motor,
        intensity 0..255. Routed through the HID output report so it works
        whether or not the evdev force-feedback path is in use.
        """
        if motor not in (0, 1):
            return
        value = max(0, min(255, int(intensity))) * 257  # 0..255 -> 0..65535
        self._dsu_rumble[motor] = value
        self._led_controller.set_rumble(self._dsu_rumble[0], self._dsu_rumble[1])

    def _start_motion_reader(self, hidraw_path: str) -> None:
        self._stop_motion_reader()
        transport = detect_hid_transport(hidraw_path)
        self._motion_provider.connection_type = 2 if transport == "bt" else 1
        uniq = read_hid_uniq(hidraw_path)
        if uniq:
            try:
                mac = bytes.fromhex(uniq.replace(":", ""))
                if len(mac) >= 6:
                    self._motion_provider.mac = mac[:6]
            except ValueError:
                pass
        self._motion_reader = DS4MotionReader(hidraw_path, self._motion_provider)
        self._motion_reader.start()

    def _stop_motion_reader(self) -> None:
        if self._motion_reader is not None:
            self._motion_reader.stop()
            self._motion_reader = None

    def set_profile(self, profile: ProfileConfig):
        return self.apply_profile(profile)

    def attach_device(self, device_path: str) -> bool:
        if self.is_connected:
            return True

        self.status = SlotStatus.CONNECTING
        try:
            self._device = InputDevice(device_path)
        except (OSError, PermissionError) as e:
            logger.error("Slot %s: cannot open %s: %s", self._slot_id, device_path, e)
            self.status = SlotStatus.ERROR
            return False

        try:
            self._last_device_uniq = self._device.uniq or None
        except Exception:
            self._last_device_uniq = None
            logger.debug("Could not read unique id from %s", device_path, exc_info=True)
        try:
            name = self._device.name
        except Exception:
            name = "unknown"
        logger.info("Slot %s: physical controller %s (%s)", self._slot_id, name, device_path)

        # Attempt exclusive grab with proper error handling
        try:
            self._device.grab()
            self._grabbed = True
            logger.debug("Slot %s: exclusive grab acquired for %s", self._slot_id, device_path)
        except OSError as e:
            message = (
                f"Slot {self._slot_id}: exclusive evdev grab failed for {device_path}: {e}. "
                "Disable Steam Input, ds4drv, or another controller service, then reconnect. "
                "The app will not expose duplicate physical and virtual game input."
            )
            logger.warning(message)
            self.log_message.emit(message)
            self._grabbed = False
            self._release_physical_device()
            self.status = SlotStatus.ERROR
            return False

        if not self._virtual_device.is_active():
            if self._virtual_device.create():
                logger.info("Slot %s: virtual device is ready", self._slot_id)
            else:
                logger.error("Slot %s: virtual device creation failed", self._slot_id)
                self._release_physical_device()
                self.status = SlotStatus.ERROR
                return False

        self._device_path = device_path
        self.status = SlotStatus.CONNECTED
        self._battery_level = self._read_battery()
        logger.info("Slot %s: connected; input worker will start", self._slot_id)

        # Discover LED path from sysfs
        try:
            led_path = LEDController.find_ds4_led(device_path)
        except Exception:
            led_path = None
            logger.warning("Could not discover LED for %s", device_path, exc_info=True)
        if led_path:
            self._led_controller.set_led_path(led_path)
            logger.info(f"Found LED path: {led_path}")

        # Find specific HID device for this controller
        if self._device:
            try:
                hid_path = DeviceManager.get_hid_device_path(self._device)
            except Exception:
                hid_path = None
                logger.warning("Could not discover HID interface for %s", device_path, exc_info=True)
            if hid_path:
                self._led_controller.set_hid_device(hid_path)
                logger.info(f"Found HID device: {hid_path}")
                try:
                    self._start_motion_reader(str(hid_path))
                except Exception:
                    logger.warning("Could not start motion reader for %s", hid_path, exc_info=True)

        # Apply LED settings from profile
        try:
            self._led_controller.set_color(*self._profile.led_color)
            self._led_controller.set_brightness(self._profile.led_brightness)
        except Exception:
            logger.warning("Could not apply initial LED settings", exc_info=True)

        self.device_connected.emit(self._device)
        self.log_message.emit(f"Slot {self._slot_id}: DS4 connected at {device_path}")
        return True

    def detach_device(self) -> bool:
        self._stop_motion_reader()
        if not self._device:
            return True
        if not self.stop_worker():
            logger.error(
                "Slot %s: keeping device resources open because worker is still active", self._slot_id
            )
            return False
        was_connected = self.is_connected
        self._release_physical_device()
        self._battery_level = None
        self.status = SlotStatus.DISCONNECTED

        # Destroy virtual device to release event device and close cached fds
        if self._virtual_device.is_active():
            self._virtual_device.destroy()
            logger.info("Slot %s: virtual device destroyed", self._slot_id)

        if was_connected:
            self.device_disconnected.emit()
            self.log_message.emit(f"Slot {self._slot_id}: DS4 disconnected")
        return True

    def _release_physical_device(self):
        """Ungrab and close the physical fd, including failed attach paths."""
        device = self._device
        if device is None:
            self._device_path = None
            self._grabbed = False
            return
        if self._grabbed:
            try:
                device.ungrab()
            except OSError:
                pass
            self._grabbed = False
            logger.debug("Slot %s: released exclusive grab", self._slot_id)
        # Close regardless of grab: when grab() failed the fd stayed open
        # until GC (evdev __del__), leaking one descriptor per reattach.
        try:
            device.close()
        except OSError:
            pass
        self._device = None
        self._device_path = None

    def _setup_worker(self):
        self._worker.set_input_mapper(self._input_mapper)
        self._worker.set_virtual_device(self._virtual_device)
        self._worker.set_led_controller(self._led_controller)
        self._worker.device_connected.connect(self._on_worker_connected)
        self._worker.device_disconnected.connect(self._on_worker_disconnected)
        self._worker.log_message.connect(self.log_message.emit)
        self._worker.battery_update.connect(self._on_worker_battery_update)

    def _on_worker_connected(self, device):
        pass

    def _on_worker_battery_update(self, level: int):
        if 0 <= level <= 100:
            self._battery_level = level
            self.battery_update.emit(level)

    def _on_worker_disconnected(self):
        if self.is_connected:
            self.detach_device()

    def start_worker(self):
        if self.is_connected and self._input_mapper and not self._worker.isRunning():
            self._macro_engine.resume()
            logger.info("Slot %s: starting worker loop", self._slot_id)
            if self._profile is not None:
                self._worker.set_select_timeout(self._profile.poll_rate_ms / 1000.0)
            self._worker.set_device(self._device)
            self._worker.set_device_grabbed(self._grabbed)
            self._worker.start()
            logger.info("Slot %s: input worker started", self._slot_id)
        elif self._worker.isRunning():
            logger.debug("Slot %s: input worker is already running", self._slot_id)

    def stop_worker(self) -> bool:
        if not self._macro_engine.pause_and_cancel(timeout=1.0):
            logger.error("Slot %s: macro output did not stop", self._slot_id)
            return False
        if self._worker.isRunning():
            logger.info("Slot %s: stopping input worker", self._slot_id)
            self._worker.stop(intentional=True)
            if self._worker.isRunning():
                self._worker.wait(3000)
            if self._worker.isRunning():
                logger.error("Slot %s: worker did not stop", self._slot_id)
                self._macro_engine.resume()
                return False
            logger.info("Slot %s: input worker stopped", self._slot_id)
        self._macro_engine.resume()
        return True

    def _read_battery(self) -> int | None:
        """Battery level 0-100 from sysfs, None = unknown.

        The old code read ``self._device.device.read_feature_report(...)``
        which does not exist on evdev devices (AttributeError on every
        call), so the GUI battery column never updated from ``--``.
        """
        if not self._device:
            return None
        try:
            hid_path = DeviceManager.get_hid_device_path(self._device)
        except Exception:
            hid_path = None
        return battery_percent_from_sysfs(str(hid_path) if hid_path else None)

    def refresh_battery(self):
        if self.is_connected:
            level = self._read_battery()
            if level is not None and level != self._battery_level:
                self._battery_level = level
                self.battery_update.emit(level)

    def get_led_color(self) -> tuple:
        if self._profile:
            return self._profile.led_color
        return (0, 0, 255)

    def set_led_color(self, r: int, g: int, b: int):
        """Set LED color both in hardware (if available) and profile."""
        self._led_controller.set_color(r, g, b)
        if self._profile:
            self._profile.led_color = (r, g, b)

    def test_rumble(self, duration_ms: int = 500) -> bool:
        """Proportional rumble self-test (auto-stops after duration_ms).

        Prefers the worker's force-feedback path; falls back to a direct
        HID output report when the worker loop is not running.
        """
        if not self.is_connected:
            return False
        if self._worker.isRunning():
            return self._worker.test_rumble(duration_ms)
        ok = self._led_controller.set_rumble(0xFFFF, 0x8000)
        if ok:
            led = self._led_controller

            def _stop():
                # One-shot may fire after the slot was discarded (cleanup
                # closed the LED): capture only the controller (never self)
                # and swallow late errors instead of reopening a dead fd.
                try:
                    led.set_rumble(0, 0)
                except Exception:
                    pass

            QTimer.singleShot(duration_ms, _stop)
        return ok

    def cleanup(self):
        if not self.stop_worker() or not self.detach_device():
            logger.error("Slot %s: cleanup deferred because worker is active", self._slot_id)
            return False
        self._led_controller.close()
        self._macro_engine.shutdown()
        return True
