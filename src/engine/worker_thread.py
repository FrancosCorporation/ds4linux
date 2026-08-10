from PySide6.QtCore import QThread, Signal
from evdev import InputDevice, ecodes as e
import logging

from .device_manager import DeviceManager
from .virtual_device import VirtualDevice
from .input_mapper import InputMapper
from .led_controller import LEDController

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    device_connected = Signal(object)
    device_disconnected = Signal()
    event_received = Signal(int, int, int)
    log_message = Signal(str)
    battery_update = Signal(int)

    def __init__(self):
        super().__init__()
        self._device_manager = DeviceManager()
        self._virtual_device: VirtualDevice = None
        self._input_mapper: InputMapper = None
        self._led_controller: LEDController = None
        self._running = False
        self._device: InputDevice = None

        self._device_manager.set_callbacks(
            on_found=self._on_device_found,
            on_lost=self._on_device_lost
        )

    def set_virtual_device(self, vdev: VirtualDevice):
        self._virtual_device = vdev

    def set_input_mapper(self, mapper: InputMapper):
        self._input_mapper = mapper

    def set_led_controller(self, led: LEDController):
        self._led_controller = led

    def _on_device_found(self, device: InputDevice):
        self._device = device
        self.device_connected.emit(device)
        led_path = DeviceManager.get_led_path(device)
        if led_path and self._led_controller:
            self._led_controller.set_led_path(led_path)
            self._apply_led_settings()
        self.log_message.emit(f"DS4 connected: {device.path}")

    def _on_device_lost(self):
        self._device = None
        self.device_disconnected.emit()
        self.log_message.emit("DS4 disconnected")

    def _apply_led_settings(self):
        if self._led_controller and self._input_mapper:
            profile = self._input_mapper.profile
            self._led_controller.set_color(*profile.led_color)
            self._led_controller.set_brightness(profile.led_brightness)

    def run(self):
        self._running = True
        self._find_and_open_device()
        while self._running:
            if not self._device:
                self.msleep(1000)
                self._find_and_open_device()
                continue
            try:
                for event in self._device.read_loop():
                    if not self._running:
                        break
                    self._process_event(event)
            except OSError as ex:
                logger.warning(f"Device read error: {ex}")
                self._device_manager.close_device()
                self._device = None
            except Exception as ex:
                logger.error(f"Unexpected error in worker: {ex}")
                self.msleep(100)

    def _find_and_open_device(self):
        device = self._device_manager.find_ds4()
        if device and self._device_manager.open_device(device.path):
            self._device = device
            led_path = DeviceManager.get_led_path(device)
            if led_path and self._led_controller:
                self._led_controller.set_led_path(led_path)
                self._apply_led_settings()
            self.device_connected.emit(device)
            self.log_message.emit(f"DS4 connected: {device.path}")

    def _process_event(self, event):
        if event.type == e.EV_KEY:
            self._handle_key_event(event)
        elif event.type == e.EV_ABS:
            self._handle_abs_event(event)

    def _handle_key_event(self, event):
        if not self._input_mapper or not self._virtual_device:
            return
        result = self._input_mapper.map_button(event.code, event.value)
        if result:
            vcode, value = result
            self._virtual_device.write_event(e.EV_KEY, vcode, value)
            self._virtual_device.sync()
            self.event_received.emit(e.EV_KEY, vcode, value)

    def _handle_abs_event(self, event):
        if not self._input_mapper or not self._virtual_device:
            return
        if event.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
            result = self._input_mapper.map_hat(event.code, event.value)
        else:
            result = self._input_mapper.map_axis(event.code, event.value)
        if result:
            vcode, value = result
            self._virtual_device.write_event(e.EV_ABS, vcode, value)
            self._virtual_device.sync()
            self.event_received.emit(e.EV_ABS, vcode, value)

    def stop(self):
        self._running = False
        self._device_manager.close_device()
        self.wait(2000)

    def is_device_connected(self) -> bool:
        return self._device is not None and self._device_manager.is_grabbed()