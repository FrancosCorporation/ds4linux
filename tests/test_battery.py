"""Battery source tests: sysfs power supply + DS4 status byte.

Regression for the read path that used ``InputDevice.device.
read_feature_report`` (AttributeError on evdev devices — the GUI battery
column never updated from ``--``).
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import src.engine.battery as battery_mod
from src.engine.battery import battery_percent_from_status, battery_percent_from_sysfs


class TestStatusByte(unittest.TestCase):
    def test_capacity_mapping(self):
        self.assertEqual(battery_percent_from_status(0), 0)
        self.assertEqual(battery_percent_from_status(11), 100)
        # Half capacity (5/11) rounds to 45%
        self.assertEqual(battery_percent_from_status(5), 45)

    def test_reserved_values_saturate_to_full(self):
        # hid-playstation documents 0..11; anything above is reserved.
        self.assertEqual(battery_percent_from_status(12), 100)
        self.assertEqual(battery_percent_from_status(15), 100)

    def test_ignores_non_capacity_bits(self):
        # Cable/charging bits above 0x0F must not leak into the percent.
        self.assertEqual(battery_percent_from_status(11 | 0x10 | 0x80), 100)


class TestSysfsSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = battery_mod._SYSFS_HIDRAW
        battery_mod._SYSFS_HIDRAW = Path(self._tmp.name)
        self.hidraw = Path(self._tmp.name) / "hidraw3"
        psy = self.hidraw / "device" / "power_supply" / "ps-controller-battery-0"
        psy.mkdir(parents=True)
        self.capacity = psy / "capacity"

    def tearDown(self):
        battery_mod._SYSFS_HIDRAW = self._old_root
        self._tmp.cleanup()

    def test_reads_capacity(self):
        self.capacity.write_text("42\n")
        self.assertEqual(
            battery_percent_from_sysfs("/dev/hidraw3"), 42
        )

    def test_clamps_out_of_range(self):
        self.capacity.write_text("255\n")
        self.assertEqual(battery_percent_from_sysfs("/dev/hidraw3"), 100)
        self.capacity.write_text("-5\n")
        self.assertEqual(battery_percent_from_sysfs("/dev/hidraw3"), 0)

    def test_unknown_path_or_missing_supply_returns_zero(self):
        self.assertEqual(battery_percent_from_sysfs(None), 0)
        self.assertEqual(battery_percent_from_sysfs("/dev/hidraw99"), 0)
        self.capacity.write_text("80\n")
        self.capacity.unlink()
        self.assertEqual(battery_percent_from_sysfs("/dev/hidraw3"), 0)

    def test_garbage_capacity_returns_zero(self):
        self.capacity.write_text("not-a-number\n")
        self.assertEqual(battery_percent_from_sysfs("/dev/hidraw3"), 0)


class TestWorkerBattery(unittest.TestCase):
    def setUp(self):
        from src.engine.worker_thread import WorkerThread

        self.worker = WorkerThread()

    def test_read_without_device_is_zero(self):
        self.assertEqual(self.worker._read_battery(), 0)

    def test_read_falls_back_to_last_status_byte(self):
        self.worker._last_battery_status = 11
        with mock.patch(
            "src.engine.worker_thread.battery_percent_from_sysfs", return_value=0
        ):
            self.assertEqual(self.worker._read_battery(), 100)

    def test_poll_emits_on_change_and_throttles(self):
        got: list[int] = []
        self.worker.battery_update.connect(got.append)
        overdue = time.monotonic() - self.worker.BATTERY_POLL_S - 1

        with mock.patch.object(self.worker, "_read_battery", return_value=55):
            self.worker._last_battery_poll = overdue  # force "due"
            self.worker._maybe_emit_battery()
        self.assertEqual(got, [55])

        # Second call immediately after: throttled, no emit even if the
        # level changed.
        with mock.patch.object(self.worker, "_read_battery", return_value=77):
            self.worker._maybe_emit_battery()
        self.assertEqual(got, [55])

        # Unknown (0) reads are never emitted.
        self.worker._last_battery_poll = overdue
        with mock.patch.object(self.worker, "_read_battery", return_value=0):
            self.worker._maybe_emit_battery()
        self.assertEqual(got, [55])

    def test_poll_emits_again_after_interval(self):
        got: list[int] = []
        self.worker.battery_update.connect(got.append)
        with mock.patch.object(self.worker, "_read_battery", return_value=60):
            self.worker._last_battery_poll = (
                time.monotonic() - self.worker.BATTERY_POLL_S - 1
            )
            self.worker._maybe_emit_battery()
        with mock.patch.object(self.worker, "_read_battery", return_value=70):
            self.worker._last_battery_poll = (
                time.monotonic() - self.worker.BATTERY_POLL_S - 1
            )
            self.worker._maybe_emit_battery()  # interval elapsed: due again
        self.assertEqual(got, [60, 70])

    def test_throttle_math_at_fresh_boot(self):
        """monotonic() can start near 0 in fresh CI containers: the throttle
        math must still emit when the poll is overdue (run() resets to
        'overdue', not 0.0 — a 0.0 reset would delay the first poll by up
        to 30 s on a fresh boot)."""
        got: list[int] = []
        self.worker.battery_update.connect(got.append)
        with mock.patch.object(self.worker, "_read_battery", return_value=80), \
                mock.patch("src.engine.worker_thread.time.monotonic",
                           return_value=10.0):
            # run()'s reset: overdue relative to the (low) clock
            self.worker._last_battery_poll = 10.0 - self.worker.BATTERY_POLL_S - 1
            self.worker._maybe_emit_battery()
        self.assertEqual(got, [80])

        # And a 0.0 reset at fresh-boot time IS throttled (documents why
        # run() must never reset to 0.0):
        with mock.patch.object(self.worker, "_read_battery", return_value=90), \
                mock.patch("src.engine.worker_thread.time.monotonic",
                           return_value=10.0):
            self.worker._last_battery_poll = 0.0
            self.worker._maybe_emit_battery()
        self.assertEqual(got, [80])


class TestSlotBattery(unittest.TestCase):
    def test_slot_read_without_device_is_zero(self):
        from src.engine.controller_slot import ControllerSlot

        slot = ControllerSlot(0)
        self.assertEqual(slot._read_battery(), 0)


if __name__ == "__main__":
    unittest.main()
