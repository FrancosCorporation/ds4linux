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

    device_added = Signal(str)       # hidraw path
    device_removed = Signal(str)
    scan_finished = Signal(list)     # list of initial paths

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
            self._monitor.filter_by(subsystem="hidraw")
        except Exception as e:
            logger.error(f"pyudev error: {e}")
            self._running = False
            return

        # Use QTimer to poll for events every 500ms
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start(500)

    def _poll_events(self) -> None:
        if not self._monitor or not self._running:
            return
        try:
            # poll() returns a single Action or None
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

    def _check_and_emit(self, path: str, added: bool) -> None:
        try:
            dev = evdev.InputDevice(path)
            if dev.info.vendor != DS4_VID or dev.info.product not in DS4_PIDS:
                return
        except (OSError, PermissionError):
            return

        if added:
            self.device_added.emit(path)
        else:
            self.device_removed.emit(path)

    def _scan_existing(self) -> None:
        paths: List[str] = []
        for p in evdev.list_devices():
            try:
                dev = evdev.InputDevice(p)
                if dev.info.vendor == DS4_VID and dev.info.product in DS4_PIDS:
                    paths.append(p)
            except (OSError, PermissionError):
                continue

        self.scan_finished.emit(paths)