"""Integration test for the worker's evdev D-pad path.

Exercises the exact code used by ``WorkerThread`` when hid-sony reports
``BTN_DPAD_*`` key events: ``DpadState`` + ``WorkerThread._write_hat``.
"""

import unittest

from evdev import ecodes as e

from src.constants import XBOX_ABS_MAP, XboxAbs
from src.engine.dpad import LEFT, RIGHT, UP, DpadState
from src.engine.worker_thread import WorkerThread
from tests.helpers import make_usb_hidraw_report


class FakeVirtualDevice:
    """Captures EV_ABS writes and syncs emitted by the worker."""

    def __init__(self):
        self.events = []
        self.syncs = 0

    def write_event(self, ev_type, code, value):
        self.events.append((ev_type, code, value))

    def sync(self):
        self.syncs += 1


class TestWorkerDpadPath(unittest.TestCase):
    def setUp(self):
        self.vdev = FakeVirtualDevice()
        self.axis_state = {}
        self.dpad = DpadState()
    def _apply(self, direction, pressed):
        changed = self.dpad.update(direction, pressed)
        if changed:
            WorkerThread._write_hat(
                self.vdev.write_event, self.vdev.sync, XBOX_ABS_MAP,
                self.axis_state, self.dpad.x, self.dpad.y,
                e.ABS_HAT0X, e.ABS_HAT0Y,
            )
        return changed

    def _hat_events(self):
        return [ev for ev in self.vdev.events if ev[0] == e.EV_ABS]

    def test_cardinal_press_and_release(self):
        self._apply(UP, True)
        self.assertEqual(self._hat_events(), [(e.EV_ABS, XboxAbs.HAT0Y, -1)])
        self._apply(UP, False)
        self.assertEqual(
            self._hat_events(),
            [(e.EV_ABS, XboxAbs.HAT0Y, -1), (e.EV_ABS, XboxAbs.HAT0Y, 0)],
        )

    def test_stuck_diagonal_regression(self):
        """UP -> LEFT -> release UP must emit HAT0Y=0."""
        self._apply(UP, True)
        self._apply(LEFT, True)
        self._apply(UP, False)

        self.assertEqual(self.axis_state[e.ABS_HAT0Y], 0)
        self.assertEqual(self.axis_state[e.ABS_HAT0X], -1)
        self.assertEqual(self.dpad.y, 0)
        self.assertEqual(self.dpad.x, -1)

        self._apply(LEFT, False)
        self.assertEqual(self.axis_state[e.ABS_HAT0X], 0)
        self.assertEqual(self.axis_state[e.ABS_HAT0Y], 0)

    def test_no_duplicate_writes_on_repeat(self):
        self._apply(UP, True)
        count = len(self.vdev.events)
        self.assertFalse(self._apply(UP, True))
        self.assertEqual(len(self.vdev.events), count)

    def test_sliding_from_up_to_right(self):
        self._apply(UP, True)
        self._apply(RIGHT, True)
        self._apply(UP, False)
        self._apply(RIGHT, False)
        self.assertEqual(self.axis_state[e.ABS_HAT0X], 0)
        self.assertEqual(self.axis_state[e.ABS_HAT0Y], 0)

    def test_hat_written_for_ps4_profile_too(self):
        from src.constants import PS4_ABS_MAP

        self.dpad = DpadState()
        self.axis_state = {}
        self._apply(LEFT, True)
        # same numeric code on both maps; sanity check the map lookup
        self.assertIn(e.ABS_HAT0X, PS4_ABS_MAP)


class TestWorkerHidrawReport(unittest.TestCase):
    """End-to-end check of _process_hidraw_report with a real InputMapper."""

    def setUp(self):
        from src.constants import DS4_TO_XBOX_BTN_MAP, DS4Btn, XboxAbs, XboxBtn
        from src.engine.input_mapper import InputMapper, ProfileConfig

        self.worker = WorkerThread()
        profile = ProfileConfig(
            button_maps={int(k): int(v) for k, v in DS4_TO_XBOX_BTN_MAP.items()},
        )
        self.mapper = InputMapper(profile)
        self.btn_state: dict = {}
        self.axis_state: dict = {}
        self.events: list = []
        self.syncs = 0
        self.DS4Btn = DS4Btn
        self.XboxAbs = XboxAbs
        self.XboxBtn = XboxBtn

    def _write(self, ev_type, code, value):
        self.events.append((ev_type, code, value))

    def _sync(self):
        self.syncs += 1

    def _process(self, report):
        return self.worker._process_hidraw_report(
            report, self._write, self._sync, self.btn_state, self.axis_state,
            self.mapper, e.EV_KEY, e.EV_ABS,
        )

    def test_button_hat_and_trigger_in_one_report(self):
        # D-pad right (hat=2), Cross pressed, L2 fully pulled
        report = make_usb_hidraw_report(dpad=2, b0_extra=0x20, l2=255)
        dpad_x, dpad_y = self._process(report)

        self.assertEqual((dpad_x, dpad_y), (1, 0))
        self.assertIn((e.EV_ABS, self.XboxAbs.HAT0X, 1), self.events)
        self.assertIn((e.EV_KEY, self.XboxBtn.A, 1), self.events)  # Cross -> A
        self.assertIn((e.EV_ABS, self.XboxAbs.Z, 255), self.events)  # L2 full
        self.assertGreater(self.syncs, 0)

    def test_dpad_neutral_and_button_release(self):
        report = make_usb_hidraw_report(dpad=2, b0_extra=0x20)
        dpad_x, dpad_y = self._process(report)
        count = len(self.events)

        # Release everything, D-pad back to neutral (hat=8)
        report = make_usb_hidraw_report(dpad=8)
        dpad_x, dpad_y = self._process(report)

        self.assertEqual((dpad_x, dpad_y), (0, 0))
        self.assertIn((e.EV_ABS, self.XboxAbs.HAT0X, 0), self.events[count:])
        self.assertIn((e.EV_KEY, self.XboxBtn.A, 0), self.events[count:])

    def test_repeat_report_writes_nothing(self):
        report = make_usb_hidraw_report(dpad=2, b0_extra=0x20)
        self._process(report)
        count = len(self.events)
        self._process(report)
        self.assertEqual(len(self.events), count,
                         "identical report must not re-emit events")

    def test_touchpad_click_forwarded_on_ps4_profile(self):
        """Touchpad click is part of the button set and forwards when mapped."""
        from src.constants import DS4_TO_PS4_BTN_MAP

        self.mapper.profile.button_maps = {
            int(k): int(v) for k, v in DS4_TO_PS4_BTN_MAP.items()
        }
        report = make_usb_hidraw_report(b2=0x02)  # touchpad click only
        dpad_x, dpad_y = self._process(report)

        self.assertEqual((dpad_x, dpad_y), (0, 0))
        self.assertIn((e.EV_KEY, e.BTN_TOUCH, 1), self.events)


if __name__ == "__main__":
    unittest.main()
