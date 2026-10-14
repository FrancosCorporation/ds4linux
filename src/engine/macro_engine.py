"""Button-macro execution on the virtual device.

A single daemon worker drains a bounded FIFO queue, so a mash of macro
presses can never spawn unbounded threads or interleave the writes of two
runs of the same macro. Steps are validated (delay clamped) before they run
so a hostile/broken profile cannot park the worker for minutes.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# evdev EV_KEY (kept local so importing this module stays cheap)
EV_KEY = 0x01


class MacroAction:
    def __init__(self, action_type: str, code: int, value: int, delay: float = 0.0):
        self.action_type = action_type  # 'key' or 'wait'
        self.code = code
        self.value = value
        self.delay = delay


class MacroEngine:
    """Executes queued macros against the virtual uinput device."""

    # Bounded FIFO: when full, the oldest pending macro is dropped so the
    # newest presses stay responsive.
    MAX_PENDING = 32
    # Upper bound for any single step delay (matches ProfileManager clamp).
    MAX_DELAY_S = 10.0
    # Idle worker poll interval (wakeup is event-driven; this is a safety net).
    IDLE_POLL_S = 0.5

    def __init__(self, virtual_device):
        self.vdev = virtual_device
        self._pending: list[list[MacroAction]] = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._interrupt = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._generation = 0
        self._stopped = False
        self._paused = False
        self._worker: threading.Thread | None = None
        self._pressed_keys: set[int] = set()
        self.dropped = 0  # macros discarded because the queue was full

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute_macro(self, actions: list[MacroAction]) -> bool:
        """Queue one macro run; returns False when it had to be dropped."""
        if not actions:
            return False
        with self._lock:
            if self._stopped or self._paused:
                return False
            if len(self._pending) >= self.MAX_PENDING:
                self._pending.pop(0)
                self.dropped += 1
                logger.debug("Macro queue full — dropped oldest (dropped=%d)",
                             self.dropped)
            self._pending.append(list(actions))
            worker = self._ensure_worker_locked()
        self._wake.set()
        return worker is not None

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def shutdown(self, timeout: float = 1.0) -> None:
        """Cancel active output and stop the worker thread permanently."""
        with self._lock:
            self._stopped = True
            self._generation += 1
            self._pending.clear()
            worker = self._worker
            self._interrupt.set()
        self._wake.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout)

    def cancel_all(self, timeout: float = 1.0) -> bool:
        """Discard queued macros and wait until active keys have been released.

        The engine remains reusable after cancellation, for example when a
        profile is replaced while its virtual device stays alive.
        """
        return self._cancel_pending(timeout, pause=False)

    def pause_and_cancel(self, timeout: float = 1.0) -> bool:
        """Block new macro submissions and drain active output safely."""
        return self._cancel_pending(timeout, pause=True)

    def _cancel_pending(self, timeout: float, pause: bool) -> bool:
        with self._lock:
            self._generation += 1
            self._paused = pause
            self._pending.clear()
            worker = self._worker
            self._interrupt.set()
        self._wake.set()
        if worker is not None and worker.is_alive():
            finished = self._idle.wait(max(0.0, timeout))
        else:
            finished = self._idle.is_set()
        if finished:
            if not pause:
                self._interrupt.clear()
        return finished

    def resume(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._paused = False
            self._interrupt.clear()
        self._wake.set()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------
    def _ensure_worker_locked(self) -> threading.Thread | None:
        if self._worker is None or not self._worker.is_alive():
            if self._stopped:
                return None
            self._worker = threading.Thread(
                target=self._run_loop, name="ds4linux-macro-engine", daemon=True
            )
            self._worker.start()
        return self._worker

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if self._stopped:
                    return
                actions = self._pending.pop(0) if self._pending else None
                if actions is not None:
                    self._idle.clear()
            if actions is None:
                self._wake.wait(self.IDLE_POLL_S)
                self._wake.clear()
                continue
            try:
                with self._lock:
                    generation = self._generation
                self._run_macro(actions, generation)
            finally:
                self._idle.set()

    def _run_macro(self, actions: list[MacroAction], generation: int) -> None:
        for action in actions:
            if self._is_cancelled(generation):
                self._release_active_keys()
                return
            try:
                if action.action_type == "wait":
                    if self._wait_interruptible(action.delay, generation):
                        self._release_active_keys()
                        return
                elif action.action_type == "key":
                    self.vdev.write_event(EV_KEY, action.code, action.value)
                    self.vdev.sync()
                    if action.value == 0:
                        self._pressed_keys.discard(action.code)
                    else:
                        self._pressed_keys.add(action.code)
                    if action.delay > 0:
                        if self._wait_interruptible(action.delay, generation):
                            self._release_active_keys()
                            return
            except Exception:
                logger.debug("Macro step failed", exc_info=True)
                break
        self._release_active_keys()

    def _is_cancelled(self, generation: int) -> bool:
        with self._lock:
            return self._stopped or generation != self._generation

    def _wait_interruptible(self, seconds: float, generation: int) -> bool:
        delay = self._bounded_delay(seconds)
        if delay <= 0:
            return self._is_cancelled(generation)
        return self._interrupt.wait(delay) or self._is_cancelled(generation)

    def _release_active_keys(self) -> None:
        for code in tuple(self._pressed_keys):
            try:
                self.vdev.write_event(EV_KEY, code, 0)
                self.vdev.sync()
            except Exception:
                logger.warning("Could not release macro key %s", code, exc_info=True)
            finally:
                self._pressed_keys.discard(code)

    @classmethod
    def _bounded_delay(cls, seconds: float) -> float:
        try:
            delay = float(seconds)
        except (TypeError, ValueError):
            return 0.0
        return min(delay, cls.MAX_DELAY_S) if delay > 0 else 0.0

    @classmethod
    def _sleep(cls, seconds: float) -> None:
        delay = cls._bounded_delay(seconds)
        if delay > 0:
            time.sleep(delay)
