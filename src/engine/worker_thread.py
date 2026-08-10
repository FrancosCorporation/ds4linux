from PySide6.QtCore import QThread, Signal
from evdev import InputDevice, ecodes as e
import logging

from .virtual_device import VirtualDevice
from .input_mapper import InputMapper
from .led_controller import LEDController
from .device_manager import DeviceManager

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    """
    Reads events from a single pre-grabbed InputDevice in a background thread.
    The device grab, open, close lifecycle is handled by ControllerSlot / DeviceMonitor.
    """
    device_connected = Signal(object)
    device_disconnected = Signal()
    event_received = Signal(int, int, int)
    log_message = Signal(str)
    battery_update = Signal(int)

    def __init__(self):
        super().__init__()
        self._virtual_device: VirtualDevice = None
        self._input_mapper: InputMapper = None
        self._led_controller: LEDController = None
        self._running = False
        self._device: InputDevice = None

    def set_virtual_device(self, vdev: VirtualDevice):
        self._virtual_device = vdev

    def set_input_mapper(self, mapper: InputMapper):
        self._input_mapper = mapper

    def set_led_controller(self, led: LEDController):
        self._led_controller = led

    def set_device(self, device: InputDevice):
        """Called by ControllerSlot after attach_device() (device already grabbed)."""
        self._device = device

    def _apply_led_settings(self):
        if self._led_controller and self._input_mapper:
            profile = self._input_mapper.profile
            self._led_controller.set_color(*profile.led_color)
            self._led_controller.set_brightness(profile.led_brightness)

    def _read_battery(self) -> int:
        if not self._device:
            return 0
        try:
            report = self._device.device.read_feature_report(0x02, 17)
            if report and len(report) >= 2:
                return min(100, round(report[1] / 255 * 100))
        except Exception:
            pass
        return 100

    def run(self):
        if not self._device:
            self.log_message.emit("Worker started without device")
            return

        self._running = True
        self.device_connected.emit(self._device)

        led_path = DeviceManager.get_led_path(self._device)
        if led_path and self._led_controller:
            self._led_controller.set_led_path(led_path)
            self._apply_led_settings()

        battery = self._read_battery()
        self.battery_update.emit(battery)

        try:
            for event in self._device.read_loop():
                if not self._running:
                    break
                self._process_event(event)
        except OSError as ex:
            logger.warning(f"Device read error: {ex}")
        except Exception as ex:
            logger.error(f"Unexpected error in worker: {ex}")
        finally:
            self._running = False
            self.device_disconnected.emit()
            self.log_message.emit("Worker stopped")

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
        self.wait(2000)

    def is_device_connected(self) -> bool:
        return self._device is not None and self.isRunning()