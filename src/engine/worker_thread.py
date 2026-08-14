from PySide6.QtCore import QThread, Signal
import select
import logging

from .virtual_device import VirtualDevice
from .input_mapper import InputMapper
from .led_controller import LEDController
from .ds4_hidraw import DS4HIDRAWReader, find_ds4_hidraw

logger = logging.getLogger(__name__)

DS4_BTN_CROSS = 0x01
DS4_BTN_CIRCLE = 0x02
DS4_BTN_TRIANGLE = 0x04
DS4_BTN_SQUARE = 0x08
DS4_BTN_L1 = 0x10
DS4_BTN_R1 = 0x20
DS4_BTN_SHARE = 0x40
DS4_BTN_OPTIONS = 0x80
DS4_BTN_L3 = 0x01 << 8
DS4_BTN_R3 = 0x02 << 8
DS4_BTN_PS = 0x04 << 8
DS4_BTN_TOUCHPAD = 0x08 << 8


class WorkerThread(QThread):
    device_connected = Signal(object)
    device_disconnected = Signal()
    battery_update = Signal(int)
    log_message = Signal(str)
    raw_event = Signal(int, int, int)
    fd_updated = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._virtual_device: VirtualDevice = None
        self._input_mapper: InputMapper = None
        self._led_controller: LEDController = None
        self._running = False
        self._device = None
        self._device_grabbed = True
        self._hidraw_reader: DS4HIDRAWReader = None
        self._intentional_stop = False

    def set_virtual_device(self, vdev: VirtualDevice):
        self._virtual_device = vdev

    def set_input_mapper(self, mapper: InputMapper):
        self._input_mapper = mapper

    def set_led_controller(self, led: LEDController):
        self._led_controller = led

    def set_device(self, device):
        self._device = device

    def set_device_grabbed(self, grabbed: bool):
        self._device_grabbed = grabbed

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
        use_hidraw = True
        # Always use HIDRAW for reliable D-pad input
        if self._device is not None and not self._device_grabbed:
            logger.info("Worker: evdev grabbed by another process, using HIDRAW")

        if not self._device or use_hidraw or not self._device_grabbed:
            hidraw_path = find_ds4_hidraw()
            if hidraw_path:
                self._hidraw_reader = DS4HIDRAWReader(hidraw_path)
                if self._hidraw_reader.open():
                    use_hidraw = True
                    logger.info(f"Worker: using HIDRAW mode {hidraw_path}")
                    self.device_connected.emit(None)
                else:
                    logger.error("Worker: no device, aborting")
                    self._running = False
                    if not self._intentional_stop:
                        self.device_disconnected.emit()
                    return
            else:
                logger.error("Worker: no device or hidraw, aborting")
                self._running = False
                if not self._intentional_stop:
                    self.device_disconnected.emit()
                return
        else:
            logger.info(f"Worker: using evdev mode, device={self._device}")

        self._running = True
        self.device_connected.emit(self._device)

        vdev = self._virtual_device
        mapper = self._input_mapper
        if not vdev or not mapper:
            return

        write_event = vdev.write_event
        sync = vdev.sync

        from evdev import ecodes as e
        from ..constants import XBOX_ABS_MAP, PS4_ABS_MAP, DS4Abs
        from ..engine.virtual_device import VirtualDeviceType

        EV_KEY = e.EV_KEY
        EV_ABS = e.EV_ABS
        EV_FF = e.EV_FF
        EV_ABS_HAT0X = e.ABS_HAT0X
        EV_ABS_HAT0Y = e.ABS_HAT0Y

        btn_state = mapper._btn_state
        axis_state = mapper._axis_state

        phys_fd = self._device.fd if (self._device and not use_hidraw) else -1
        virt_fd = vdev.uinput_fd
        hidraw_fd = self._hidraw_reader._fd if self._hidraw_reader else -1

        last_dpad_x = 0
        last_dpad_y = 0

        try:
            while self._running:
                fds = []
                if phys_fd >= 0:
                    fds.append(phys_fd)
                current_virt_fd = vdev.uinput_fd
                if current_virt_fd >= 0:
                    fds.append(current_virt_fd)
                if hidraw_fd >= 0:
                    fds.append(hidraw_fd)

                if not fds:
                    break

                try:
                    readable, _, _ = select.select(fds, [], [], 0.05)
                except (ValueError, OSError):
                    continue
                if phys_fd in readable and self._device:
                    try:
                        for event in self._device.read():
                            if not self._running:
                                break

                            if event.type in (EV_KEY, EV_ABS):
                                self.raw_event.emit(event.type, event.code, event.value)

                            profile = mapper.profile
                            btn_map = profile.button_maps
                            if profile.device_type == VirtualDeviceType.XBOX:
                                abs_map = XBOX_ABS_MAP
                            else:
                                abs_map = PS4_ABS_MAP

                            if event.type == EV_KEY:
                                 code = event.code
                                 pressed = event.value == 1
                                 # Convert D-pad KEY events to HAT ABS events
                                 if code == e.BTN_DPAD_UP:
                                     axis_state[EV_ABS_HAT0Y] = -1 if pressed else axis_state.get(EV_ABS_HAT0Y, 0)
                                     if not pressed and axis_state.get(EV_ABS_HAT0X, 0) != 0:
                                         pass  # keep X value
                                     elif not pressed:
                                         axis_state[EV_ABS_HAT0Y] = 0
                                     hvx = axis_state.get(EV_ABS_HAT0X, 0)
                                     hvy = axis_state.get(EV_ABS_HAT0Y, 0)
                                     vx = abs_map.get(EV_ABS_HAT0X)
                                     vy = abs_map.get(EV_ABS_HAT0Y)
                                     if vx is not None: write_event(EV_ABS, vx, hvx); sync()
                                     if vy is not None: write_event(EV_ABS, vy, hvy); sync()
                                     continue
                                 elif code == e.BTN_DPAD_DOWN:
                                     axis_state[EV_ABS_HAT0Y] = 1 if pressed else axis_state.get(EV_ABS_HAT0Y, 0)
                                     if not pressed and axis_state.get(EV_ABS_HAT0X, 0) != 0:
                                         pass
                                     elif not pressed:
                                         axis_state[EV_ABS_HAT0Y] = 0
                                     hvx = axis_state.get(EV_ABS_HAT0X, 0)
                                     hvy = axis_state.get(EV_ABS_HAT0Y, 0)
                                     vx = abs_map.get(EV_ABS_HAT0X)
                                     vy = abs_map.get(EV_ABS_HAT0Y)
                                     if vx is not None: write_event(EV_ABS, vx, hvx); sync()
                                     if vy is not None: write_event(EV_ABS, vy, hvy); sync()
                                     continue
                                 elif code == e.BTN_DPAD_LEFT:
                                     axis_state[EV_ABS_HAT0X] = -1 if pressed else axis_state.get(EV_ABS_HAT0X, 0)
                                     if not pressed and axis_state.get(EV_ABS_HAT0Y, 0) != 0:
                                         pass
                                     elif not pressed:
                                         axis_state[EV_ABS_HAT0X] = 0
                                     hvx = axis_state.get(EV_ABS_HAT0X, 0)
                                     hvy = axis_state.get(EV_ABS_HAT0Y, 0)
                                     vx = abs_map.get(EV_ABS_HAT0X)
                                     vy = abs_map.get(EV_ABS_HAT0Y)
                                     if vx is not None: write_event(EV_ABS, vx, hvx); sync()
                                     if vy is not None: write_event(EV_ABS, vy, hvy); sync()
                                     continue
                                 elif code == e.BTN_DPAD_RIGHT:
                                     axis_state[EV_ABS_HAT0X] = 1 if pressed else axis_state.get(EV_ABS_HAT0X, 0)
                                     if not pressed and axis_state.get(EV_ABS_HAT0Y, 0) != 0:
                                         pass
                                     elif not pressed:
                                         axis_state[EV_ABS_HAT0X] = 0
                                     hvx = axis_state.get(EV_ABS_HAT0X, 0)
                                     hvy = axis_state.get(EV_ABS_HAT0Y, 0)
                                     vx = abs_map.get(EV_ABS_HAT0X)
                                     vy = abs_map.get(EV_ABS_HAT0Y)
                                     if vx is not None: write_event(EV_ABS, vx, hvx); sync()
                                     if vy is not None: write_event(EV_ABS, vy, hvy); sync()
                                     continue
                                 # Map DS4 KEY_W (up) and KEY_Q (left) to D-pad
                                 if code == e.KEY_W:  # Up
                                     write_event(EV_KEY, e.BTN_DPAD_UP, 1 if pressed else 0); sync()
                                     continue
                                 elif code == e.KEY_Q:  # Left
                                     write_event(EV_KEY, e.BTN_DPAD_LEFT, 1 if pressed else 0); sync()
                                     continue
                                 elif code == e.KEY_S:  # Down
                                     write_event(EV_KEY, e.BTN_DPAD_DOWN, 1 if pressed else 0); sync()
                                     continue
                                 elif code == e.KEY_E:  # Right
                                     write_event(EV_KEY, e.BTN_DPAD_RIGHT, 1 if pressed else 0); sync()
                                     continue
                                 if code not in btn_map:
                                     continue
                                 prev_state = btn_state.get(code)
                                 if prev_state == pressed:
                                     continue
                                 btn_state[code] = pressed
                                 vcode = btn_map[code]
                                 write_event(EV_KEY, vcode, 1 if pressed else 0)
                                 sync()

                            elif event.type == EV_ABS:
                                code = event.code
                                if code in (EV_ABS_HAT0X, EV_ABS_HAT0Y):
                                    # Send BOTH HAT ABS (for Xbox-style games) AND BTN_DPAD keys (for other games)
                                    vcode = abs_map.get(code)
                                    if vcode is not None:
                                        if axis_state.get(code) != event.value:
                                            axis_state[code] = event.value
                                            write_event(EV_ABS, vcode, event.value)
                                            sync()
                                    if code == EV_ABS_HAT0X:
                                        if event.value == 1:
                                            write_event(EV_KEY, e.BTN_DPAD_RIGHT, 1); sync()
                                            write_event(EV_KEY, e.BTN_DPAD_RIGHT, 0); sync()
                                        elif event.value == -1:
                                            write_event(EV_KEY, e.BTN_DPAD_LEFT, 1); sync()
                                            write_event(EV_KEY, e.BTN_DPAD_LEFT, 0); sync()
                                    elif code == EV_ABS_HAT0Y:
                                        if event.value == 1:
                                            write_event(EV_KEY, e.BTN_DPAD_DOWN, 1); sync()
                                            write_event(EV_KEY, e.BTN_DPAD_DOWN, 0); sync()
                                        elif event.value == -1:
                                            write_event(EV_KEY, e.BTN_DPAD_UP, 1); sync()
                                            write_event(EV_KEY, e.BTN_DPAD_UP, 0); sync()
                                else:
                                    result = mapper.map_axis(code, event.value)
                                    if result:
                                        write_event(EV_ABS, result[0], result[1])
                                        sync()
                    except OSError as ex:
                        logger.warning(f"Worker: evdev read error: {ex}")
                        break

                if hidraw_fd in readable and self._hidraw_reader:
                    try:
                        report = self._hidraw_reader.read_report()
                        if report and len(report) >= 64:
                            last_dpad_x, last_dpad_y = self._process_hidraw_report(
                                report, write_event, sync, btn_state, axis_state,
                                mapper, last_dpad_x, last_dpad_y, EV_KEY, EV_ABS
                            )
                    except Exception as ex:
                        logger.warning(f"Worker: hidraw read error: {ex}")

                if current_virt_fd in readable and self._device:
                    try:
                        for event in vdev._uinput.read():
                            if event.type == EV_FF:
                                try:
                                    self._device.write(EV_FF, event.code, event.value)
                                    self._device.syn()
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
            if self._hidraw_reader:
                self._hidraw_reader.close()
            if not self._intentional_stop:
                self.device_disconnected.emit()

    def _process_hidraw_report(self, report, write_event, sync, btn_state, axis_state, mapper, last_dpad_x, last_dpad_y, EV_KEY, EV_ABS):
        """Process a HIDRAW report. Returns (new_dpad_x, new_dpad_y)."""
        from evdev import ecodes as e
        from ..constants import XBOX_ABS_MAP, PS4_ABS_MAP, DS4Abs
        from ..engine.virtual_device import VirtualDeviceType

        _EV_KEY = EV_KEY
        _EV_ABS = EV_ABS

        profile = mapper.profile
        btn_map = profile.button_maps
        abs_map = XBOX_ABS_MAP if profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP

        buttons = {
            e.BTN_SOUTH: bool(report[1] & DS4_BTN_CROSS),
            e.BTN_EAST: bool(report[1] & DS4_BTN_CIRCLE),
            e.BTN_NORTH: bool(report[1] & DS4_BTN_TRIANGLE),
            e.BTN_WEST: bool(report[1] & DS4_BTN_SQUARE),
            e.BTN_TL: bool(report[1] & DS4_BTN_L1),
            e.BTN_TR: bool(report[1] & DS4_BTN_R1),
            e.BTN_SELECT: bool(report[1] & DS4_BTN_SHARE),
            e.BTN_START: bool(report[1] & DS4_BTN_OPTIONS),
            e.BTN_THUMBL: bool(report[2] & DS4_BTN_L3),
            e.BTN_THUMBR: bool(report[2] & DS4_BTN_R3),
            e.BTN_MODE: bool(report[2] & DS4_BTN_PS),
        }

        dpad_byte = (report[3] >> 4) & 0x0F
        dpad_map = {
            0: (0, 0), 3: (0, 1), 6: (-1, 0), 8: (0, -1), 11: (1, 0),
            1: (1, 1), 2: (1, 1), 4: (-1, 1), 5: (-1, 1), 7: (-1, -1),
            9: (1, -1), 10: (1, -1), 12: (-1, -1), 13: (-1, -1),
            14: (-1, 0), 15: (1, 1),
        }
        dpad_x, dpad_y = dpad_map.get(dpad_byte, (0, 0))

        if dpad_x != last_dpad_x:
            code = abs_map.get(DS4Abs.HAT0X.value)
            if code is not None:
                write_event(_EV_ABS, code, dpad_x)
                sync()

        if dpad_y != last_dpad_y:
            code = abs_map.get(DS4Abs.HAT0Y.value)
            if code is not None:
                write_event(_EV_ABS, code, dpad_y)
                sync()

        lx, ly = report[4], report[5]
        rx, ry = report[6], report[7]
        l2, r2 = report[8], report[9]

        for code, val in [(DS4Abs.X, lx), (DS4Abs.Y, ly), (DS4Abs.RX, rx), (DS4Abs.RY, ry)]:
            result = mapper.map_axis(code.value, val)
            if result:
                write_event(_EV_ABS, result[0], result[1])
                sync()

        for code, val in [(DS4Abs.Z, l2), (DS4Abs.RZ, r2)]:
            result = mapper.map_axis(code.value, val)
            if result:
                write_event(_EV_ABS, result[0], result[1])
                sync()

        for ds4_code, pressed in buttons.items():
            if ds4_code not in btn_map:
                continue
            prev_state = btn_state.get(ds4_code)
            if prev_state == pressed:
                continue
            btn_state[ds4_code] = pressed
            write_event(_EV_KEY, btn_map[ds4_code], 1 if pressed else 0)
            sync()
            self.raw_event.emit(_EV_KEY, ds4_code, 1 if pressed else 0)

        return dpad_x, dpad_y

    def stop(self, intentional=False):
        self._intentional_stop = intentional
        self._running = False
        self.wait(2000)
        self._intentional_stop = False

    def is_device_connected(self) -> bool:
        return (self._device is not None or self._hidraw_reader is not None) and self.isRunning()
