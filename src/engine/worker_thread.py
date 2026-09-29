import logging
import select
import threading
import time

from evdev import InputDevice
from evdev import ecodes as e
from PySide6.QtCore import QThread, Signal

from ..constants import PS4_ABS_MAP, XBOX_ABS_MAP, DS4Abs
from .battery import battery_percent_from_status, battery_percent_from_sysfs
from .dpad import DOWN, LEFT, RIGHT, UP, DpadState
from .ds4_hidraw import (
    DS4_REPORT_ID_BT,
    DS4_REPORT_ID_USB,
    DS4HIDRAWReader,
    find_ds4_hidraw,
    parse_ds4_report,
)
from .ff_upload import (
    EV_UINPUT,
    UI_FF_ERASE,
    UI_FF_UPLOAD,
    FFUpload,
    build_rumble_effect,
    handle_ff_erase,
    handle_ff_upload,
)
from .input_mapper import InputMapper
from .led_controller import LEDController
from .motion_source import parse_ds4_battery
from .virtual_device import VirtualDevice, VirtualDeviceType

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    # Named constants (avoid magic numbers in the hot path)
    MIN_HIDRAW_REPORT_BYTES = 12
    DEFAULT_SELECT_TIMEOUT = 0.01
    MAX_CONSECUTIVE_ERRORS = 5
    ERROR_BACKOFF_S = 0.05
    # Safety watchdog: stop the physical motors when the game stops sending
    # play events (crash/disconnect) so rumble can never stick on forever.
    RUMBLE_STALE_S = 5.0
    # How often a failed physical FF path is re-probed (transient upload
    # errors must not degrade rumble to the HID fallback for the session).
    PHYS_FF_RETRY_S = 30.0
    # Throttle for the rumble-reader reopen attempts while its event node
    # is unavailable (otherwise the hot loop churns open/exception ~100 Hz).
    RUMBLE_RETRY_S = 1.0
    # Battery polling: sysfs/status read at most this often (GUI shows the
    # latest emitted level; 0 means "unknown" and is never emitted).
    BATTERY_POLL_S = 30.0

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
        # Last known battery percent (0 = unknown) + poll throttle.
        self._last_battery_level = 0
        self._last_battery_status = 0
        self._last_battery_poll = 0.0
        # Raw axis dedup: HIDRAW repeats the full state at ~250 Hz — the
        # Readings tab only needs physical changes (like kernel events).
        self._raw_axis_prev: dict[int, int] = {}
        # Physical HAT tracker for the raw_event dedup: axis_state holds the
        # EFFECTIVE value (post-macro), so a macro-bound direction held down
        # would differ from the raw value on every report and flood the GUI.
        self._raw_hat_prev: dict[int, int] = {}
        # Same idea for buttons: emitted for EVERY physical button (mapped
        # or not) on transition, with its own tracker — btn_state must stay
        # untouched here or map_button's internal dedup would swallow the
        # mapped write.
        self._raw_btn_prev: dict[int, bool] = {}
        # select() tick: bounds how fast the loop notices _running == False.
        if select_timeout is None:
            select_timeout = self.DEFAULT_SELECT_TIMEOUT
        self._select_timeout = max(0.001, float(select_timeout))
        # Persistent reader for game -> physical rumble (EV_FF) events.
        self._rumble_dev = None
        self._rumble_path: str | None = None
        # Effects uploaded by the game on the virtual device
        # (virtual effect id -> magnitudes/timing captured via UI_FF_UPLOAD).
        self._rumble_effects: dict[int, FFUpload] = {}
        self._playing_virt_id: int | None = None
        self._rumble_deadline = 0.0
        self._rumble_active = False
        # Serializes the FF/rumble state (deadline/active/effect) and the
        # physical evdev FF writes between the worker loop, the GUI
        # test_rumble() caller and the auto-stop Timer thread. The virtual
        # effect cache (_rumble_effects) and _playing_virt_id are touched
        # only by the worker loop thread itself — no cross-thread access,
        # so they need no lock (only the FF state above does).
        self._ff_lock = threading.RLock()
        # Physical-side force feedback: one EVIOCSFF FF_RUMBLE effect reused
        # for every play. _phys_ff_ok None = probe not done yet; after a
        # failed upload it becomes False and is re-probed every
        # PHYS_FF_RETRY_S (transient errors must not kill FF for the
        # session).
        self._phys_effect = None
        self._phys_effect_id: int | None = None
        self._phys_ff_ok: bool | None = None
        self._phys_ff_retry_at = 0.0
        self._rumble_retry_at = 0.0
        # Generation token for the test_rumble auto-stop Timer: any
        # game-driven play (in _on_play_event) invalidates the pending
        # stop so the Timer can never kill a game's real rumble.
        self._rumble_generation = 0
        self._test_stop_timer = None
        # D-pad macro bookkeeping (shared by evdev HAT and HIDRAW paths):
        # previous pressed state per BTN_DPAD_* code for transition dedup,
        # and the last HAT value actually written to the virtual device.
        self._dpad_macro_prev: dict[int, bool] = {}
        self._dpad_hat_written: dict[int, int] = {}

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
        # The virtual device was recreated: old effect ids no longer apply.
        self._rumble_effects.clear()
        self._playing_virt_id = None

    def _ensure_rumble_reader(self, vdev: VirtualDevice) -> int:
        """(Re)open the rumble reader when the virtual device is recreated.

        Switching the emulated type (Xbox <-> PS4) destroys and recreates the
        uinput device, so the cached reader would point at a dead event node.
        Comparing the event path every tick is cheap and self-heals.
        Returns a readable fd, or -1 when rumble forwarding is unavailable.
        """
        # The virtual device's event node is what matters (it exists even in
        # HIDRAW-only setups); gating on the physical evdev device silently
        # disabled FF forwarding when _device was momentarily unset.
        path = vdev.event_device_path
        if path is None:
            self._close_rumble_reader()
            return -1
        if path != self._rumble_path:
            self._close_rumble_reader()
            self._rumble_path = path
            self._rumble_dev = None  # force (re)open below
            # A new path should open immediately — don't inherit a retry
            # throttle from a previous failure on a different node.
            self._rumble_retry_at = 0.0
        if self._rumble_dev is None:
            # (Re)open while broken, throttled to once per second: a
            # transient failure on the first attempt used to kill FF
            # forwarding until the vdev was recreated, and an unthrottled
            # retry would churn open/exception at ~100 Hz in the hot loop.
            if time.monotonic() >= self._rumble_retry_at:
                self._rumble_retry_at = time.monotonic() + self.RUMBLE_RETRY_S
                try:
                    self._rumble_dev = InputDevice(path)
                    self._rumble_dev.set_nonblocking(True)
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
        """Battery 0-100, or 0 when it cannot be read (unknown).

        Sources, in order: the kernel power supply next to the HID device
        (hid-sony/hid-playstation), then the last DS4 status byte seen on
        the HIDRAW path.  The old code called ``self._device.device.
        read_feature_report`` which does not exist on evdev devices, so
        every read raised AttributeError and the signal never fired.
        """
        hidraw_path = (
            self._hidraw_reader.hidraw_path if self._hidraw_reader else None
        )
        if hidraw_path is None and self._device is not None:
            try:
                hidraw_path = find_ds4_hidraw(
                    getattr(self._device, "uniq", None)
                )
            except Exception:
                hidraw_path = None
        level = battery_percent_from_sysfs(hidraw_path)
        if level <= 0 and self._last_battery_status > 0:
            level = battery_percent_from_status(self._last_battery_status)
        return level

    def _maybe_emit_battery(self) -> None:
        """Poll battery and emit on change (throttled by TIME, not by tick).
        Unknown reads (0) are never emitted: the GUI treats 0 as "no data"."""
        now = time.monotonic()
        if now - self._last_battery_poll < self.BATTERY_POLL_S:
            return
        self._last_battery_poll = now
        level = self._read_battery()
        if level > 0 and level != self._last_battery_level:
            self._last_battery_level = level
            self.battery_update.emit(level)

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
        # Fresh physical FF probe per run (device may differ between runs).
        self._phys_ff_ok = None
        self._phys_ff_retry_at = 0.0
        self._phys_effect = None
        self._phys_effect_id = None
        self._rumble_active = False
        self._dpad_macro_prev = {}
        self._dpad_hat_written = {}
        self._raw_axis_prev = {}
        self._raw_btn_prev = {}
        self._raw_hat_prev = {}
        self._last_battery_level = 0
        self._last_battery_status = 0
        # 'overdue', not 0.0: on a fresh boot (monotonic() < BATTERY_POLL_S)
        # a 0.0 reset would delay the first battery poll by up to 30 s.
        self._last_battery_poll = time.monotonic() - self.BATTERY_POLL_S - 1
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

        # Release sweep: the mapper's pressed-state cache survives worker
        # restarts, but the virtual device may have been recreated (slot
        # reconnect) or left with a pressed key (worker died mid-press,
        # profile swap). Emit EV_KEY 0 for everything the previous run
        # believed was down, then start clean — otherwise a release that
        # happens while the worker is stopped is swallowed by stale dedup
        # state and the virtual button sticks until the next full pair.
        self.release_stuck_buttons(mapper, write_event, sync)

        dpad_buttons = {
            e.BTN_DPAD_UP: UP,
            e.BTN_DPAD_DOWN: DOWN,
            e.BTN_DPAD_LEFT: LEFT,
            e.BTN_DPAD_RIGHT: RIGHT,
        }

        dpad_state = DpadState()

        # Public, shared state cache (see InputMapper docs): the worker is the
        # only writer while running, the GUI only reads indirectly via signals.
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

                # Throttled battery poll (no-op for BATTERY_POLL_S ticks).
                self._maybe_emit_battery()

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
                            abs_map = (XBOX_ABS_MAP if profile.device_type == VirtualDeviceType.XBOX
                                       else PS4_ABS_MAP)

                            if event.type == EV_KEY:
                                code = event.code
                                pressed = event.value == 1

                                # ---- D-pad (hid-sony reports BTN_DPAD_*) ----
                                direction = dpad_buttons.get(code)
                                if direction is not None:
                                    # A macro bound to a D-pad button wins
                                    # over the hat translation.
                                    if mapper.maybe_execute_macro(code, event.value):
                                        continue
                                    if dpad_state.update(direction, pressed):
                                        self._write_hat(
                                            write_event, mark_sync, abs_map, axis_state,
                                            dpad_state.x, dpad_state.y,
                                            ABS_HAT0X, ABS_HAT0Y,
                                        )
                                    continue

                                # General mapping + macro trigger via profile
                                result = mapper.map_button(code, event.value)
                                if result:
                                    write_event(EV_KEY, result[0], result[1])
                                    mark_sync()

                            elif event.type == EV_ABS:
                                code = event.code
                                # ---- D-pad (hid-playstation reports HAT axes) ----
                                if code in (ABS_HAT0X, ABS_HAT0Y):
                                    # axis_state keys are plain int evdev codes
                                    norm = -1 if event.value < 0 else (1 if event.value > 0 else 0)
                                    if axis_state.get(code, 0) != norm:
                                        axis_state[code] = norm
                                        # D-pad macros fire on hat changes too
                                        # (mirrors the BTN_DPAD branch above).
                                        eff_x, eff_y = self._dpad_macro_step(
                                            mapper,
                                            axis_state.get(ABS_HAT0X, 0),
                                            axis_state.get(ABS_HAT0Y, 0),
                                        )
                                        target = eff_x if code == ABS_HAT0X else eff_y
                                        if self._dpad_hat_written.get(code, 0) != target:
                                            self._dpad_hat_written[code] = target
                                            vcode = abs_map.get(DS4Abs(code))
                                            if vcode is not None:
                                                write_event(EV_ABS, vcode, target)
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
                # Force-feedback upload/erase handshake (uinput control channel)
                # ------------------------------------------------------------------
                if current_virt_fd in readable:
                    self._handle_uinput_events(vdev)

                # ------------------------------------------------------------------
                # Rumble forwarding (game -> physical)
                # ------------------------------------------------------------------
                if rumble_fd in readable and self._rumble_dev is not None:
                    try:
                        for event in self._rumble_dev.read():
                            if event.type == EV_FF:
                                self._on_play_event(event.code, event.value)
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

                # Watchdog: never leave the motors running if the game died
                # without sending the stop event. Check+act under the FF
                # lock (test_rumble/Timer mutate the same state).
                with self._ff_lock:
                    if self._rumble_active and time.monotonic() > self._rumble_deadline:
                        logger.debug("Worker: rumble deadline reached — stopping")
                        self._stop_rumble()

        except OSError as ex:
            logger.error("Worker: device read OSError: %s", ex)
        except Exception:
            logger.exception("Worker: unexpected fatal error")
        finally:
            logger.info("Worker: event loop finished — cleaning up")
            self._running = False
            self._stop_rumble()
            if self._hidraw_reader:
                self._hidraw_reader.close()
                self._hidraw_fd = -1
            self._close_rumble_reader()
            vdev.close_event_fd()
            if not self._intentional_stop:
                self.device_disconnected.emit()
            # Consume the flag: stop() leaves it set when wait() times out
            # so this block could still see it; clear it for the next run.
            self._intentional_stop = False

    # ------------------------------------------------------------------
    # FF handshake + D-pad macros (helpers shared by the event paths)
    # ------------------------------------------------------------------
    def release_stuck_buttons(self, mapper, write_event, sync) -> None:
        """Release sweep + state reset (see the call site in ``run``).

        Emits EV_KEY 0 for every *mapped* button the previous run believed
        was down (macro-bound buttons never wrote the virtual device, so
        they hold nothing), then clears the mapper cache so a release
        happening while the worker was stopped can never be swallowed by
        stale dedup data.
        """
        wrote = False
        for ds4_code, was_pressed in list(mapper.button_state.items()):
            # The code ACTUALLY written last run — the current button_maps
            # may have changed (profile swap) and would release the wrong
            # code, leaving the old one stuck on the surviving vdev.
            virtual_code = mapper.written_virtual.get(ds4_code)
            if was_pressed and virtual_code is not None:
                write_event(e.EV_KEY, virtual_code, 0)
                wrote = True
        mapper.reset_state()
        if wrote:
            sync()

    def _handle_uinput_events(self, vdev) -> None:
        """Drain FF upload/erase handshake events from the uinput fd.

        The kernel writes EV_UINPUT events there whenever a game uploads
        (EVIOCSFF) or erases an effect; the captured magnitudes are what
        makes rumble proportional instead of on/off.
        """
        uinput_dev = vdev.uinput
        if uinput_dev is None:
            return
        try:
            for event in uinput_dev.read():
                if event.type == EV_UINPUT:
                    if event.code == UI_FF_UPLOAD:
                        upload = handle_ff_upload(vdev.uinput_fd, event.value)
                        if upload is not None:
                            self._rumble_effects[upload.effect_id] = upload
                    elif event.code == UI_FF_ERASE:
                        erased_id = handle_ff_erase(vdev.uinput_fd, event.value)
                        if erased_id is not None:
                            self._rumble_effects.pop(erased_id, None)
                            with self._ff_lock:
                                if self._playing_virt_id == erased_id:
                                    self._stop_rumble()
                                    self._playing_virt_id = None
        except BlockingIOError:
            pass  # no pending events
        except OSError as ex:
            logger.debug("Worker: FF handshake read error: %s", ex)

    def _dpad_macro_step(self, mapper, dpad_x: int, dpad_y: int) -> tuple[int, int]:
        """Fire macros bound to D-pad directions and neutralize them.

        Shared by the evdev HAT-axes branch and the HIDRAW path (which
        only expose the hat, unlike hid-sony's BTN_DPAD_* events — without
        this, D-pad macros would never fire in those modes). Returns the
        effective (x, y) with macro-bound directions zeroed so the macro
        *replaces* the button, matching the evdev BTN_DPAD behaviour.
        """
        directions = (
            (e.BTN_DPAD_LEFT, dpad_x < 0),
            (e.BTN_DPAD_RIGHT, dpad_x > 0),
            (e.BTN_DPAD_UP, dpad_y < 0),
            (e.BTN_DPAD_DOWN, dpad_y > 0),
        )
        bound: dict[int, bool] = {}
        for code, active in directions:
            if not mapper.is_macro_button(code):
                continue
            bound[code] = True
            prev = self._dpad_macro_prev.get(code, False)
            if prev != active:
                self._dpad_macro_prev[code] = active
                if active and mapper.macro_engine is not None:
                    # .get() instead of direct indexing: the profile can be
                    # swapped from the GUI between is_macro_button and here.
                    macro = (
                        mapper.profile.macros.get(code) if mapper.profile else None
                    )
                    if macro:
                        mapper.macro_engine.execute_macro(macro)
        eff_x = 0 if (dpad_x < 0 and bound.get(e.BTN_DPAD_LEFT)) or (
            dpad_x > 0 and bound.get(e.BTN_DPAD_RIGHT)
        ) else dpad_x
        eff_y = 0 if (dpad_y < 0 and bound.get(e.BTN_DPAD_UP)) or (
            dpad_y > 0 and bound.get(e.BTN_DPAD_DOWN)
        ) else dpad_y
        return eff_x, eff_y

    # ------------------------------------------------------------------
    # Rumble: game (virtual) -> physical
    # ------------------------------------------------------------------
    def _on_play_event(self, virt_id: int, count: int):
        """Handle one EV_FF playback event coming from the game.

        ``count`` is the play count (0 == stop) the game wrote on the
        virtual device; the effect id is virtual, so it is translated to the
        magnitudes captured by the UI_FF_UPLOAD handshake and replayed on the
        physical pad.
        """
        if count <= 0:
            with self._ff_lock:
                self._playing_virt_id = None
                self._rumble_generation += 1  # invalidates a pending test stop
            self._stop_rumble()
            return

        upload = self._rumble_effects.get(virt_id)
        if upload is not None:
            strong, weak, length = upload.strong, upload.weak, upload.replay_length
            if strong == 0 and weak == 0:
                # The game uploaded a silent effect: respect it.
                self._stop_rumble()
                return
        else:
            # No handshake data (unusual): legacy on/off rumble at full power.
            strong, weak, length = 0xFFFF, 0xFFFF, 0

        with self._ff_lock:
            self._playing_virt_id = virt_id
            self._rumble_generation += 1  # invalidates a pending test stop
        self._play_rumble(strong, weak, length, count)

    def _play_rumble(self, strong: int, weak: int, length_ms: int, count: int):
        """Drive the physical motors proportionally.

        Primary path: upload one FF_RUMBLE effect on the physical evdev
        device (EVIOCSFF) and play it — the kernel's ff-memless layer then
        owns timing, transport (USB/BT output reports) and gain. When the
        physical pad has no force feedback (or there is no evdev node at
        all), fall back to driving the DS4 motors through a HID output
        report via the LED controller.
        """
        # Bounded playback window: timed effects (length > 0) end on their
        # own in the kernel; "until stopped" effects are capped by the
        # watchdog so a crashed game can never leave the motors buzzing.
        # One critical section: the GUI (test_rumble) and the auto-stop
        # Timer mutate the same state/fd concurrently with this loop.
        with self._ff_lock:
            now = time.monotonic()
            if length_ms > 0:
                self._rumble_deadline = now + (max(1, int(count)) * length_ms) / 1000.0
            else:
                self._rumble_deadline = now + self.RUMBLE_STALE_S

            # A failed upload used to disable the physical FF path for the
            # rest of the session (_phys_ff_ok = False forever) — a
            # transient error (EAGAIN, busy node) would permanently degrade
            # rumble to the HID fallback. Re-probe periodically instead.
            if (
                self._phys_ff_ok is False
                and self._device is not None
                and now >= self._phys_ff_retry_at
            ):
                self._phys_ff_ok = None
                self._phys_ff_retry_at = now + self.PHYS_FF_RETRY_S

            if self._phys_ff_ok is not False and self._device is not None:
                if self._upload_and_play(strong, weak, length_ms, count):
                    self._phys_ff_ok = True
                    self._rumble_active = True
                    return
                if self._phys_ff_ok is None:
                    logger.info("Worker: physical FF unavailable — using HID rumble")
                self._phys_ff_ok = False
                self._phys_effect = None
                self._phys_effect_id = None

            if self._led_controller is not None and self._led_controller.set_rumble(strong, weak):
                self._rumble_active = True
            else:
                logger.debug("Worker: no rumble backend available")

    def _upload_and_play(self, strong: int, weak: int, length_ms: int, count: int) -> bool:
        try:
            if self._phys_effect is None:
                self._phys_effect = build_rumble_effect(
                    strong, weak, replay_length=length_ms, effect_id=-1
                )
            else:
                # Re-upload of the cached effect: evdev wrote the allocated
                # id back into the struct on the first EVIOCSFF
                # (upload_effect(writeback_id=True)), so this UPDATE the
                # existing kernel effect instead of allocating a new one —
                # no FF slot leak across repeated play events. Defense in
                # depth: if the id somehow never made it back (old kernels,
                # silent error), id == -1 would ALLOCATE a new slot per
                # play — rebuild the effect instead.
                eff = self._phys_effect
                if eff.id < 0:
                    self._phys_effect = build_rumble_effect(
                        strong, weak, replay_length=length_ms, effect_id=-1
                    )
                    eff = self._phys_effect
                eff.u.ff_rumble_effect.strong_magnitude = strong
                eff.u.ff_rumble_effect.weak_magnitude = weak
                eff.ff_replay.length = max(0, min(0xFFFF, int(length_ms)))
                eff.ff_replay.delay = 0
            self._phys_effect_id = self._device.upload_effect(self._phys_effect)
            self._device.write(e.EV_FF, self._phys_effect_id, max(1, int(count)))
            self._device.syn()
            return True
        except OSError as ex:
            logger.debug("Worker: physical FF upload/play failed: %s", ex)
            return False

    def _stop_rumble(self):
        """Stop the physical motors on both backends (idempotent)."""
        with self._ff_lock:
            if not self._rumble_active:
                return
            self._rumble_active = False
            if self._phys_ff_ok and self._device is not None and self._phys_effect_id is not None:
                try:
                    self._device.write(e.EV_FF, self._phys_effect_id, 0)
                    self._device.syn()
                except OSError as ex:
                    logger.debug("Worker: rumble stop failed: %s", ex)
            if self._led_controller is not None:
                self._led_controller.set_rumble(0, 0)

    def test_rumble(self, duration_ms: int = 500) -> bool:
        """Rumble self-test triggered from the GUI (proportional, auto-stops).

        Safe to call from the GUI thread: it only issues ioctl/write calls.
        """
        try:
            self._play_rumble(0xFFFF, 0x8000, length_ms=duration_ms, count=1)
        except Exception:
            logger.debug("Worker: rumble test failed", exc_info=True)
            return False
        # HID backend has no kernel-side timeout: schedule an explicit stop,
        # bound to THIS test run via a generation token — without it a game
        # starting real rumble between the test and the firing would get
        # its rumble killed by this Timer.
        if self._test_stop_timer is not None:
            self._test_stop_timer.cancel()
        generation = self._rumble_generation

        def _auto_stop():
            with self._ff_lock:
                if self._rumble_generation == generation:
                    self._stop_rumble()

        timer = threading.Timer(duration_ms / 1000.0, _auto_stop)
        timer.daemon = True
        timer.start()
        self._test_stop_timer = timer
        return True

    def _process_hidraw_report(self, report, write_event, sync, btn_state, axis_state,
                               mapper, EV_KEY, EV_ABS):
        """Apply one parsed HIDRAW report to the virtual device.

        Pure translation step between ``parse_ds4_report`` state and the
        virtual device: D-pad goes through ``_write_hat`` (same helper as the
        evdev path), sticks/triggers through ``InputMapper.map_axis`` and
        buttons through ``InputMapper.map_button`` (macros included — a
        macro-bound button is consumed instead of forwarded).  Change
        detection for the HAT axes relies on ``axis_state`` so both input
        paths share one source of truth.

        The returned ``(dpad_x, dpad_y)`` is the effective (post-macro)
        direction — used by tests to assert the translation; the production
        caller in ``run()`` ignores it.
        """
        profile = mapper.profile
        btn_map = profile.button_maps
        abs_map = XBOX_ABS_MAP if profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP

        # Only real DS4 input reports: anything else (unknown report id,
        # truncated BT packet) is skipped entirely — a neutral-state burst
        # would stick the virtual sticks at center.
        if (
            not report
            or len(report) < self.MIN_HIDRAW_REPORT_BYTES
            or report[0] not in (DS4_REPORT_ID_USB, DS4_REPORT_ID_BT)
        ):
            return 0, 0

        state = parse_ds4_report(report)
        dpad_x, dpad_y = state['dpad_x'], state['dpad_y']

        # Remember the DS4 status byte (battery capacity 0..11) so the
        # throttled poll has a fallback when sysfs has no power supply.
        battery = parse_ds4_battery(report)
        if battery is not None:
            self._last_battery_status = battery[0]

        # Batch the sync: one syn() per report instead of one per write
        # (mirrors the evdev path, which uses the same deferred pattern).
        wrote = [False]

        def mark_sync():
            wrote[0] = True

        prev_x = axis_state.get(e.ABS_HAT0X, 0)
        prev_y = axis_state.get(e.ABS_HAT0Y, 0)
        raw_x, raw_y = dpad_x, dpad_y
        # D-pad macros (hid-sony path fires BTN_DPAD_* macros; mirror here
        # so macro-bound directions work in HIDRAW mode too).
        dpad_x, dpad_y = self._dpad_macro_step(mapper, dpad_x, dpad_y)
        # raw_event carries the *physical* HAT, deduped against a PHYSICAL
        # tracker — axis_state stores the effective value, so a macro-bound
        # direction held down would differ from the raw value on every
        # report (~250 Hz of emits) and flood the GUI.
        prev_raw_x = self._raw_hat_prev.get(e.ABS_HAT0X, 0)
        prev_raw_y = self._raw_hat_prev.get(e.ABS_HAT0Y, 0)
        if raw_x != prev_raw_x:
            self._raw_hat_prev[e.ABS_HAT0X] = raw_x
            self.raw_event.emit(EV_ABS, e.ABS_HAT0X, raw_x)
        if raw_y != prev_raw_y:
            self._raw_hat_prev[e.ABS_HAT0Y] = raw_y
            self.raw_event.emit(EV_ABS, e.ABS_HAT0Y, raw_y)
        if (dpad_x, dpad_y) != (prev_x, prev_y):
            self._write_hat(write_event, mark_sync, abs_map, axis_state,
                            dpad_x, dpad_y, e.ABS_HAT0X, e.ABS_HAT0Y)

        for ds4_code, val in ((DS4Abs.X, state['lx']), (DS4Abs.Y, state['ly']),
                              (DS4Abs.RX, state['rx']), (DS4Abs.RY, state['ry']),
                              (DS4Abs.Z, state['l2']), (DS4Abs.RZ, state['r2'])):
            result = mapper.map_axis(ds4_code.value, val)
            if result:
                write_event(EV_ABS, result[0], result[1])
                mark_sync()
            # NOTE: raw_event always carries *physical* DS4 codes in both
            # input paths — the Readings tab maps them to DS4 widgets.
            # Deduped on physical changes: HIDRAW repeats the full state
            # every report, so emitting unconditionally flooded the GUI at
            # ~1500 emits/s with stationary sticks.
            if self._raw_axis_prev.get(ds4_code.value) != val:
                self._raw_axis_prev[ds4_code.value] = val
                self.raw_event.emit(EV_ABS, ds4_code.value, val)

        for ds4_code, pressed in state['buttons'].items():
            # Physical press/release FIRST, for EVERY button (mapped or
            # not): the Readings tab tracks all of them and the evdev path
            # emits unconditionally at the top of the loop. The raw
            # transition dedup uses its own tracker — btn_state must stay
            # untouched here or map_button's internal dedup would swallow
            # the mapped write.
            prev_raw = self._raw_btn_prev.get(ds4_code, False)
            if prev_raw != pressed:
                self._raw_btn_prev[ds4_code] = pressed
                self.raw_event.emit(EV_KEY, ds4_code, 1 if pressed else 0)
            macro_bound = mapper.is_macro_button(ds4_code)
            if not macro_bound and ds4_code not in btn_map:
                continue
            # Default False: an unpressed button on the very first report is
            # already "released", so we must not emit a burst of EV_KEY 0.
            prev_state = btn_state.get(ds4_code, False)
            if prev_state == pressed:
                continue
            # map_button handles macro execution (macro-bound buttons are
            # consumed), state tracking and the virtual code lookup in one
            # place — same entry point as the evdev path.
            result = mapper.map_button(ds4_code, 1 if pressed else 0)
            if result:
                write_event(EV_KEY, result[0], result[1])
                mark_sync()

        if wrote[0]:
            sync()
        return dpad_x, dpad_y
    def stop(self, intentional=False):
        logger.debug("Worker: stop(intentional=%s)", intentional)
        if self._test_stop_timer is not None:
            self._test_stop_timer.cancel()
            self._test_stop_timer = None
        self._intentional_stop = intentional
        self._running = False
        if not self.wait(2000):
            # Thread still winding down: leave the flag set so its finally
            # block sees the intentional stop (and clears it when done).
            # Zeroing it here was the bug — a slow exit emitted
            # device_disconnected and tore down a restarted session.
            logger.debug("Worker: stop() timed out — thread still exiting")
            return
        self._intentional_stop = False

    def is_device_connected(self) -> bool:
        return (self._device is not None or self._hidraw_reader is not None) and self.isRunning()
