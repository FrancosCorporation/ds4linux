"""Auto-profile detection tests: asynchronous, non-blocking behaviour."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from src.engine.auto_profile import AutoProfileManager, AutoProfileRule


def _qt_app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=2.0):
    """Poll while pumping Qt events (queued cross-thread signals deliver
    through the main-thread event loop)."""
    app = _qt_app()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.01)
    return predicate()


class TestAutoProfileAsync(unittest.TestCase):
    def setUp(self):
        import src.engine.auto_profile as ap_mod

        self._tmp = tempfile.TemporaryDirectory()
        self._old_file = ap_mod.AUTO_PROFILE_FILE
        ap_mod.AUTO_PROFILE_FILE = Path(self._tmp.name) / "auto_profiles.json"

    def tearDown(self):
        import src.engine.auto_profile as ap_mod

        ap_mod.AUTO_PROFILE_FILE = self._old_file
        self._tmp.cleanup()
    def test_check_now_returns_immediately(self):
        """xprop/pgrep must never run on the caller's (GUI) thread."""
        ap = AutoProfileManager()
        started = threading.Event()
        release = threading.Event()

        def slow_detection():
            started.set()
            release.wait(2.0)
            return ("steam", "Game")

        ap.get_foreground_info = slow_detection  # type: ignore[method-assign]

        t0 = time.monotonic()
        ap.check_now()
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.2, "check_now must not block the caller")
        self.assertTrue(started.wait(1.0), "detection thread must start")

        # While busy, a second tick must not spawn another detection run
        with mock.patch.object(
            threading.Thread, "start", side_effect=AssertionError("overlap")
        ):
            ap.check_now()

        release.set()
        self.assertTrue(wait_until(lambda: not ap._detect_busy))
        ap.stop()

    def test_applies_profile_asynchronously(self):
        ap = AutoProfileManager()
        ap._rules = [AutoProfileRule(
            name="r", program="steam", title="", profile="CS2", enabled=True,
        )]
        ap.get_foreground_info = lambda: ("steam", "Counter-Strike 2")  # type: ignore

        applied = []
        ap.profile_apply_requested.connect(applied.append)
        ap.check_now()
        self.assertTrue(wait_until(lambda: applied), "profile must be applied")
        self.assertEqual(applied, ["CS2"])

        # Same foreground again: no re-apply
        ap.check_now()
        self.assertTrue(wait_until(lambda: not ap._detect_busy))
        self.assertEqual(applied, ["CS2"])
        ap.stop()

    def test_skips_detection_when_nothing_to_apply(self):
        ap = AutoProfileManager()
        ap._rules = []
        ap._revert_to_default = False
        ap.get_foreground_info = mock.Mock()  # type: ignore[method-assign]
        ap.check_now()
        time.sleep(0.05)
        ap.get_foreground_info.assert_not_called()
        ap.stop()

    def test_disabled_guard_ignores_late_result(self):
        ap = AutoProfileManager()
        gate = threading.Event()

        def gated():
            gate.wait(2.0)
            return ("wine", "game.exe")

        ap.get_foreground_info = gated  # type: ignore[method-assign]
        applied = []
        ap.profile_apply_requested.connect(applied.append)
        ap.check_now()
        self.assertTrue(wait_until(lambda: ap._detect_busy))
        ap.set_enabled(False)  # user flips the switch mid-detection
        gate.set()
        self.assertTrue(wait_until(lambda: not ap._detect_busy))
        self.assertEqual(applied, [], "late result must be discarded")
        ap.stop()

    def test_stop_disables_detection(self):
        """Cleanup stop() must disarm detection: late calls must not
        re-arm the poll timer (regression: stop() left _enabled=True)."""
        ap = AutoProfileManager()
        self.assertTrue(ap.is_enabled())
        ap.stop()
        self.assertFalse(ap.is_enabled())
        ap.check_now()  # must be a no-op, never spawn a detection thread
        self.assertFalse(ap._detect_busy)
        self.assertFalse(ap.is_enabled())

    def test_load_skips_malformed_rules_without_losing_the_rest(self):
        """One unknown/renamed field used to wipe every rule (list
        comprehension inside a try), and the next save() persisted it."""
        import json as _json

        import src.engine.auto_profile as ap_mod

        ap = AutoProfileManager()  # loads the (empty) temp file
        ap._rules = []
        data = {
            "enabled": True,
            "rules": [
                {"name": "good", "program": "steam", "title": "",
                 "profile": "CS2", "enabled": True},
                {"name": "bad", "program": "wine", "title": "",
                 "profile": "X", "enabled": True, "unexpected_field": 1},
                {"totally": "wrong"},
            ],
        }
        ap_mod.AUTO_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ap_mod.AUTO_PROFILE_FILE.write_text(_json.dumps(data))

        ap2 = AutoProfileManager()
        self.assertEqual(len(ap2._rules), 1)
        self.assertEqual(ap2._rules[0].profile, "CS2")
        ap.stop()
        ap2.stop()

    def test_thread_start_failure_clears_busy_latch(self):
        ap = AutoProfileManager()
        ap._rules = [AutoProfileRule(
            name="r", program="steam", title="", profile="CS2", enabled=True,
        )]
        with mock.patch(
            "threading.Thread.start", side_effect=RuntimeError("no threads")
        ):
            ap.check_now()  # must not raise, must not stay busy
        self.assertFalse(ap._detect_busy)
        # Detection still works afterwards (latch not stuck).
        ap.get_foreground_info = lambda: ("steam", "Counter-Strike 2")  # type: ignore
        applied = []
        ap.profile_apply_requested.connect(applied.append)
        ap.check_now()
        self.assertTrue(wait_until(lambda: applied))
        self.assertEqual(applied, ["CS2"])
        ap.stop()


if __name__ == "__main__":
    unittest.main()
