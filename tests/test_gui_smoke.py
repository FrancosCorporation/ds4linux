"""Headless GUI smoke tests (offscreen Qt).

They guarantee the widgets can be built, the hotspots stay aligned with
the controller image, and profile save/load round-trips through the UI.
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.config.profile_manager as profile_manager_module
from src.constants import DS4Btn
from src.engine.virtual_device import VirtualDeviceType
from src.gui.mapping_tab import (
    OVERLAY_BUTTON_DEFS,
    ControllerOverlayWidget,
    MappingTabWidget,
    physical_name,
    target_name,
)


class FakeVirtualDevice:
    def __init__(self):
        self.device_type = VirtualDeviceType.XBOX

    def set_device_type(self, device_type):
        self.device_type = device_type


class FakeSlot:
    def __init__(self):
        self._worker = None
        self._virtual_device = FakeVirtualDevice()
        self.profile = None
        self.led = None

    @property
    def worker(self):
        return self._worker

    @property
    def virtual_device(self):
        return self._virtual_device

    @property
    def physical_device(self):
        return None

    def set_profile(self, profile):
        self.profile = profile

    def set_led_color(self, r, g, b):
        self.led = (r, g, b)

    def stop_worker(self):
        pass


class TestOverlayGeometry(unittest.TestCase):
    def setUp(self):
        self.overlay = ControllerOverlayWidget()
        self.overlay.resize(420, 380)

    def test_controller_asset_size_unchanged(self):
        """Hotspot coordinates are calibrated for a 360x360 asset.

        If the artwork is ever replaced, OVERLAY_BUTTON_DEFS must be
        recalibrated — this test fails first so nobody ships a misaligned
        overlay by accident.
        """
        from PySide6.QtGui import QImage

        asset = Path(__file__).resolve().parents[1] / "assets" / "ds4_controller.png"
        self.assertTrue(asset.exists(), f"missing asset: {asset}")
        image = QImage(str(asset))
        self.assertEqual((image.width(), image.height()), (360, 360))

    def test_every_hotspot_center_hits_its_own_button(self):
        for code, _symbol, rx, ry, rw, rh, _kind in OVERLAY_BUTTON_DEFS:
            center = self.overlay._button_rect(rx, ry, rw, rh).center()
            self.assertEqual(
                self.overlay._button_at(center), code,
                f"hotspot for {physical_name(code)} is unreachable/overlapped",
            )

    def test_hotspot_interior_is_never_shadowed(self):
        """5x5 grid per hotspot: no interior point may be captured by a
        different (earlier) button — that would break clickability."""
        for code, _symbol, rx, ry, rw, rh, _kind in OVERLAY_BUTTON_DEFS:
            rect = self.overlay._button_rect(rx, ry, rw, rh)
            for fx in (0.1, 0.3, 0.5, 0.7, 0.9):
                for fy in (0.1, 0.3, 0.5, 0.7, 0.9):
                    point = QPointF(
                        rect.x() + rect.width() * fx,
                        rect.y() + rect.height() * fy,
                    )
                    hit = self.overlay._button_at(point)
                    self.assertEqual(
                        hit, code,
                        f"interior point of {physical_name(code)} at "
                        f"({point.x():.0f},{point.y():.0f}) hit {hit}",
                    )

    def test_all_buttons_present(self):
        codes = {code for code, *_rest in OVERLAY_BUTTON_DEFS}
        for expected in (DS4Btn.DPAD_UP, DS4Btn.DPAD_DOWN, DS4Btn.DPAD_LEFT,
                         DS4Btn.DPAD_RIGHT, DS4Btn.SOUTH, DS4Btn.EAST,
                         DS4Btn.NORTH, DS4Btn.WEST, DS4Btn.TOUCHPAD):
            self.assertIn(int(expected), codes)

    def test_click_emits_signal(self):
        captured = []
        self.overlay.button_clicked.connect(captured.append)
        code, _s, rx, ry, rw, rh, _k = OVERLAY_BUTTON_DEFS[0]
        center = self.overlay._button_rect(rx, ry, rw, rh).center()
        event = QMouseEvent(
            QEvent.MouseButtonPress, center, self.overlay.mapToGlobal(center),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
        )
        self.overlay.mousePressEvent(event)
        self.assertEqual(captured, [code])

    def test_hat_events_light_up_dpad(self):
        self.overlay.handle_raw_event(3, 16, -1)  # EV_ABS, ABS_HAT0X, left
        self.overlay.handle_raw_event(3, 17, 1)   # ABS_HAT0Y, down
        pressed = {c for c, v in self.overlay._pressed.items() if v}
        self.assertIn(int(DS4Btn.DPAD_LEFT), pressed)
        self.assertIn(int(DS4Btn.DPAD_DOWN), pressed)
        self.overlay.handle_raw_event(3, 16, 0)
        self.overlay.handle_raw_event(3, 17, 0)
        self.assertFalse(any(self.overlay._pressed.values()))


class TestNameHelpers(unittest.TestCase):
    def test_physical_vs_target_names(self):
        from src.constants import DS4Btn
        self.assertEqual(physical_name(int(DS4Btn.SOUTH)), "✕ Cross")
        self.assertEqual(target_name(int(DS4Btn.SOUTH), VirtualDeviceType.XBOX), "A")
        self.assertEqual(target_name(int(DS4Btn.SOUTH), VirtualDeviceType.PS4), "Cross")


class TestMappingWidget(unittest.TestCase):
    def test_mappings_roundtrip(self):
        w = MappingTabWidget()
        w.set_mappings({304: 304, 305: 305})
        self.assertEqual(w.get_mappings(), {304: 304, 305: 305})
        w._remove_mapping(304)
        self.assertEqual(w.get_mappings(), {305: 305})

    def test_reset_defaults_fills_everything(self):
        w = MappingTabWidget()
        w._reset_defaults()
        mappings = w.get_mappings()
        self.assertGreaterEqual(len(mappings), 16)
        for code in (304, 305, 307, 308, 310, 311):
            self.assertIn(code, mappings)


class TestProfileEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        profile_manager_module.PROFILE_DIR = Path(cls.tmp.name)
        profile_manager_module.CONFIG_FILE = Path(cls.tmp.name) / "config.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_editor_builds_and_saves(self):
        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        slot = FakeSlot()
        pm = ProfileManager()
        editor = ProfileEditorWindow(0, slot, pm)

        editor.profile_name_edit.setText("Teste UI")
        editor.mapping_tab.set_mappings({304: 308})
        editor._save_profile()

        loaded = pm.load_profile("Teste UI")
        self.assertEqual(loaded.name, "Teste UI")
        self.assertEqual(loaded.button_maps.get(304), 308)
        self.assertIsNotNone(slot.profile)

    def test_led_color_is_tuple(self):
        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        slot = FakeSlot()
        editor = ProfileEditorWindow(0, slot, ProfileManager())
        editor._set_led_color((10, 20, 30))
        self.assertEqual(editor._current_profile.led_color, (10, 20, 30))


if __name__ == "__main__":
    unittest.main()
