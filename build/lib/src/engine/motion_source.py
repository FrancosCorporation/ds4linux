"""DS4 motion (accelerometer/gyroscope) source for the DSU server.

Parses raw DS4 HID input reports from hidraw — independent of whether the
evdev node is grabbed — and exposes the latest sample through
``DS4MotionProvider`` (a ``MotionProvider`` for ``CemuHookServer``).

Report layout (hid-playstation ``dualshock4_input_report_common``):
  USB report 0x01: common starts at byte 1  (64 bytes total)
  BT  report 0x11: common starts at byte 3  (78 bytes total)
  common: buttons @4..8, sensor_timestamp @9, temperature @11,
          gyro x/y/z int16 LE @12/14/16, accel x/y/z int16 LE @18/20/22,
          status[0] @29 (battery capacity bits 0..3, cable bit 4)

Scaling (hid-playstation constants):
  accel raw / 8192  -> g
  gyro  raw / 1024  -> deg/s

Axis convention (controller flat, touchpad up, USB edge away from the
player): X forward, Y right, Z up.  DSU mapping:
  pitch = gyro Y (rotation about the right axis), yaw = gyro Z,
  roll = gyro X (rotation about the forward axis).
"""
from __future__ import annotations

import logging
import os
import select
import struct
import threading
from pathlib import Path

from .cemuhook_server import MotionProvider, dsu_battery_status

logger = logging.getLogger(__name__)

ACCEL_LSB_PER_G = 8192.0
GYRO_LSB_PER_DEG_S = 1024.0

_COMMON_MOTION_MIN = 24  # need through accel z at common+23
_USB_BASE = 1
_BT_BASE = 3
_STATUS0_BATTERY_CAPACITY = 0x0F
_STATUS0_CABLE_STATE = 0x10


def _motion_offsets(report: bytes) -> int | None:
    """Return the common-struct base offset for a motion-capable report."""
    if not report:
        return None
    report_id = report[0]
    if report_id == 0x01 and len(report) >= _USB_BASE + _COMMON_MOTION_MIN:
        return _USB_BASE
    if report_id == 0x11 and len(report) >= _BT_BASE + _COMMON_MOTION_MIN:
        return _BT_BASE
    return None


def parse_ds4_motion(report: bytes) -> tuple[float, float, float, float, float, float] | None:
    """Extract (accel_x, accel_y, accel_z, pitch, yaw, roll) from a report.

    Returns ``None`` for reports without motion data (unknown report id or
    too short, e.g. the minimal BT report).
    """
    base = _motion_offsets(report)
    if base is None:
        return None
    gyro = struct.unpack_from("<3h", report, base + 12)
    accel = struct.unpack_from("<3h", report, base + 18)
    return (
        accel[0] / ACCEL_LSB_PER_G,
        accel[1] / ACCEL_LSB_PER_G,
        accel[2] / ACCEL_LSB_PER_G,
        gyro[1] / GYRO_LSB_PER_DEG_S,  # pitch
        gyro[2] / GYRO_LSB_PER_DEG_S,  # yaw
        gyro[0] / GYRO_LSB_PER_DEG_S,  # roll
    )


def parse_ds4_battery(report: bytes) -> tuple[int, bool] | None:
    """Return (capacity 0..11, charging) from a report's status byte."""
    base = _motion_offsets(report)
    if base is None or len(report) < base + 30:
        return None
    status0 = report[base + 29]
    return status0 & _STATUS0_BATTERY_CAPACITY, bool(status0 & _STATUS0_CABLE_STATE)


def detect_hid_transport(hidraw_path: str) -> str | None:
    """'usb' / 'bt' from sysfs HID_ID (bus 0003 usb, 0005 bluetooth)."""
    try:
        uevent = (
            Path("/sys/class/hidraw")
            / Path(hidraw_path).name
            / "device"
            / "uevent"
        ).read_text()
    except OSError:
        return None
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            parts = line.split(":", 1)
            if len(parts) == 2:
                bus = parts[1].strip()[:4]
                if bus.startswith("0003"):
                    return "usb"
                if bus.startswith("0005"):
                    return "bt"
    return None


def read_hid_uniq(hidraw_path: str) -> str | None:
    """Device MAC ('aa:bb:cc:dd:ee:ff') from sysfs HID_UNIQ, if present."""
    try:
        uevent = (
            Path("/sys/class/hidraw")
            / Path(hidraw_path).name
            / "device"
            / "uevent"
        ).read_text()
    except OSError:
        return None
    for line in uevent.splitlines():
        if line.startswith("HID_UNIQ="):
            value = line.split("=", 1)[1].strip()
            return value or None
    return None


class DS4MotionProvider(MotionProvider):
    """Thread-safe holder of the latest DS4 motion sample + battery."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sample = (0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        self._battery = 0

    def update(self, sample) -> None:
        with self._lock:
            self._sample = sample

    @property
    def battery(self) -> int:
        with self._lock:
            return self._battery

    @battery.setter
    def battery(self, value: int) -> None:
        # Locked like the sample: the reader thread writes it while the DSU
        # UDP thread reads it for the info/motors replies.
        with self._lock:
            self._battery = value

    def get_motion(self) -> tuple[float, float, float, float, float, float]:
        with self._lock:
            return self._sample


class DS4MotionReader(threading.Thread):
    """Reads raw DS4 input reports from hidraw and feeds a provider."""

    def __init__(self, hidraw_path: str, provider: DS4MotionProvider):
        super().__init__(name=f"ds4-motion-{Path(hidraw_path).name}", daemon=True)
        self._path = hidraw_path
        self._provider = provider
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()
        # Guard against self-join (would raise RuntimeError): stop() is
        # always called from another thread today, but a future callback
        # from the reader itself must not deadlock on it.
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=1.0)

    def run(self) -> None:
        try:
            fd = os.open(self._path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as ex:
            logger.warning(f"DS4MotionReader: cannot open {self._path}: {ex}")
            return
        try:
            while not self._stop_event.is_set():
                try:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                try:
                    data = os.read(fd, 256)
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError:
                    break
                if not data:
                    break  # EOF (e.g. device gone)
                sample = parse_ds4_motion(data)
                if sample is not None:
                    self._provider.update(sample)
                battery = parse_ds4_battery(data)
                if battery is not None:
                    capacity, charging = battery
                    self._provider.battery = dsu_battery_status(capacity, charging)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
