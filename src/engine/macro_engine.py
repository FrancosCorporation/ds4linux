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
        self._stopped = False
        self._worker: threading.Thread | None = None
        self.dropped = 0  # macros discarded because the queue was full

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute_macro(self, actions: list[MacroAction]) -> bool:
        """Queue one macro run; returns False when it had to be dropped."""
        if not actions:
            return False
        with self._lock:
            if self._stopped:
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
        """Stop the worker thread (idempotent)."""
        with self._lock:
            self._stopped = True
            worker = self._worker
            self._worker = None
        self._wake.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout)

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
            if actions is None:
                self._wake.wait(self.IDLE_POLL_S)
                self._wake.clear()
                continue
            self._run_macro(actions)

    def _run_macro(self, actions: list[MacroAction]) -> None:
        for action in actions:
            try:
                if action.action_type == "wait":
                    self._sleep(action.delay)
                elif action.action_type == "key":
                    self.vdev.write_event(EV_KEY, action.code, action.value)
                    self.vdev.sync()
                    if action.delay > 0:
                        self._sleep(action.delay)
            except Exception:
                logger.debug("Macro step failed", exc_info=True)
                break

    @classmethod
    def _sleep(cls, seconds: float) -> None:
        try:
            delay = float(seconds)
        except (TypeError, ValueError):
            return
        if delay > 0:
            time.sleep(min(delay, cls.MAX_DELAY_S))
