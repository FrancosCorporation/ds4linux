"""Regression tests for D-pad normalization and profile mapping."""

import unittest
from types import SimpleNamespace
from unittest import mock

from evdev import ecodes as e

from src.constants import DS4_TO_PS4_BTN_MAP, DS4_TO_XBOX_BTN_MAP, PS4Btn, XboxBtn
from src.engine.dpad import LEFT, RIGHT, UP
from src.engine.input_mapper import InputMapper, ProfileConfig
from src.engine.virtual_device import VirtualDeviceType
from src.engine.worker_thread import WorkerThread
from tests.helpers import make_bt_report, make_usb_hidraw_report


class FakeVirtualDevice:
    """Captures virtual events and syncs emitted by the worker."""

    def __init__(self):
        self.events = []
        self.syncs = 0

    def write_event(self, ev_type, code, value):
        self.events.append((ev_type, code, value))

    def sync(self):
        self.syncs += 1


class TestWorkerDpadPath(unittest.TestCase):
    def setUp(self):
        self.worker = WorkerThread()
        self.vdev = FakeVirtualDevice()
        self.mapper = InputMapper(ProfileConfig(
            dpad_output_mode="buttons",
            button_maps={int(k): int(v) for k, v in DS4_TO_XBOX_BTN_MAP.items()},
        ))
        self.dpad = set()

    def _apply(self, direction, pressed):
        code = {UP: e.BTN_DPAD_UP, "down": e.BTN_DPAD_DOWN,
                LEFT: e.BTN_DPAD_LEFT, RIGHT: e.BTN_DPAD_RIGHT}[direction]
        if pressed:
            self.dpad.add(code)
        else:
            self.dpad.discard(code)
        before = len(self.vdev.events)
        self.worker._set_dpad_source(
            "evdev-key", self.dpad, self.mapper,
            self.vdev.write_event, self.vdev.sync,
        )
        return len(self.vdev.events) != before

    def _key_events(self):
        return [ev for ev in self.vdev.events if ev[0] == e.EV_KEY]

    def test_cardinal_press_and_release(self):
        self._apply(UP, True)
        self.assertEqual(self._key_events(), [(e.EV_KEY, XboxBtn.DPAD_UP, 1)])
        self._apply(UP, False)
        self.assertEqual(
            self._key_events(),
            [(e.EV_KEY, XboxBtn.DPAD_UP, 1), (e.EV_KEY, XboxBtn.DPAD_UP, 0)],
        )

    def test_stuck_diagonal_regression(self):
        """UP -> LEFT -> release UP must emit HAT0Y=0."""
        self._apply(UP, True)
        self._apply(LEFT, True)
        self._apply(UP, False)

        self.assertIn((e.EV_KEY, XboxBtn.DPAD_UP, 0), self.vdev.events)
        self.assertIn((e.EV_KEY, XboxBtn.DPAD_LEFT, 1), self.vdev.events)

        self._apply(LEFT, False)
        self.assertEqual(self.mapper.button_state[e.BTN_DPAD_LEFT], False)
        self.assertEqual(self.mapper.button_state[e.BTN_DPAD_UP], False)

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
        self.assertEqual(self.mapper.button_state[e.BTN_DPAD_RIGHT], False)
        self.assertEqual(self.mapper.button_state[e.BTN_DPAD_UP], False)

    def test_ps4_profile_uses_its_direction_destinations(self):
        self.mapper.set_profile(ProfileConfig(
            device_type=VirtualDeviceType.PS4,
            dpad_output_mode="buttons",
            button_maps={int(k): int(v) for k, v in DS4_TO_PS4_BTN_MAP.items()},
        ))
        self.dpad.clear()
        self.worker._dpad_sources.clear()
        self.worker._dpad_effective = set()
        self.vdev.events.clear()
        self._apply(LEFT, True)
        self._apply(UP, True)
        self._apply(LEFT, False)
        self._apply(UP, False)
        self.assertIn((e.EV_KEY, PS4Btn.DPAD_LEFT, 1), self.vdev.events)
        self.assertIn((e.EV_KEY, PS4Btn.DPAD_UP, 1), self.vdev.events)

    def test_removed_direction_is_suppressed(self):
        self.mapper.profile.button_maps.pop(e.BTN_DPAD_UP)
        self._apply(UP, True)
        self._apply(UP, False)
        self.assertEqual(self._key_events(), [])

    def test_direction_can_be_remapped_to_another_button(self):
        self.mapper.profile.button_maps[e.BTN_DPAD_UP] = e.BTN_A
        self._apply(UP, True)
        self._apply(UP, False)
        self.assertEqual(self._key_events(), [(e.EV_KEY, e.BTN_A, 1), (e.EV_KEY, e.BTN_A, 0)])

    def test_evdev_hat_uses_the_same_mapping_and_releases(self):
        mark_sync = self.vdev.sync
        self.worker._process_dpad_hat(
            e.ABS_HAT0Y, -1, self.mapper, self.vdev.write_event, mark_sync,
        )
        self.worker._process_dpad_hat(
            e.ABS_HAT0Y, 0, self.mapper, self.vdev.write_event, mark_sync,
        )
        self.assertEqual(self._key_events(), [
            (e.EV_KEY, XboxBtn.DPAD_UP, 1),
            (e.EV_KEY, XboxBtn.DPAD_UP, 0),
        ])

    def test_opposite_directions_cancel_and_resume(self):
        self._apply(UP, True)
        self._apply("down", True)
        self._apply(UP, False)
        self.assertIn((e.EV_KEY, XboxBtn.DPAD_UP, 0), self.vdev.events)
        self.assertIn((e.EV_KEY, XboxBtn.DPAD_DOWN, 1), self.vdev.events)

    def test_hat_axis_change_updates_only_effective_direction(self):
        self.worker._process_dpad_hat(
            e.ABS_HAT0X, -1, self.mapper, self.vdev.write_event, self.vdev.sync,
        )
        self.worker._process_dpad_hat(
            e.ABS_HAT0Y, -1, self.mapper, self.vdev.write_event, self.vdev.sync,
        )
        self.assertEqual(self._key_events(), [
            (e.EV_KEY, XboxBtn.DPAD_LEFT, 1),
            (e.EV_KEY, XboxBtn.DPAD_UP, 1),
        ])


