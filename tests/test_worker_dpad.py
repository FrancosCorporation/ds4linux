"""Integration test for the worker's evdev D-pad path.

Exercises the exact code used by ``WorkerThread`` when hid-sony reports
``BTN_DPAD_*`` key events: ``DpadState`` + ``WorkerThread._write_hat``.
"""

import unittest
from unittest import mock

from evdev import ecodes as e

from src.constants import XBOX_ABS_MAP, DS4Abs, XboxAbs
from src.engine.dpad import LEFT, RIGHT, UP, DpadState
from src.engine.worker_thread import WorkerThread
from tests.helpers import make_bt_report, make_usb_hidraw_report


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
        """The PS4 map must drive _write_hat with real HAT writes — the
        old assertion only checked that the map contains the codes."""
        from src.constants import PS4_ABS_MAP

        self.dpad = DpadState()
        self.axis_state = {}

        def apply_ps4(direction, pressed):
            changed = self.dpad.update(direction, pressed)
            if changed:
                WorkerThread._write_hat(
                    self.vdev.write_event, self.vdev.sync, PS4_ABS_MAP,
                    self.axis_state, self.dpad.x, self.dpad.y,
                    e.ABS_HAT0X, e.ABS_HAT0Y,
                )
            return changed

        apply_ps4(LEFT, True)    # HAT0X=-1
        apply_ps4(UP, True)      # diagonal HAT0Y=-1
        apply_ps4(LEFT, False)   # HAT0X=0
        apply_ps4(UP, False)     # HAT0Y=0

        self.assertEqual(self.axis_state[e.ABS_HAT0X], 0)
        self.assertEqual(self.axis_state[e.ABS_HAT0Y], 0)
        self.assertIn(
            (e.EV_ABS, PS4_ABS_MAP[DS4Abs.HAT0X], -1), self.vdev.events
        )
        self.assertIn(
            (e.EV_ABS, PS4_ABS_MAP[DS4Abs.HAT0Y], -1), self.vdev.events
        )


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
        # Production passes mapper.button_state/axis_state (the mapper's own
        # dicts) — mirror that here or the transition dedup diverges from
        # reality.
        self.btn_state = self.mapper.button_state
        self.axis_state = self.mapper.axis_state
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

    def test_bt_report_full_path(self):
        """BT 0x11 reports (78 bytes) go through the same translation."""
        report = make_bt_report(dpad=4, b0_extra=0x20, l2=255)  # Down+Cross+L2
        dpad_x, dpad_y = self._process(report)

        self.assertEqual((dpad_x, dpad_y), (0, 1))
        self.assertIn((e.EV_KEY, self.XboxBtn.A, 1), self.events)
        self.assertIn((e.EV_ABS, self.XboxAbs.Z, 255), self.events)
        self.assertIn((e.EV_ABS, self.XboxAbs.HAT0Y, 1), self.events)

    def test_bt_report_truncated_minimal(self):
        """A 12-byte BT report must parse without crashing (the kernel
        normally delivers 78; MIN_HIDRAW_REPORT_BYTES == 12) — dpad AND
        sticks both translate correctly at the exact lower bound."""
        report = make_bt_report(dpad=2, size=12, lx=200)
        dpad_x, dpad_y = self._process(report)
        self.assertEqual((dpad_x, dpad_y), (1, 0))
        # The stick was parsed from index 3 and forwarded (transformed by
        # the mapper's center-128 normalization)
        xs = [ev for ev in self.events if ev[1] == self.XboxAbs.X]
        self.assertEqual(len(xs), 1)
        self.assertNotEqual(xs[0][2], 0)  # real transformed value, not a default

    def test_bt_report_below_minimum_is_empty(self):
        """11 bytes is below the BT minimum (12): empty state, no writes."""
        report = b"\x11" + bytes(10)  # too short for the BT layout
        dpad_x, dpad_y = self._process(report)
        self.assertEqual((dpad_x, dpad_y), (0, 0))
        self.assertEqual(self.events, [])

    def test_unknown_report_id_is_empty(self):
        report = b"\x05" + bytes(63)  # neither 0x01 nor 0x11
        dpad_x, dpad_y = self._process(report)
        self.assertEqual((dpad_x, dpad_y), (0, 0))
        self.assertEqual(self.events, [])

    def test_raw_button_not_reemitted_on_repeat(self):
        """Buttons: raw_event fires on TRANSITION only (one emit per press),
        even though HIDRAW repeats the full state at ~250 Hz."""
        got = []
        self.worker.raw_event.connect(lambda t, c, v: got.append((t, c, v)))
        report = make_usb_hidraw_report(dpad=8, b0_extra=0x20)  # Cross pressed
        self._process(report)
        self._process(report)
        self._process(report)
        crosses = [ev for ev in got if ev[1] == int(e.BTN_SOUTH)]
        self.assertEqual(crosses, [(e.EV_KEY, int(e.BTN_SOUTH), 1)])

    def test_raw_button_emitted_for_unmapped_button(self):
        """Unmapped physical buttons still reach the Readings tab in HIDRAW
        mode (the evdev path emits unconditionally at the top of the loop)."""
        got = []
        self.worker.raw_event.connect(lambda t, c, v: got.append((t, c, v)))
        # Square (b0 bit 0x10): mapped to BTN_WEST by the default map, so
        # remove its mapping first to make it unmapped-but-physical.
        self.mapper.profile.button_maps.pop(int(e.BTN_WEST), None)
        report = make_usb_hidraw_report(dpad=8, b0_extra=0x10)
        self._process(report)
        self.assertIn((e.EV_KEY, int(e.BTN_WEST), 1), got)
        # And nothing was written to the virtual device for it
        self.assertNotIn((e.EV_KEY, int(e.BTN_WEST), 1), self.events)

    def test_stationary_stick_emits_raw_once(self):
        """Sticks: raw_event is deduped on physical change — stationary
        sticks must not flood the GUI at report rate."""
        got = []
        self.worker.raw_event.connect(lambda t, c, v: got.append((t, c, v)))
        report = make_usb_hidraw_report(dpad=8, lx=100, ly=128)
        self._process(report)
        self._process(report)
        self._process(report)
        xs = [ev for ev in got if ev[1] == e.ABS_X]
        self.assertEqual(xs, [(e.EV_ABS, e.ABS_X, 100)])

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


