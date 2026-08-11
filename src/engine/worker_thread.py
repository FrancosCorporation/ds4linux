from PySide6.QtCore import QThread, Signal
from evdev import InputDevice, ecodes as e
import select
import logging

from .virtual_device import VirtualDevice
from .input_mapper import InputMapper
from .led_controller import LEDController

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    """
    Reads events from a single pre-grabbed InputDevice in a background thread.
    Optimized for minimal input lag - processes events as quickly as possible.

    The device grab, open, close lifecycle is handled by ControllerSlot.
    """
    device_connected = Signal(object)
    device_disconnected = Signal()
    battery_update = Signal(int)
    log_message = Signal(str)
    # Emits (event_type, code, value) for raw input events — used by
    # mapping listen mode and wizard without interfering with normal mapping.
    raw_event = Signal(int, int, int)

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
            return

        self._running = True
        self.device_connected.emit(self._device)

        battery = self._read_battery()
        self.battery_update.emit(battery)

        vdev = self._virtual_device
        mapper = self._input_mapper
        device = self._device

        if not vdev or not mapper:
            return

        write_event = vdev.write_event
        sync = vdev.sync

        btn_map = mapper.profile.button_maps

        from ..constants import XBOX_ABS_MAP, PS4_ABS_MAP, VirtualDeviceType
        if mapper.profile.device_type == VirtualDeviceType.XBOX:
            abs_map = XBOX_ABS_MAP
        else:
            abs_map = PS4_ABS_MAP

        EV_KEY = e.EV_KEY
        EV_ABS = e.EV_ABS
        EV_FF = e.EV_FF
        EV_ABS_HAT0X = e.ABS_HAT0X
        EV_ABS_HAT0Y = e.ABS_HAT0Y

        btn_state = mapper._btn_state
        axis_state = mapper._axis_state

        phys_fd = device.fd
        virt_fd = vdev.uinput_fd
        fds_to_watch = [phys_fd]
        if virt_fd >= 0:
            fds_to_watch.append(virt_fd)

        try:
            while self._running:
                try:
                    readable, _, _ = select.select(fds_to_watch, [], [], 0.1)
                except (ValueError, OSError):
                    break

                if phys_fd in readable:
                    try:
                        for event in device.read(timeout=0):
                            if not self._running:
                                break

                            # Emit raw event for UI listen mode / wizard
                            if event.type in (EV_KEY, EV_ABS):
                                self.raw_event.emit(event.type, event.code, event.value)

                            if event.type == EV_KEY:
                                code = event.code
                                pressed = event.value == 1

                                if code not in btn_map:
                                    continue

                                prev_state = btn_state.get(code)
                                if prev_state == pressed:
                                    continue

                                btn_state[code] = pressed
                                vcode = btn_map[code]
                                val = 1 if pressed else 0
                                write_event(EV_KEY, vcode, val)
                                sync()

                            elif event.type == EV_ABS:
                                code = event.code

                                if code == EV_ABS_HAT0X or code == EV_ABS_HAT0Y:
                                    vcode = abs_map.get(code)
                                    if vcode is None:
                                        continue
                                    if axis_state.get(code) == event.value:
                                        continue
                                    axis_state[code] = event.value
                                    write_event(EV_ABS, vcode, event.value)
                                    sync()
                                else:
                                    result = mapper.map_axis(code, event.value)
                                    if result:
                                        vcode, val = result
                                        write_event(EV_ABS, vcode, val)
                                        sync()
                    except OSError:
                        break

                if virt_fd in readable:
                    try:
                        for event in vdev._uinput.read(timeout=0):
                            if event.type == EV_FF:
                                try:
                                    device.write(EV_FF, event.code, event.value)
                                    device.syn()
                                except OSError:
                                    pass
                    except OSError:
                        pass

        except OSError as ex:
            logger.warning(f"Device read error: {ex}")
        except Exception as ex:
            logger.error(f"Unexpected error in worker: {ex}")
        finally:
            self._running = False
            self.device_disconnected.emit()

    def stop(self):
        self._running = False
        self.wait(2000)

    def is_device_connected(self) -> bool:
        return self._device is not None and self.isRunning()