class TestWorkerDpadHatOutput(unittest.TestCase):
    """The backwards-compatible profile mode emits absolute HAT axes."""

    def setUp(self):
        self.worker = WorkerThread()
        self.vdev = FakeVirtualDevice()
        self.mapper = InputMapper(ProfileConfig(
            button_maps={int(k): int(v) for k, v in DS4_TO_XBOX_BTN_MAP.items()},
        ))

    def _key(self, code, value):
        self.worker._process_dpad_key(
            code, value, self.mapper, self.vdev.write_event, self.vdev.sync,
        )

    def test_default_hat_mode_emits_diagonal_and_neutral_transitions(self):
        self.assertEqual(self.mapper.profile.dpad_output_mode, "hat")
        self._key(e.BTN_DPAD_UP, 1)
        self._key(e.BTN_DPAD_LEFT, 1)
        self.assertIn((e.EV_ABS, e.ABS_HAT0X, -1), self.vdev.events)
        self.assertIn((e.EV_ABS, e.ABS_HAT0Y, -1), self.vdev.events)
        self.assertFalse(any(t == e.EV_KEY and c in {
            e.BTN_DPAD_UP, e.BTN_DPAD_LEFT,
        } for t, c, _ in self.vdev.events))

        self._key(e.BTN_DPAD_UP, 0)
        self.assertEqual(self.vdev.events[-1], (e.EV_ABS, e.ABS_HAT0Y, 0))
        self._key(e.BTN_DPAD_LEFT, 0)
        self.assertEqual(self.vdev.events[-1], (e.EV_ABS, e.ABS_HAT0X, 0))

    def test_multiple_directions_mapped_to_one_hat_target_hold_until_last_release(self):
        self.mapper.profile.button_maps[e.BTN_DPAD_RIGHT] = e.BTN_DPAD_UP
        self._key(e.BTN_DPAD_UP, 1)
        self._key(e.BTN_DPAD_RIGHT, 1)
        self._key(e.BTN_DPAD_UP, 0)
        self.assertEqual(self.vdev.events[-1], (e.EV_ABS, e.ABS_HAT0Y, -1))
        self._key(e.BTN_DPAD_RIGHT, 0)
        self.assertEqual(self.vdev.events[-1], (e.EV_ABS, e.ABS_HAT0Y, 0))

    def test_custom_non_dpad_destination_remains_a_button(self):
        self.mapper.profile.button_maps[e.BTN_DPAD_UP] = e.BTN_A
        self._key(e.BTN_DPAD_UP, 1)
        self._key(e.BTN_DPAD_UP, 0)
        self.assertEqual(self.vdev.events, [
            (e.EV_KEY, e.BTN_A, 1), (e.EV_KEY, e.BTN_A, 0),
        ])


