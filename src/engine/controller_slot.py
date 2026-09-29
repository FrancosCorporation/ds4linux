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
        self._battery_level = 100
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
        was_running = self._worker.isRunning()
        if was_running:
            self._worker.stop(intentional=True)
            if not self._worker.wait(1000):
                # Rare: the loop is still winding down (exit took >2s).
                # Give it a bounded extra window instead of swapping the
                # virtual device under a live thread (its select()/writes
                # would hit a destroyed fd).
                if not self._worker.wait(2000):
                    logger.warning(
                        "Slot %s: worker did not exit before the profile "
                        "swap — proceeding with the device swap anyway",
                        self._slot_id,
                    )
            # Release keys the stopped run left pressed BEFORE set_profile
            # resets the mapper state: the vdev survives a same-type swap
            # and would keep them stuck until the next press+release. Only
            # when the thread really exited AND the vdev is still alive —
            # a winding-down thread may still write the same vdev, and a
            # destroyed vdev has nothing stuck on it.
            if not self._worker.isRunning() and self._virtual_device.is_active():
                self._worker.release_stuck_buttons(
                    self._input_mapper,
                    self._virtual_device.write_event,
                    self._virtual_device.sync,
                )

        self._profile = value
        self._input_mapper.set_profile(value)
        self._virtual_device.set_device_type(value.device_type)

        # Reconnect worker to new virtual device
        self._worker.set_virtual_device(self._virtual_device)

        if self._led_controller.is_available():
            self._led_controller.set_color(*value.led_color)
            self._led_controller.set_brightness(value.led_brightness)

        if was_running and self.is_connected:
            self.start_worker()

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
    def battery_level(self) -> int:
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
        self.profile = profile

    def attach_device(self, device_path: str) -> bool:
        if self.is_connected:
            return True

        self.status = SlotStatus.CONNECTING
        try:
            self._device = InputDevice(device_path)
            print(f"[SLOT{self._slot_id}] Controle Físico Encontrado: {device_path} name={self._device.name}")
        except (OSError, PermissionError) as e:
            logger.error(f"Cannot open {device_path}: {e}")
            print(f"[SLOT{self._slot_id}] ERRO: Não foi possível abrir {device_path}: {e}")
            self.status = SlotStatus.ERROR
            return False

        # Attempt exclusive grab with proper error handling
        try:
            self._device.grab()
            self._grabbed = True
            print(f"[SLOT{self._slot_id}] Grab exclusivo concedido em {device_path}")
        except OSError as e:
            print(f"[SLOT{self._slot_id}] ERRO CRÍTICO: grab() falhou — dispositivo ocupado por outro processo ({e})")
            print(f"[SLOT{self._slot_id}]   Verifique se Steam Input, ds4drv ou outra instância do ds4linux está rodando")
            logger.warning(f"grab() failed for {device_path}: {e} - continuing without grab")
            self._grabbed = False

        if not self._virtual_device.is_active():
            if self._virtual_device.create():
                print(f"[SLOT{self._slot_id}] Dispositivo Virtual Criado com sucesso (fd={self._virtual_device.uinput_fd})")
            else:
                print(f"[SLOT{self._slot_id}] ERRO: Falha ao criar Dispositivo Virtual!")
                self.status = SlotStatus.ERROR
                return False

        self._device_path = device_path
        self.status = SlotStatus.CONNECTED
        self._battery_level = self._read_battery()
        print(f"[SLOT{self._slot_id}] Status: CONNECTED — worker será iniciado")

        # Discover LED path from sysfs
        led_path = LEDController.find_ds4_led(device_path)
        if led_path:
            self._led_controller.set_led_path(led_path)
            logger.info(f"Found LED path: {led_path}")

        # Find specific HID device for this controller
        if self._device:
            hid_path = DeviceManager.get_hid_device_path(self._device)
            if hid_path:
                self._led_controller.set_hid_device(hid_path)
                logger.info(f"Found HID device: {hid_path}")
                self._start_motion_reader(str(hid_path))

        # Apply LED settings from profile
        self._led_controller.set_color(*self._profile.led_color)
        self._led_controller.set_brightness(self._profile.led_brightness)

        self.device_connected.emit(self._device)
        self.log_message.emit(f"Slot {self._slot_id}: DS4 connected at {device_path}")
        return True

    def detach_device(self):
        self._stop_motion_reader()
        if not self._device:
            return
        if self._grabbed:
            try:
                self._device.ungrab()
            except OSError:
                pass
            self._grabbed = False
            print(f"[SLOT{self._slot_id}] Dispositivo físico desanexado e ungrab")
        # Close regardless of grab: when grab() failed the fd stayed open
        # until GC (evdev __del__), leaking one descriptor per reattach.
        try:
            self._device.close()
        except OSError:
            pass

        was_connected = self.is_connected
        self._device = None
        self._device_path = None
        self.status = SlotStatus.DISCONNECTED

        # Destroy virtual device to release event device and close cached fds
        if self._virtual_device.is_active():
            self._virtual_device.destroy()
            print(f"[SLOT{self._slot_id}] Dispositivo Virtual destruído")

        if was_connected:
            self.device_disconnected.emit()
            self.log_message.emit(f"Slot {self._slot_id}: DS4 disconnected")

    def _setup_worker(self):
        self._worker.set_input_mapper(self._input_mapper)
        self._worker.set_virtual_device(self._virtual_device)
        self._worker.set_led_controller(self._led_controller)
        self._worker.device_connected.connect(self._on_worker_connected)
        self._worker.device_disconnected.connect(self._on_worker_disconnected)
        self._worker.log_message.connect(self.log_message.emit)
        self._worker.battery_update.connect(self.battery_update.emit)

    def _on_worker_connected(self, device):
        pass

    def _on_worker_disconnected(self):
        if self.is_connected:
            self.detach_device()

    def start_worker(self):
        if self.is_connected and self._input_mapper and not self._worker.isRunning():
            logger.info("Slot %s: starting worker loop", self._slot_id)
            if self._profile is not None:
                self._worker.set_select_timeout(self._profile.poll_rate_ms / 1000.0)
            self._worker.set_device(self._device)
            self._worker.set_device_grabbed(self._grabbed)
            self._worker.start()
            print(f"[SLOT{self._slot_id}] Worker started (thread={self._worker.thread()})")
        elif self._worker.isRunning():
            print(f"[SLOT{self._slot_id}] Worker já está rodando, não iniciando novamente")

    def stop_worker(self):
        if self._worker.isRunning():
            print(f"[SLOT{self._slot_id}] Parando Worker...")
            self._worker.stop()
            self._worker.wait(2000)
            print(f"[SLOT{self._slot_id}] Worker parado")

    def _read_battery(self) -> int:
        """Battery level 0-100 from the kernel power supply, 0 = unknown.

        The old code read ``self._device.device.read_feature_report(...)``
        which does not exist on evdev devices (AttributeError on every
        call), so the GUI battery column never updated from ``--``.
        """
        if not self._device:
            return 0
        try:
            hid_path = DeviceManager.get_hid_device_path(self._device)
        except Exception:
            hid_path = None
        return battery_percent_from_sysfs(str(hid_path) if hid_path else None)

    def refresh_battery(self):
        if self.is_connected:
            level = self._read_battery()
            # 0 means "unknown" — keep the last known value instead of lying.
            if level > 0 and level != self._battery_level:
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
        self.stop_worker()
        self.detach_device()
        self._led_controller.close()
        self._macro_engine.shutdown()