class TestDpadMacroHidraw(unittest.TestCase):
    """D-pad macros must fire in HIDRAW mode (they only worked over evdev
    BTN_DPAD_* events before — the HAT paths had no macro hook)."""

    def setUp(self):
        from src.constants import DS4_TO_XBOX_BTN_MAP
        from src.engine.input_mapper import InputMapper, MacroAction, ProfileConfig

        self.worker = WorkerThread()
        profile = ProfileConfig(
            button_maps={int(k): int(v) for k, v in DS4_TO_XBOX_BTN_MAP.items()},
        )
        self.macro_engine = mock.Mock()
        profile.macros[int(e.BTN_DPAD_UP)] = [
            MacroAction("key", 0x130, 1),
            MacroAction("key", 0x130, 0),
        ]
        self.mapper = InputMapper(profile, macro_engine=self.macro_engine)
        # Production passes mapper.button_state/axis_state (the mapper's
        # own dicts).
        self.btn_state = self.mapper.button_state
        self.axis_state = self.mapper.axis_state
        self.events: list = []

    def _process(self, report):
        return self.worker._process_hidraw_report(
            report,
            lambda t, c, v: self.events.append((t, c, v)),
            lambda: None,
            self.btn_state,
            self.axis_state,
            self.mapper,
            e.EV_KEY,
            e.EV_ABS,
        )

    def _hat_writes(self, code):
        return [v for (t, c, v) in self.events if c == code]

    def test_macro_fires_once_and_hat_direction_suppressed(self):
        up = make_usb_hidraw_report(dpad=0)
        self._process(up)
        self.macro_engine.execute_macro.assert_called_once()
        self.assertNotIn(-1, self._hat_writes(e.ABS_HAT0Y))  # Up suppressed

        # Level source repeats the state: no second fire (transition dedup)
        self._process(up)
        self.macro_engine.execute_macro.assert_called_once()

        # Release: still one fire, hat stays neutral
        self._process(make_usb_hidraw_report(dpad=8))
        self.macro_engine.execute_macro.assert_called_once()
        self.assertNotIn(-1, self._hat_writes(e.ABS_HAT0Y))

    def test_unbound_direction_still_writes_hat(self):
        self._process(make_usb_hidraw_report(dpad=2))  # Right (no macro)
        self.macro_engine.execute_macro.assert_not_called()
        self.assertIn(1, self._hat_writes(e.ABS_HAT0X))

    def test_step_neutralizes_only_bound_axis(self):
        """Left has no macro: x passes through; Up is macro-bound: y zeroed."""
        eff_x, eff_y = self.worker._dpad_macro_step(self.mapper, -1, -1)
        self.assertEqual(eff_x, -1)   # left unbound
        self.assertEqual(eff_y, 0)    # up bound -> suppressed
        # Second identical call: dedup, no extra macro execution
        self.macro_engine.execute_macro.assert_called_once()
        self.worker._dpad_macro_step(self.mapper, -1, -1)
        self.macro_engine.execute_macro.assert_called_once()

    def test_raw_event_emitted_for_macro_bound_button(self):
        """Regression: HIDRAW mode suppressed raw_event for macro-bound
        buttons, so a macro could never be re-recorded in the fallback
        mode (the one used exactly when grab() fails)."""
        from src.engine.input_mapper import MacroAction

        self.mapper.profile.macros[int(e.BTN_SOUTH)] = [
            MacroAction("key", 0x130, 1),
            MacroAction("key", 0x130, 0),
        ]
        got = []
        self.worker.raw_event.connect(lambda t, c, v: got.append((t, c, v)))

        # Cross pressed (b0 bit 0x20) in a normal neutral-D-pad report
        self._process(make_usb_hidraw_report(dpad=8, b0_extra=0x20))

        self.macro_engine.execute_macro.assert_called_once()
        self.assertIn((e.EV_KEY, int(e.BTN_SOUTH), 1), got)
        # And the mapped key is consumed (macro replaced it)
        self.assertNotIn((e.EV_KEY, 0x130, 1), self.events)

    def test_macro_suppresses_write_but_raw_transition_flows(self):
        """Macro-bound direction: the effective HAT write is suppressed but
        the PHYSICAL raw_event transition still reaches the GUI (editors/
        overlay), deduped against the physical tracker — holding the
        direction must not flood raw_event either."""
        from src.engine.input_mapper import MacroAction

        self.mapper.profile.macros[int(e.BTN_DPAD_RIGHT)] = [
            MacroAction("key", 0x130, 1),
            MacroAction("key", 0x130, 0),
        ]
        got = []
        self.worker.raw_event.connect(lambda t, c, v: got.append((t, c, v)))

        # Press RIGHT: physical HAT0X=1 flows to raw_event...
        self._process(make_usb_hidraw_report(dpad=2))
        self.assertIn((e.EV_ABS, e.ABS_HAT0X, 1), got)
        self.macro_engine.execute_macro.assert_called_once()
        # ...while the effective write is suppressed (macro replaced it)
        self.assertNotIn((e.EV_ABS, e.ABS_HAT0X, 1), self.events)

        # HOLD the direction for many reports: no raw_event flood
        # (physical tracker dedup — raw stays 1 while held)
        for _ in range(20):
            self._process(make_usb_hidraw_report(dpad=2))
        rights = [ev for ev in got if ev[1] == e.ABS_HAT0X]
        self.assertEqual(rights, [(e.EV_ABS, e.ABS_HAT0X, 1)])

        # Release: physical transition 1 -> 0 flows once
        self._process(make_usb_hidraw_report(dpad=8))
        rights = [ev for ev in got if ev[1] == e.ABS_HAT0X]
        self.assertEqual(
            rights,
            [(e.EV_ABS, e.ABS_HAT0X, 1), (e.EV_ABS, e.ABS_HAT0X, 0)],
        )


if __name__ == "__main__":
    unittest.main()