class TestEvdevFrames(unittest.TestCase):
    def setUp(self):
        self.worker = WorkerThread()
        self.vdev = FakeVirtualDevice()
        self.mapper = InputMapper(ProfileConfig(
            dpad_output_mode="buttons",
            button_maps={e.BTN_SOUTH: e.BTN_A},
        ))

    @staticmethod
    def event(event_type, code, value):
        return SimpleNamespace(type=event_type, code=code, value=value)

    def _process(self, events, device):
        self.worker._process_evdev_events(
            events, device, self.mapper, self.vdev.write_event,
            self.vdev.sync, [False],
        )

    def test_syncs_once_per_evdev_frame(self):
        device = SimpleNamespace()
        self._process([
            self.event(e.EV_KEY, e.BTN_SOUTH, 1),
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
            self.event(e.EV_KEY, e.BTN_SOUTH, 0),
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
        ], device)
        self.assertEqual(self.vdev.events, [
            (e.EV_KEY, e.BTN_A, 1), (e.EV_KEY, e.BTN_A, 0),
        ])
        self.assertEqual(self.vdev.syncs, 2)

    def test_syn_dropped_discards_tail_and_recovers_actual_key_state(self):
        device = SimpleNamespace(
            active_keys=lambda: [],
            capabilities=lambda absinfo=False: {e.EV_KEY: [e.BTN_SOUTH]},
        )
        self._process([
            self.event(e.EV_SYN, e.SYN_DROPPED, 0),
            self.event(e.EV_KEY, e.BTN_SOUTH, 1),  # Lost frame data is ignored.
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
        ], device)
        self.assertEqual(self.vdev.events, [])
        self.assertEqual(self.vdev.syncs, 0)
        self.assertFalse(self.mapper.button_state.get(e.BTN_SOUTH, False))

    def test_syn_dropped_releases_key_if_kernel_state_is_neutral(self):
        self._process([
            self.event(e.EV_KEY, e.BTN_SOUTH, 1),
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
        ], SimpleNamespace())
        device = SimpleNamespace(
            active_keys=lambda: [],
            capabilities=lambda absinfo=False: {e.EV_KEY: [e.BTN_SOUTH]},
        )
        self._process([
            self.event(e.EV_SYN, e.SYN_DROPPED, 0),
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
        ], device)
        self.assertEqual(self.vdev.events, [
            (e.EV_KEY, e.BTN_A, 1), (e.EV_KEY, e.BTN_A, 0),
        ])
        self.assertEqual(self.vdev.syncs, 2)

    def test_failed_state_query_does_not_falsely_release_held_key(self):
        self._process([
            self.event(e.EV_KEY, e.BTN_SOUTH, 1),
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
        ], SimpleNamespace())

        def fail_query():
            raise OSError("temporarily unavailable")

        self._process([
            self.event(e.EV_SYN, e.SYN_DROPPED, 0),
            self.event(e.EV_SYN, e.SYN_REPORT, 0),
        ], SimpleNamespace(
            active_keys=fail_query,
            capabilities=lambda absinfo=False: {},
        ))
        self.assertTrue(self.mapper.button_state[e.BTN_SOUTH])
        self.assertEqual(self.vdev.events, [(e.EV_KEY, e.BTN_A, 1)])


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
        self.assertNotIn((e.EV_KEY, e.BTN_DPAD_UP, 1), self.events)  # Up suppressed

        # Level source repeats the state: no second fire (transition dedup)
        self._process(up)
        self.macro_engine.execute_macro.assert_called_once()

        # Release: still one fire, hat stays neutral
        self._process(make_usb_hidraw_report(dpad=8))
        self.macro_engine.execute_macro.assert_called_once()
        self.assertNotIn((e.EV_KEY, e.BTN_DPAD_UP, 1), self.events)

    def test_unbound_direction_uses_default_button_mapping(self):
        self._process(make_usb_hidraw_report(dpad=2))  # Right (no macro)
        self.macro_engine.execute_macro.assert_not_called()
        self.assertIn((e.EV_ABS, e.ABS_HAT0X, 1), self.events)

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
        """Macro-bound direction: the mapped key is suppressed but
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
        # ...while the mapped output is suppressed (macro replaced it)
        self.assertNotIn((e.EV_KEY, e.BTN_DPAD_RIGHT, 1), self.events)
        self.assertFalse(any(t == e.EV_ABS and c == e.ABS_HAT0X and v != 0
                             for t, c, v in self.events))

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
