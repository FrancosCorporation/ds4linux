"""Macro execution tests: engine queueing + wiring into both input paths.

Guards the regression where macros were stored in profiles but never
triggered by the worker (evdev and hidraw paths).
"""

from __future__ import annotations

import time
import unittest
from unittest import mock

from evdev import ecodes as e

from src.engine.input_mapper import InputMapper, MacroAction, ProfileConfig
from src.engine.macro_engine import EV_KEY, MacroEngine
from src.engine.worker_thread import WorkerThread
from tests.helpers import make_usb_report


class FakeVDev:
    """Records writes the way VirtualDevice does."""

    def __init__(self):
        self.events = []
        self.syncs = 0

    def write_event(self, ev_type, code, value):
        self.events.append((ev_type, code, value))

    def sync(self):
        self.syncs += 1


class RecordingMacroEngine:
    """Stand-in MacroEngine that records execute_macro calls."""

    def __init__(self):
        self.calls = []

    def execute_macro(self, actions):
        self.calls.append(list(actions))
        return True


# ---------------------------------------------------------------------------
# MacroEngine
# ---------------------------------------------------------------------------
class TestMacroEngine(unittest.TestCase):
    def setUp(self):
        self.vdev = FakeVDev()
        self.eng = MacroEngine(self.vdev)

    def tearDown(self):
        self.eng.shutdown()

    def _wait_events(self, count, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.vdev.events) < count:
            time.sleep(0.01)

    def test_executes_key_and_wait_actions(self):
        actions = [
            MacroAction("key", 0x130, 1),
            MacroAction("wait", 0, 0, 0.01),
            MacroAction("key", 0x130, 0),
        ]
        self.assertTrue(self.eng.execute_macro(actions))
        self._wait_events(2)
        self.assertEqual(self.vdev.events, [(EV_KEY, 0x130, 1), (EV_KEY, 0x130, 0)])
        self.assertEqual(self.vdev.syncs, 2)

    def test_empty_macro_rejected(self):
        self.assertFalse(self.eng.execute_macro([]))
        self.assertEqual(self.eng.pending_count(), 0)

    def test_queue_is_bounded(self):
        actions = [MacroAction("wait", 0, 0, 0.05)]
        for _ in range(MacroEngine.MAX_PENDING + 10):
            self.eng.execute_macro(actions)
        self.assertLessEqual(self.eng.pending_count(), MacroEngine.MAX_PENDING)
        self.assertGreater(self.eng.dropped, 0)

    def test_queue_drops_oldest_not_newest(self):
        """The documented policy drops the OLDEST pending macro; a bug that
        dropped the newest (pop(-1)) would leave delay 0.0 pending."""
        eng = self.eng
        with mock.patch.object(eng, "_ensure_worker_locked", return_value=None):
            for i in range(MacroEngine.MAX_PENDING + 2):
                eng.execute_macro([MacroAction("wait", 0, 0, float(i))])
        self.assertEqual(eng.dropped, 2)
        self.assertEqual(len(eng._pending), MacroEngine.MAX_PENDING)
        delays = [a[0].delay for a in eng._pending]
        self.assertEqual(delays[0], 2.0)   # two oldest gone
        self.assertEqual(delays[-1], float(MacroEngine.MAX_PENDING + 1))  # newest kept

    def test_delay_clamped(self):
        with mock.patch("src.engine.macro_engine.time.sleep") as sleep:
            MacroEngine._sleep(9999)
        sleep.assert_called_once_with(MacroEngine.MAX_DELAY_S)

    def test_negative_delay_not_slept(self):
        with mock.patch("src.engine.macro_engine.time.sleep") as sleep:
            MacroEngine._sleep(-1)
        sleep.assert_not_called()

    def test_shutdown_stops_queueing(self):
        self.eng.shutdown()
        self.assertFalse(self.eng.execute_macro([MacroAction("key", 0x130, 1)]))


