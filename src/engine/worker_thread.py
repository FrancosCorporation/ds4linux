import errno
import logging
import select
import threading
import time

from evdev import InputDevice
from evdev import ecodes as e
from PySide6.QtCore import QThread, Signal

from ..constants import DS4Abs
from .battery import battery_percent_from_status, battery_percent_from_sysfs
from .dpad import DOWN, LEFT, RIGHT, UP, hat_from_directions
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
from .virtual_device import VirtualDevice

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
    # latest emitted level; None means unknown while 0 is a valid reading).
    BATTERY_POLL_S = 30.0

    device_connected = Signal(object)
    device_disconnected = Signal()
    battery_update = Signal(int)
    log_message = Signal(str)
    raw_event = Signal(int, int, int)
    mapped_event = Signal(int, int, int)
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
        # None means unknown; 0 is a valid empty-battery measurement.
        self._last_battery_level: int | None = None
        self._last_battery_status: int | None = None
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
        # Each physical driver representation is normalized into the same
        # four logical directions before applying the profile mappings.
        self._dpad_sources: dict[str, set[int]] = {}
        self._dpad_effective: set[int] = set()
        self._dpad_target_sources: dict[int, set[int]] = {}
        self._dpad_hat_output_active = False
        self._dpad_hat_input = {e.ABS_HAT0X: 0, e.ABS_HAT0Y: 0}

    # All setters below MUST be called from the GUI thread BEFORE start();
    # run() reads them on the worker thread and never mutates them.
    def _ensure_setup_phase(self, setter: str):
        if self.isRunning():
            logger.warning("Worker: %s called while the thread is running", setter)

    def set_virtual_device(self, vdev: VirtualDevice):
        self._ensure_setup_phase("set_virtual_device")
        if self._virtual_device is not None:
            remove_observer = getattr(self._virtual_device, "set_event_observer", None)
            if remove_observer is not None:
                remove_observer(None)
        self._virtual_device = vdev
        add_observer = getattr(vdev, "set_event_observer", None)
        if add_observer is not None:
            add_observer(self.mapped_event.emit)

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
                    logger.info("Worker: rumble reader on %s (fd=%s)", path, self._rumble_dev.fd)
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

    def _read_battery(self) -> int | None:
        """Battery 0-100, or None when it cannot be read.

        Sources, in order: the kernel power supply next to the HID device
        (hid-sony/hid-playstation), then the last DS4 status byte seen on
        the HIDRAW path.  The old code called ``self._device.device.
        read_feature_report`` which does not exist on evdev devices, so
        every read raised AttributeError and the signal never fired.
        """
        hidraw_path = self._hidraw_reader.hidraw_path if self._hidraw_reader else None
        if hidraw_path is None and self._device is not None:
            try:
                hidraw_path = find_ds4_hidraw(getattr(self._device, "uniq", None))
            except Exception:
                hidraw_path = None
        level = battery_percent_from_sysfs(hidraw_path)
        if level is None and self._last_battery_status is not None:
            level = battery_percent_from_status(self._last_battery_status)
        return level

    def _maybe_emit_battery(self) -> None:
        """Poll battery and emit on change (throttled by TIME, not by tick).
        Unknown reads (None) are not emitted; zero percent remains valid."""
        now = time.monotonic()
        if now - self._last_battery_poll < self.BATTERY_POLL_S:
            return
        self._last_battery_poll = now
        level = self._read_battery()
        if level is not None and level != self._last_battery_level:
            self._last_battery_level = level
            self.battery_update.emit(level)

    # ------------------------------------------------------------------
    # D-pad helpers (BTN_DPAD_* -> ABS_HAT0X/ABS_HAT0Y)
    # ------------------------------------------------------------------
    @staticmethod
    def _dpad_codes_for_hat(x: int, y: int) -> set[int]:
        directions = set()
        if x < 0:
            directions.add(e.BTN_DPAD_LEFT)
        elif x > 0:
            directions.add(e.BTN_DPAD_RIGHT)
        if y < 0:
            directions.add(e.BTN_DPAD_UP)
        elif y > 0:
            directions.add(e.BTN_DPAD_DOWN)
        return directions

    def _process_dpad_key(self, code: int, value: int, mapper, write_event, mark_sync) -> None:
        if code not in (e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT):
            return
        directions = set(self._dpad_sources.get("evdev-key", set()))
        if value in (1, 2):
            directions.add(code)
        elif value == 0:
            directions.discard(code)
        else:
            return
        self._set_dpad_source("evdev-key", directions, mapper, write_event, mark_sync)

    def _process_dpad_hat(self, code: int, value: int, mapper, write_event, mark_sync) -> None:
        if code not in (e.ABS_HAT0X, e.ABS_HAT0Y):
            return
        self._dpad_hat_input[code] = -1 if value < 0 else (1 if value > 0 else 0)
        self._set_dpad_source(
            "evdev-hat",
            self._dpad_codes_for_hat(
                self._dpad_hat_input[e.ABS_HAT0X],
                self._dpad_hat_input[e.ABS_HAT0Y],
            ),
            mapper,
            write_event,
            mark_sync,
        )

    def _set_dpad_source(self, source: str, directions: set[int], mapper, write_event, mark_sync) -> None:
        """Apply normalized D-pad directions through the configured mapping.

        Opposites cancel according to Linux HAT semantics. BTN_DPAD events,
        evdev HAT axes, and HIDRAW reports all reach this function, so macros,
        removed bindings, remaps, repeat handling and destination refcounts
        behave identically for every physical driver.
        """
        self._dpad_sources[source] = set(directions)
        combined = set().union(*self._dpad_sources.values()) if self._dpad_sources else set()
        x, y = hat_from_directions(
            direction
            for direction, active in (
                (LEFT, e.BTN_DPAD_LEFT in combined),
                (RIGHT, e.BTN_DPAD_RIGHT in combined),
                (UP, e.BTN_DPAD_UP in combined),
                (DOWN, e.BTN_DPAD_DOWN in combined),
            )
            if active
        )
        effective = self._dpad_codes_for_hat(x, y)
        previous = self._dpad_effective
        self._dpad_effective = effective
        dpad_targets = {
            e.BTN_DPAD_UP,
            e.BTN_DPAD_DOWN,
            e.BTN_DPAD_LEFT,
            e.BTN_DPAD_RIGHT,
        }
        hat_mode = mapper.profile.dpad_output_mode == "hat"
        for code in (e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT):
            was_pressed, pressed = code in previous, code in effective
            if was_pressed == pressed:
                continue
            target_before = mapper.written_virtual.get(code)
            result = mapper.map_button(code, int(pressed))
            if pressed:
                target_after = mapper.written_virtual.get(code)
                if hat_mode and target_after in dpad_targets:
                    self._dpad_target_sources.setdefault(target_after, set()).add(code)
                elif result:
                    write_event(e.EV_KEY, result[0], result[1])
                    mark_sync()
            elif hat_mode and target_before in dpad_targets:
                sources = self._dpad_target_sources.get(target_before)
                if sources is not None:
                    sources.discard(code)
                    if not sources:
                        self._dpad_target_sources.pop(target_before, None)
            elif result:
                write_event(e.EV_KEY, result[0], result[1])
                mark_sync()

        if hat_mode:
            target_directions = set(self._dpad_target_sources)
            tx, ty = hat_from_directions(
                direction
                for direction, code in (
                    (LEFT, e.BTN_DPAD_LEFT),
                    (RIGHT, e.BTN_DPAD_RIGHT),
                    (UP, e.BTN_DPAD_UP),
                    (DOWN, e.BTN_DPAD_DOWN),
                )
                if code in target_directions
            )
            if target_directions or self._dpad_hat_output_active:
                for ds4_axis, value in ((DS4Abs.HAT0X, tx), (DS4Abs.HAT0Y, ty)):
                    result = mapper.map_hat(ds4_axis, value)
                    if result:
                        write_event(e.EV_ABS, result[0], result[1])
                        mark_sync()
                self._dpad_hat_output_active = bool(tx or ty)

    @staticmethod
    def _flush_pending_sync(pending_sync, sync) -> None:
        if pending_sync[0]:
            sync()
            pending_sync[0] = False

    def _process_evdev_events(
        self, events, device, mapper, write_event, sync, pending_sync, axis_infos=None
    ) -> None:
        """Translate one evdev read while preserving SYN frame boundaries.

        After SYN_DROPPED the kernel stream is unreliable until SYN_REPORT;
        discard that frame tail, query the device's current state, and emit
        only the necessary transitions into the virtual controller.
        """
        dropped = False
        dpad_keys = {
            e.BTN_DPAD_UP,
            e.BTN_DPAD_DOWN,
            e.BTN_DPAD_LEFT,
            e.BTN_DPAD_RIGHT,
        }
        for event in events:
            if event.type == e.EV_SYN:
                if event.code == e.SYN_DROPPED:
                    self._flush_pending_sync(pending_sync, sync)
                    dropped = True
                elif event.code == e.SYN_REPORT:
                    if dropped:
                        self._recover_evdev_state(
                            device,
                            mapper,
                            write_event,
                            pending_sync,
                        )
                        dropped = False
                    self._flush_pending_sync(pending_sync, sync)
                continue
            if dropped:
                continue

            if event.type in (e.EV_KEY, e.EV_ABS):
                self.raw_event.emit(event.type, event.code, event.value)

            if event.type == e.EV_KEY:
                if event.code in dpad_keys:
                    self._process_dpad_key(
                        event.code,
                        event.value,
                        mapper,
                        write_event,
                        lambda: pending_sync.__setitem__(0, True),
                    )
                    continue
                result = mapper.map_button(event.code, event.value)
                if result:
                    write_event(e.EV_KEY, result[0], result[1])
                    pending_sync[0] = True
            elif event.type == e.EV_ABS:
                if event.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                    self._process_dpad_hat(
                        event.code,
                        event.value,
                        mapper,
                        write_event,
                        lambda: pending_sync.__setitem__(0, True),
                    )
                    continue
                results = mapper.map_axes(
                    event.code,
                    event.value,
                    (axis_infos or {}).get(event.code),
                )
                for result in results:
                    write_event(e.EV_ABS, result[0], result[1])
                    pending_sync[0] = True

        # Some devices/drivers omit SYN_REPORT or a fake/read chunk may end
        # mid-frame; make sure already translated state is never stranded.
        self._flush_pending_sync(pending_sync, sync)

    def _recover_evdev_state(self, device, mapper, write_event, pending_sync) -> None:
        """Reconcile mapped keys and axes after the kernel reports data loss."""
        try:
            active_keys = set(device.active_keys())
        except (AttributeError, OSError) as ex:
            logger.warning("Worker: cannot query active keys after SYN_DROPPED: %s", ex)
            active_keys = None

        try:
            capabilities = device.capabilities(absinfo=False)
        except (AttributeError, OSError, TypeError) as ex:
            logger.warning("Worker: cannot query capabilities after SYN_DROPPED: %s", ex)
            capabilities = {}

        def mark_sync():
            pending_sync[0] = True

        if active_keys is not None:
            key_codes = set(capabilities.get(e.EV_KEY, ()))
            key_codes.update(mapper.button_state)
            key_codes.update(mapper.profile.button_maps)
            key_codes.update(mapper.profile.macros)
            key_codes.update((e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT))

            for code in key_codes:
                pressed = code in active_keys
                if mapper.button_state.get(code, False) == pressed:
                    continue
                self.raw_event.emit(e.EV_KEY, code, int(pressed))
                if code in (e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT):
                    self._process_dpad_key(code, int(pressed), mapper, write_event, mark_sync)
                else:
                    result = mapper.map_button(code, int(pressed))
                    if result:
                        write_event(e.EV_KEY, result[0], result[1])
                        mark_sync()

        abs_codes = set(capabilities.get(e.EV_ABS, ()))
        for code in sorted(abs_codes):
            try:
                axis_info = device.absinfo(code)
                value = axis_info.value
            except (AttributeError, OSError, TypeError) as ex:
                logger.debug("Worker: cannot query ABS_%s after SYN_DROPPED: %s", code, ex)
                continue
            self.raw_event.emit(e.EV_ABS, code, value)
            if code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                self._process_dpad_hat(code, value, mapper, write_event, mark_sync)
            else:
                results = mapper.map_axes(code, value, axis_info)
                for result in results:
                    write_event(e.EV_ABS, result[0], result[1])
                    mark_sync()

    def run(self):
        if not self._virtual_device or not self._input_mapper:
            self._fail_startup("Worker: missing virtual_device or input_mapper — aborting")
            return

        if self._device is not None and not self._device_grabbed:
            self._fail_startup(
                "Worker: exclusive evdev grab is required; HIDRAW fallback would duplicate game input"
            )
            return

        vdev = self._virtual_device
        if not vdev.is_active():
            if not vdev.create():
                self._fail_startup("Worker: failed to create virtual device — aborting")
                return
            logger.info("Worker: virtual device created (fd=%s)", vdev.uinput_fd)
        else:
            logger.debug("Worker: virtual device already active (fd=%s)", vdev.uinput_fd)

        # An exclusive evdev grab is required whenever an evdev node exists.
        # HIDRAW is used only for explicit reader-only operation.
        use_hidraw = False
        if self._device is None:
            logger.info("Worker: no evdev device — using HIDRAW")
            use_hidraw = True
        else:
            logger.info("Worker: evdev mode on %s (grabbed)", self._device.path)

        # ------------------------------------------------------------------
        # Open HIDRAW if needed
        # ------------------------------------------------------------------
        if use_hidraw:
            uniq = getattr(self._device, "uniq", None) if self._device else None
            input_path = getattr(self._device, "path", None) if self._device else None
            hidraw_path = find_ds4_hidraw(uniq, input_device_path=input_path)
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
        self._dpad_sources = {}
        self._dpad_effective = set()
        self._dpad_target_sources = {}
        self._dpad_hat_output_active = False
        self._dpad_hat_input = {e.ABS_HAT0X: 0, e.ABS_HAT0Y: 0}
        self._raw_axis_prev = {}
        self._raw_btn_prev = {}
        self._raw_hat_prev = {}
        self._last_battery_level = None
        self._last_battery_status = None
        # 'overdue', not 0.0: on a fresh boot (monotonic() < BATTERY_POLL_S)
        # a 0.0 reset would delay the first battery poll by up to 30 s.
        self._last_battery_poll = time.monotonic() - self.BATTERY_POLL_S - 1
        self.device_connected.emit(self._device)

        mapper = self._input_mapper
        sync = vdev.sync

        def write_event(event_type: int, code: int, value: int):
            return vdev.write_event(event_type, code, value)

        # Batched sync: writes are queued through the deferred marker and the
        # real syn() happens once per input batch, not per event.
        pending_sync = [False]

        def mark_sync():
            pending_sync[0] = True

        EV_KEY = e.EV_KEY
        EV_ABS = e.EV_ABS
        EV_FF = e.EV_FF
        # Release sweep: the mapper's pressed-state cache survives worker
        # restarts, but the virtual device may have been recreated (slot
        # reconnect) or left with a pressed key (worker died mid-press,
        # profile swap). Emit EV_KEY 0 for everything the previous run
        # believed was down, then start clean — otherwise a release that
        # happens while the worker is stopped is swallowed by stale dedup
        # state and the virtual button sticks until the next full pair.
        self.release_stuck_buttons(mapper, write_event, sync)

        axis_infos = {}
        if self._device is not None and not use_hidraw:
            for code in (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY, e.ABS_Z, e.ABS_RZ):
                try:
                    axis_infos[code] = self._device.absinfo(code)
                except (AttributeError, OSError):
                    logger.debug("No AbsInfo for physical axis %s", code)

        phys_fd = self._device.fd if (self._device and not use_hidraw) else -1
        virt_fd = vdev.uinput_fd
        hidraw_fd = self._hidraw_fd

        logger.debug("Worker: loop fds phys=%s virt=%s hidraw=%s", phys_fd, virt_fd, hidraw_fd)

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
                        events = (event for event in self._device.read() if self._running)
                        self._process_evdev_events(
                            events,
                            self._device,
                            mapper,
                            write_event,
                            sync,
                            pending_sync,
                            axis_infos,
                        )
                        consecutive_errors = 0
                    except (BlockingIOError, InterruptedError):
                        # Nonblocking evdev reads can race select(), and a
                        # signal may interrupt a read; neither means unplug.
                        continue
                    except OSError as ex:
                        if ex.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                            continue
                        logger.error("Worker: evdev read OSError: %s", ex)
                        break
                    except Exception as ex:
                        consecutive_errors += 1
                        logger.error(
                            "Worker: evdev unexpected error (%s/%s): %s: %s",
                            consecutive_errors,
                            self.MAX_CONSECUTIVE_ERRORS,
                            type(ex).__name__,
                            ex,
                        )
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
                                report,
                                write_event,
                                mark_sync,
                                mapper.button_state,
                                mapper.axis_state,
                                mapper,
                                EV_KEY,
                                EV_ABS,
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
                        logger.error(
                            "Worker: hidraw error (%s/%s): %s: %s",
                            consecutive_errors,
                            self.MAX_CONSECUTIVE_ERRORS,
                            type(ex).__name__,
                            ex,
                        )
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
            try:
                self.release_stuck_buttons(mapper, write_event, sync)
            except Exception:
                logger.exception("Worker: failed to neutralize virtual output during shutdown")
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
        for virtual_code in set(mapper.written_axes.values()):
            write_event(e.EV_ABS, virtual_code, 0)
            wrote = True
        self._dpad_sources.clear()
        self._dpad_effective.clear()
        self._dpad_target_sources.clear()
        self._dpad_hat_output_active = False
        self._dpad_hat_input = {e.ABS_HAT0X: 0, e.ABS_HAT0Y: 0}
        for ds4_code, was_pressed in list(mapper.button_state.items()):
            if was_pressed:
                # InputMapper retains the actual destination and reference
                # counts, so duplicate mappings produce only the final up.
                result = mapper.map_button(ds4_code, 0)
                if result:
                    write_event(e.EV_KEY, result[0], result[1])
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
            if self._phys_ff_ok is False and self._device is not None and now >= self._phys_ff_retry_at:
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
                self._phys_effect = build_rumble_effect(strong, weak, replay_length=length_ms, effect_id=-1)
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

    def _process_hidraw_report(
        self, report, write_event, sync, btn_state, axis_state, mapper, EV_KEY, EV_ABS
    ):
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
        dpad_x, dpad_y = state["dpad_x"], state["dpad_y"]

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

        raw_x, raw_y = dpad_x, dpad_y
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
        self._set_dpad_source(
            "hidraw",
            self._dpad_codes_for_hat(raw_x, raw_y),
            mapper,
            write_event,
            mark_sync,
        )

        for ds4_code, val in (
            (DS4Abs.X, state["lx"]),
            (DS4Abs.Y, state["ly"]),
            (DS4Abs.RX, state["rx"]),
            (DS4Abs.RY, state["ry"]),
            (DS4Abs.Z, state["l2"]),
            (DS4Abs.RZ, state["r2"]),
        ):
            results = mapper.map_axes(ds4_code.value, val)
            for result in results:
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

        for ds4_code, pressed in state["buttons"].items():
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
