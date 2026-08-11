from __future__ import annotations

import evdev
import pyudev
from typing import List, Optional
import logging

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from ..constants import DS4_VID, DS4_PIDS

logger = logging.getLogger(__name__)


class DeviceMonitor(QObject):
    """
    Monitors udev/hidraw for DS4 hot-plug events.
    Runs in a background QThread with a QTimer that polls pyudev Monitor.
    Emits device_added / device_removed signals when a DS4 is connected/disconnected.
    """

    device_added = Signal(str)        # input event path (e.g. /dev/input/event27)
    device_removed = Signal(str)
    scan_finished = Signal(list)      # list of initial paths

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._ctx: Optional[pyudev.Context] = None
        self._monitor: Optional[pyudev.Monitor] = None
        self._running = False
        self._thread: Optional[QThread] = None
        self._timer: Optional[QTimer] = None

    def start(self) -> None:
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._init)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)

    def _init(self) -> None:
        self._running = True
        self._scan_existing()

        try:
            self._ctx = pyudev.Context()
            self._monitor = pyudev.Monitor.from_netlink(self._ctx)
            self._monitor.filter_by(subsystem="input")
        except Exception as e:
            logger.error(f"pyudev error: {e}")
            self._running = False
            return

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start(500)

    def _poll_events(self) -> None:
        if not self._monitor or not self._running:
            return
        try:
            device = self._monitor.poll(timeout=0.1)
            if device:
                self._on_udev_event(device)
        except (BlockingIOError, InterruptedError):
            pass

    def _on_udev_event(self, device: pyudev.Device) -> None:
        if device.action == "add" and device.device_node:
            self._check_and_emit(device.device_node, added=True)
        elif device.action == "remove" and device.device_node:
            self._check_and_emit(device.device_node, added=False)

    def _is_real_ds4(self, device_path: str) -> bool:
        """Check if a device is a genuine DS4 (not virtual uinput)."""
        try:
            dev = evdev.InputDevice(device_path)
            # Skip virtual uinput devices
            if "uinput" in (dev.phys or "").lower():
                return False
            # Must be a DS4 vendor and recognized PID
            if dev.info.vendor != DS4_VID or dev.info.product not in DS4_PIDS:
                return False
            # Must have button capabilities (a real controller, not a sound device)
            caps = dev.capabilities()
            # EV_KEY = 0x01, check for button events
            if 0x01 not in caps:
                return False
            # Verify it has typical DS4 buttons
            keys = caps[0x01]  # EV_KEY
            has_ds4_btn = any(k in keys for k in (
                0x130, 0x131, 0x133, 0x134,  # cross/circle/square/triangle
            ))
            return has_ds4_btn
        except (OSError, PermissionError):
            return False

    def _check_and_emit(self, device_path: str, added: bool) -> None:
        if not self._is_real_ds4(device_path):
            return

        if added:
            self.device_added.emit(device_path)
        else:
            self.device_removed.emit(device_path)

    def _scan_existing(self) -> None:
        paths: List[str] = []
        for p in evdev.list_devices():
            if self._is_real_ds4(p):
                paths.append(p)
        self.scan_finished.emit(paths)