# ---------------------------------------------------------------------------
# InputMapper wiring (map_button / dpad helper)
# ---------------------------------------------------------------------------
class TestMacroButtonWiring(unittest.TestCase):
    def setUp(self):
        self.engine = RecordingMacroEngine()
        self.profile = ProfileConfig(name="macro")
        self.profile.button_maps[e.BTN_SOUTH] = 0x130  # Cross -> A
        self.profile.macros[e.BTN_EAST] = [MacroAction("key", 0x131, 1)]
        self.mapper = InputMapper(self.profile, macro_engine=self.engine)

    def test_macro_press_fires_and_is_consumed(self):
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 1))
        self.assertEqual(len(self.engine.calls), 1)
        # Macro replaces the button: no virtual output even if mapped
        self.profile.button_maps[e.BTN_EAST] = 0x131
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 0))
        self.assertEqual(len(self.engine.calls), 1)  # release does not fire

    def test_level_source_fires_once_per_press(self):
        # hidraw repeats the same pressed state every report
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 1))
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 1))
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 1))
        self.assertEqual(len(self.engine.calls), 1)
        # Release re-arms the button for the next press
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 0))
        self.assertIsNone(self.mapper.map_button(e.BTN_EAST, 1))
        self.assertEqual(len(self.engine.calls), 2)

    def test_mapped_button_still_forwarded(self):
        self.assertEqual(
            self.mapper.map_button(e.BTN_SOUTH, 1), (0x130, 1)
        )
        # Deduped on repeat
        self.assertIsNone(self.mapper.map_button(e.BTN_SOUTH, 1))
        self.assertEqual(
            self.mapper.map_button(e.BTN_SOUTH, 0), (0x130, 0)
        )
        self.assertEqual(self.engine.calls, [])

    def test_maybe_execute_macro_dpad_semantics(self):
        self.profile.macros[e.BTN_DPAD_UP] = [MacroAction("key", 0x132, 1)]
        self.assertTrue(self.mapper.maybe_execute_macro(e.BTN_DPAD_UP, 1))
        self.assertEqual(len(self.engine.calls), 1)
        # Release of a macro-bound button is consumed but does not fire
        self.assertTrue(self.mapper.maybe_execute_macro(e.BTN_DPAD_UP, 0))
        self.assertEqual(len(self.engine.calls), 1)
        self.assertFalse(self.mapper.maybe_execute_macro(e.BTN_SOUTH, 1))


# ---------------------------------------------------------------------------
# hidraw path: WorkerThread._process_hidraw_report
# ---------------------------------------------------------------------------
class TestHidrawMacroPath(unittest.TestCase):
    def setUp(self):
        self.vdev = FakeVDev()
        self.engine = RecordingMacroEngine()
        self.profile = ProfileConfig(name="macro-hidraw")
        self.profile.button_maps[e.BTN_EAST] = 0x131      # plain mapping
        self.profile.macros[e.BTN_SOUTH] = [MacroAction("key", 0x130, 1)]
        self.mapper = InputMapper(self.profile, macro_engine=self.engine)
        self.worker = WorkerThread()

    def _process(self, report):
        self.worker._process_hidraw_report(
            report, self.vdev.write_event, self.vdev.sync,
            self.mapper.button_state, self.mapper.axis_state,
            self.mapper, e.EV_KEY, e.EV_ABS,
        )

    def test_macro_fires_once_across_repeated_reports(self):
        report = make_usb_report(b0_extra=0x20)  # BTN_SOUTH held down
        self._process(report)
        self._process(report)
        self._process(report)
        self.assertEqual(len(self.engine.calls), 1)
        # The macro replaces Cross: no BTN_SOUTH writes reach the vdev
        key_writes = [ev for ev in self.vdev.events if ev[0] == e.EV_KEY]
        self.assertNotIn((e.EV_KEY, 0x130, 1), key_writes)

    def test_plain_button_still_forwarded(self):
        report = make_usb_report(b0_extra=0x40)  # BTN_EAST (Circle) pressed
        self._process(report)
        self._process(report)  # held: no duplicate
        key_writes = [ev for ev in self.vdev.events if ev[0] == e.EV_KEY]
        self.assertEqual(key_writes, [(e.EV_KEY, 0x131, 1)])
        self.assertEqual(self.engine.calls, [])

    def test_release_of_plain_button_forwarded(self):
        self._process(make_usb_report(b0_extra=0x40))  # press
        self._process(make_usb_report())               # release
        key_writes = [ev for ev in self.vdev.events if ev[0] == e.EV_KEY]
        self.assertEqual(key_writes, [(e.EV_KEY, 0x131, 1), (e.EV_KEY, 0x131, 0)])


if __name__ == "__main__":
    unittest.main()
