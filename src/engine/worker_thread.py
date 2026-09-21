import logging
import select
import time

from evdev import InputDevice
from evdev import ecodes as e
from PySide6.QtCore import QThread, Signal

from ..constants import PS4_ABS_MAP, XBOX_ABS_MAP, DS4Abs
from .dpad import DOWN, LEFT, RIGHT, UP, DpadState
from .ds4_hidraw import DS4HIDRAWReader, find_ds4_hidraw, parse_ds4_report
from .input_mapper import InputMapper
from .led_controller import LEDController
from .virtual_device import VirtualDevice, VirtualDeviceType

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    # Named constants (avoid magic numbers in the hot path)
    FEATURE_REPORT_ID = 0x02
    FEATURE_REPORT_SIZE = 17
    MIN_HIDRAW_REPORT_BYTES = 12
    DEFAULT_SELECT_TIMEOUT = 0.01
    MAX_CONSECUTIVE_ERRORS = 5
    ERROR_BACKOFF_S = 0.05

    device_connected = Signal(object)
    device_disconnected = Signal()
    battery_update = Signal(int)
    log_message = Signal(str)
    raw_event = Signal(int, int, int)
    fd_updated = Signal(int, int)

    def __init__(self, select_timeout: float | None = None):
        super().__init__()
        self._virtual_device: VirtualDevice | None = None
        self._input_mapper: InputMapper | None = None
        self._led_controller: LEDController | None = None
        self._running = False
        self._device = None
        self._device_grabbed = True
        self._hidraw_reader: DS4HIDRAWReader | None = None
        self._intentional_stop = False
        self._hidraw_fd: int = -1
        # select() tick: bounds how fast the loop notices _running == False.
        if select_timeout is None:
            select_timeout = self.DEFAULT_SELECT_TIMEOUT
        self._select_timeout = max(0.001, float(select_timeout))
        # Persistent reader for game -> physical rumble (EV_FF) events.
        self._rumble_dev = None
        self._rumble_path: str | None = None

    # All setters below MUST be called from the GUI thread BEFORE start();
    # run() reads them on the worker thread and never mutates them.
    def _ensure_setup_phase(self, setter: str):
        if self.isRunning():
            logger.warning("Worker: %s called while the thread is running", setter)

    def set_virtual_device(self, vdev: VirtualDevice):
        self._ensure_setup_phase("set_virtual_device")
        self._virtual_device = vdev

    def set_input_mapper(self, mapper: InputMapper):
        self._ensure_setup_phase("set_input_mapper")
        self._input_mapper = mapper

    def set_led_controller(self, led: LEDController):
        self._ensure_setup_phase("set_led_controller")
        self._led_controller = led

    def set_device(self, device):
        self._ensure_setup_phase("set_device")
        self._device = device

    def set_device_grabbed(self, grabbed: bool):
        self._ensure_setup_phase("set_device_grabbed")
        self._device_grabbed = grabbed

    def set_select_timeout(self, seconds: float):
        """Polling tick in seconds (1-1000 Hz).

        Safe to call at any time: the loop reads ``_select_timeout`` on every
        tick, so the new value takes effect immediately (next select()).
        """
        self._select_timeout = max(0.001, float(seconds))

    # ------------------------------------------------------------------
    # Rumble reader lifecycle
    # ------------------------------------------------------------------
    def _close_rumble_reader(self):
        if self._rumble_dev is not None:
            try:
                self._rumble_dev.close()
            except Exception:
                logger.debug("Worker: rumble reader close failed", exc_info=True)
        self._rumble_dev = None
        self._rumble_path = None

    def _ensure_rumble_reader(self, vdev: VirtualDevice) -> int:
        """(Re)open the rumble reader when the virtual device is recreated.

        Switching the emulated type (Xbox <-> PS4) destroys and recreates the
        uinput device, so the cached reader would point at a dead event node.
        Comparing the event path every tick is cheap and self-heals.
        Returns a readable fd, or -1 when rumble forwarding is unavailable.
        """
        path = vdev.event_device_path if self._device is not None else None
        if path is None:
            self._close_rumble_reader()
            return -1
        if path != self._rumble_path:
            self._close_rumble_reader()
            self._rumble_path = path
            if path:
                try:
                    self._rumble_dev = InputDevice(path)
                    logger.info("Worker: rumble reader on %s (fd=%s)",
                                path, self._rumble_dev.fd)
                except Exception:
                    logger.debug("Worker: rumble reader unavailable", exc_info=True)
        if self._rumble_dev is None:
            return -1
        try:
            return self._rumble_dev.fd
        except Exception:
            logger.debug("Worker: rumble fd lost")
            self._close_rumble_reader()
            return -1

    def _fail_startup(self, message: str):
        """Abort before the loop starts, releasing anything already opened."""
        logger.error(message)
        self._running = False
        if self._hidraw_reader is not None:
            self._hidraw_reader.close()
            self._hidraw_reader = None
            self._hidraw_fd = -1
        self._close_rumble_reader()
        if not self._intentional_stop:
            self.device_disconnected.emit()

    def _read_battery(self) -> int:
        """Battery level 0-100, or 0 when it cannot be read (unknown)."""
        if not self._device:
            return 0
        try:
            report = self._device.device.read_feature_report(
                self.FEATURE_REPORT_ID, self.FEATURE_REPORT_SIZE
            )
            if report and len(report) >= 2:
                return min(100, round(report[1] / 255 * 100))
        except Exception:
            logger.debug("Worker: battery read failed", exc_info=True)
        return 0

    # ------------------------------------------------------------------
    # D-pad helpers (BTN_DPAD_* -> ABS_HAT0X/ABS_HAT0Y)
    # ------------------------------------------------------------------
    @staticmethod
    def _write_hat(write_event, sync, abs_map, axis_state, x, y, x_code, y_code):
        """Write both HAT axes (only changed ones) and sync once.

        ``x_code``/``y_code`` are raw evdev axis codes.  Convention used by
        every caller: ``axis_state`` keys are always plain ints, while
        ``abs_map`` is keyed by ``DS4Abs`` members (an IntEnum, so int and
        enum hash together — the enum conversion below only makes the map
        lookup explicit).
        """
        changed = False
        vx = abs_map.get(DS4Abs(x_code))
        vy = abs_map.get(DS4Abs(y_code))
        if vx is not None and axis_state.get(x_code, 0) != x:
            axis_state[x_code] = x
            write_event(e.EV_ABS, vx, x)
            changed = True
        if vy is not None and axis_state.get(y_code, 0) != y:
            axis_state[y_code] = y
            write_event(e.EV_ABS, vy, y)
            changed = True
        if changed:
            sync()
        return changed

    def run(self):
        if not self._virtual_device or not self._input_mapper:
            self._fail_startup("Worker: missing virtual_device or input_mapper — aborting")
            return

        vdev = self._virtual_device
        if not vdev.is_active():
            if not vdev.create():
                self._fail_startup("Worker: failed to create virtual device — aborting")
                return
            logger.info("Worker: virtual device created (fd=%s)", vdev.uinput_fd)
        else:
            logger.debug("Worker: virtual device already active (fd=%s)", vdev.uinput_fd)

        # Determine mode: prefer evdev grab, fall back to HIDRAW
        use_hidraw = False
        if self._device is None:
            logger.info("Worker: no evdev device — using HIDRAW")
            use_hidraw = True
        elif not self._device_grabbed:
            logger.info("Worker: evdev not grabbed — using HIDRAW")
            use_hidraw = True
        else:
            logger.info("Worker: evdev mode on %s (grabbed)", self._device.path)

        # ------------------------------------------------------------------
        # Open HIDRAW if needed
        # ------------------------------------------------------------------
        if use_hidraw:
            uniq = getattr(self._device, "uniq", None) if self._device else None
            hidraw_path = find_ds4_hidraw(uniq)
            if not hidraw_path:
                self._fail_startup("Worker: no DS4 HIDRAW device found — aborting")
                return
            logger.info("Worker: opening HIDRAW %s (uniq=%s)", hidraw_path, uniq)
            self._hidraw_reader = DS4HIDRAWReader(hidraw_path)
            if not self._hidraw_reader.open():
                self._fail_startup("Worker: HIDRAW open failed — aborting")
                return
            self._hidraw_fd = self._hidraw_reader._fd

        # ------------------------------------------------------------------
        # Main event loop
        # ------------------------------------------------------------------
        self._running = True
        self.device_connected.emit(self._device)

        mapper = self._input_mapper
        write_event = vdev.write_event
        sync = vdev.sync
        # Batched sync: writes are queued through the deferred marker and the
        # real syn() happens once per input batch, not per event.
        pending_sync = [False]

        def mark_sync():
            pending_sync[0] = True

        EV_KEY = e.EV_KEY
        EV_ABS = e.EV_ABS
        EV_FF = e.EV_FF
        ABS_HAT0X = e.ABS_HAT0X
        ABS_HAT0Y = e.ABS_HAT0Y

        dpad_buttons = {
            e.BTN_DPAD_UP: UP,
            e.BTN_DPAD_DOWN: DOWN,
            e.BTN_DPAD_LEFT: LEFT,
            e.BTN_DPAD_RIGHT: RIGHT,
        }

        dpad_state = DpadState()

        # Public, shared state caches (see InputMapper docs): the worker is the
        # only writer while running, the GUI only reads indirectly via signals.
        btn_state = mapper.button_state
        axis_state = mapper.axis_state

        phys_fd = self._device.fd if (self._device and not use_hidraw) else -1
        virt_fd = vdev.uinput_fd
        hidraw_fd = self._hidraw_fd

        logger.debug("Worker: loop fds phys=%s virt=%s hidraw=%s",
                     phys_fd, virt_fd, hidraw_fd)

        consecutive_errors = 0
        try:
            while self._running:
                # Rumble reader is refreshed per tick: it must follow the
                # virtual device whenever it is recreated (type switch).
                rumble_fd = self._ensure_rumble_reader(vdev)

                fds = []
                if phys_fd >= 0:
                    fds.append(phys_fd)
                current_virt_fd = vdev.uinput_fd
                if current_virt_fd >= 0:
                    fds.append(current_virt_fd)
                if rumble_fd >= 0:
                    fds.append(rumble_fd)
                if hidraw_fd >= 0:
                    fds.append(hidraw_fd)

                if not fds:
                    logger.debug("Worker: no file descriptors — breaking loop")
                    break

                try:
                    # The tick only bounds how fast we notice _running == False;
                    # select() itself wakes instantly when data arrives.
                    readable, _, _ = select.select(fds, [], [], self._select_timeout)
                except (ValueError, OSError) as ex:
                    logger.error("Worker: select() error: %s", ex)
                    break

                # ------------------------------------------------------------------
                # evdev path
                # ------------------------------------------------------------------
                if phys_fd in readable and self._device and not use_hidraw:
                    try:
                        for event in self._device.read():
                            if not self._running:
                                break

                            if event.type in (EV_KEY, EV_ABS):
                                self.raw_event.emit(event.type, event.code, event.value)

                            profile = mapper.profile
                            btn_map = profile.button_maps
                            abs_map = (XBOX_ABS_MAP if profile.device_type == VirtualDeviceType.XBOX
                                       else PS4_ABS_MAP)

                            if event.type == EV_KEY:
                                code = event.code
                                pressed = event.value == 1

                                # ---- D-pad (hid-sony reports BTN_DPAD_*) ----
                                direction = dpad_buttons.get(code)
                                if direction is not None:
                                    if dpad_state.update(direction, pressed):
                                        self._write_hat(
                                            write_event, mark_sync, abs_map, axis_state,
                                            dpad_state.x, dpad_state.y,
                                            ABS_HAT0X, ABS_HAT0Y,
                                        )
                                    continue

                                # General button mapping via profile
                                if code not in btn_map:
                                    logger.debug("Unmapped key event: code=%s value=%s",
                                                 code, event.value)
                                    continue
                                prev_state = btn_state.get(code, False)
                                if prev_state == pressed:
                                    continue
                                btn_state[code] = pressed
                                vcode = btn_map[code]
                                write_event(EV_KEY, vcode, 1 if pressed else 0)
                                mark_sync()

                            elif event.type == EV_ABS:
                                code = event.code
                                # ---- D-pad (hid-playstation reports HAT axes) ----
                                if code in (ABS_HAT0X, ABS_HAT0Y):
                                    # axis_state keys are plain int evdev codes
                                    norm = -1 if event.value < 0 else (1 if event.value > 0 else 0)
                                    if axis_state.get(code, 0) != norm:
                                        axis_state[code] = norm
                                        vcode = abs_map.get(DS4Abs(code))
                                        if vcode is not None:
                                            write_event(EV_ABS, vcode, norm)
                                            mark_sync()
                                    continue

                                result = mapper.map_axis(code, event.value)
                                if result:
                                    write_event(EV_ABS, result[0], result[1])
                                    mark_sync()
                                else:
                                    logger.debug("Unmapped axis event: code=%s value=%s",
                                                 code, event.value)
                        if pending_sync[0]:
                            sync()
                            pending_sync[0] = False
                        consecutive_errors = 0
                    except OSError as ex:
                        logger.error("Worker: evdev read OSError: %s", ex)
                        break
                    except Exception as ex:
                        consecutive_errors += 1
                        logger.error("Worker: evdev unexpected error (%s/%s): %s: %s",
                                     consecutive_errors, self.MAX_CONSECUTIVE_ERRORS,
                                     type(ex).__name__, ex)
                        if consecutive_errors > self.MAX_CONSECUTIVE_ERRORS:
                            logger.error("Worker: too many consecutive errors — stopping")
                            break
                        time.sleep(self.ERROR_BACKOFF_S)

                # ------------------------------------------------------------------
                # HIDRAW path
                # ------------------------------------------------------------------
                if hidraw_fd in readable and self._hidraw_reader and use_hidraw:
                    try:
                        report = self._hidraw_reader.read_report()
                        if report and len(report) >= self.MIN_HIDRAW_REPORT_BYTES:
                            self._process_hidraw_report(
                                report, write_event, mark_sync,
                                mapper.button_state, mapper.axis_state,
                                mapper, EV_KEY, EV_ABS,
                            )
                            if pending_sync[0]:
                                sync()
                                pending_sync[0] = False
                            consecutive_errors = 0
                    except OSError as ex:
                        # hidraw node died (unplug/BT drop): stop cleanly so
                        # the slot reports a disconnect.
                        logger.error("Worker: hidraw device lost: %s", ex)
                        break
                    except Exception as ex:
                        consecutive_errors += 1
                        logger.error("Worker: hidraw error (%s/%s): %s: %s",
                                     consecutive_errors, self.MAX_CONSECUTIVE_ERRORS,
                                     type(ex).__name__, ex)
                        if consecutive_errors > self.MAX_CONSECUTIVE_ERRORS:
                            logger.error("Worker: too many consecutive errors — stopping")
                            break
                        time.sleep(self.ERROR_BACKOFF_S)

                # ------------------------------------------------------------------
                # Rumble forwarding (game -> physical)
                # ------------------------------------------------------------------
                if rumble_fd in readable and self._rumble_dev is not None:
                    try:
                        forwarded = False
                        for event in self._rumble_dev.read():
                            if event.type == EV_FF:
                                try:
                                    self._device.write(EV_FF, event.code, event.value)
                                    forwarded = True
                                except OSError as ex:
                                    logger.debug("Worker: rumble forward OSError: %s", ex)
                        if forwarded:
                            self._device.syn()
                    except BlockingIOError:
                        pass  # no pending events (fd is non-blocking)
                    except OSError as ex:
                        # The event node was recreated or removed — drop the
                        # stale reader; _ensure_rumble_reader reopens on the
                        # next tick if a node exists.
                        logger.debug("Worker: rumble reader lost: %s", ex)
                        self._close_rumble_reader()
                    except Exception as ex:
                        logger.debug("Worker: rumble event read error: %s", ex)

        except OSError as ex:
            logger.error("Worker: device read OSError: %s", ex)
        except Exception:
            logger.exception("Worker: unexpected fatal error")
        finally:
            logger.info("Worker: event loop finished — cleaning up")
            self._running = False
            if self._hidraw_reader:
                self._hidraw_reader.close()
                self._hidraw_fd = -1
            self._close_rumble_reader()
            vdev.close_event_fd()
            if not self._intentional_stop:
                self.device_disconnected.emit()

    def _process_hidraw_report(self, report, write_event, sync, btn_state, axis_state,
                               mapper, EV_KEY, EV_ABS):
        """Apply one parsed HIDRAW report to the virtual device.

        Pure translation step between ``parse_ds4_report`` state and the
        virtual device: D-pad goes through ``_write_hat`` (same helper as the
        evdev path), sticks/triggers through ``InputMapper.map_axis`` and
        buttons through the profile's ``button_maps``.  Change detection for
        the HAT axes relies on ``axis_state`` so both input paths share one
        source of truth.
        """
        profile = mapper.profile
        btn_map = profile.button_maps
        abs_map = XBOX_ABS_MAP if profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP

        state = parse_ds4_report(report)
        dpad_x, dpad_y = state['dpad_x'], state['dpad_y']

        # Batch the sync: one syn() per report instead of one per write
        # (mirrors the evdev path, which uses the same deferred pattern).
        wrote = [False]

        def mark_sync():
            wrote[0] = True

        prev_x = axis_state.get(e.ABS_HAT0X, 0)
        prev_y = axis_state.get(e.ABS_HAT0Y, 0)
        if (dpad_x, dpad_y) != (prev_x, prev_y):
            self._write_hat(write_event, mark_sync, abs_map, axis_state,
                            dpad_x, dpad_y, e.ABS_HAT0X, e.ABS_HAT0Y)
            if axis_state.get(e.ABS_HAT0X, 0) != prev_x:
                self.raw_event.emit(EV_ABS, e.ABS_HAT0X, dpad_x)
            if axis_state.get(e.ABS_HAT0Y, 0) != prev_y:
                self.raw_event.emit(EV_ABS, e.ABS_HAT0Y, dpad_y)

        for ds4_code, val in ((DS4Abs.X, state['lx']), (DS4Abs.Y, state['ly']),
                              (DS4Abs.RX, state['rx']), (DS4Abs.RY, state['ry']),
                              (DS4Abs.Z, state['l2']), (DS4Abs.RZ, state['r2'])):
            result = mapper.map_axis(ds4_code.value, val)
            if result:
                write_event(EV_ABS, result[0], result[1])
                mark_sync()
                # NOTE: raw_event always carries *physical* DS4 codes in both
                # input paths — the Readings tab maps them to DS4 widgets.
                self.raw_event.emit(EV_ABS, ds4_code.value, val)

        for ds4_code, pressed in state['buttons'].items():
            if ds4_code not in btn_map:
                continue
            # Default False: an unpressed button on the very first report is
            # already "released", so we must not emit a burst of EV_KEY 0.
            prev_state = btn_state.get(ds4_code, False)
            if prev_state == pressed:
                continue
            btn_state[ds4_code] = pressed
            write_event(EV_KEY, btn_map[ds4_code], 1 if pressed else 0)
            mark_sync()
            # Physical code on purpose (see note above)
            self.raw_event.emit(EV_KEY, ds4_code, 1 if pressed else 0)

        if wrote[0]:
            sync()
        return dpad_x, dpad_y
    def stop(self, intentional=False):
        logger.debug("Worker: stop(intentional=%s)", intentional)
        self._intentional_stop = intentional
        self._running = False
        self.wait(2000)
        self._intentional_stop = False

    def is_device_connected(self) -> bool:
        return (self._device is not None or self._hidraw_reader is not None) and self.isRunning()
