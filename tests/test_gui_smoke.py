"""Headless GUI smoke tests (offscreen Qt).

They guarantee the widgets can be built, the hotspots stay aligned with
the controller image, and profile save/load round-trips through the UI.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from evdev import ecodes as e
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def _destroy_widget(widget):
    if widget is None:
        return
    cleanup = getattr(widget, "cleanup", None)
    if cleanup is not None:
        cleanup()
    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    _app.processEvents()


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
        self.connected = False
        self.started_workers = 0

    @property
    def worker(self):
        return self._worker

    @property
    def virtual_device(self):
        return self._virtual_device

    @property
    def physical_device(self):
        return type("FakeDevice", (), {"name": "Fake DS4"})() if self.connected else None

    @property
    def is_connected(self):
        return self.connected

    def set_profile(self, profile):
        self.profile = profile

    def set_led_color(self, r, g, b):
        self.led = (r, g, b)

    def stop_worker(self):
        if self._worker is not None:
            self._worker.running = False
        return True

    def start_worker(self):
        self.started_workers += 1
        if self._worker is not None:
            self._worker.running = True


class FakeRunningWorker:
    def __init__(self, running=False):
        self.running = running

    def isRunning(self):
        return self.running


class TestOverlayGeometry(unittest.TestCase):
    def setUp(self):
        self.overlay = ControllerOverlayWidget()
        self.overlay.resize(420, 380)

    def tearDown(self):
        _destroy_widget(self.overlay)

    def test_controller_asset_is_square_high_resolution_and_transparent(self):
        from PySide6.QtGui import QImage

        asset = Path(__file__).resolve().parents[1] / "assets" / "ds4_controller.png"
        self.assertTrue(asset.exists(), f"missing asset: {asset}")
        image = QImage(str(asset))
        self.assertGreaterEqual(image.width(), 512)
        self.assertEqual(image.width(), image.height())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_every_hotspot_center_hits_its_own_button(self):
        for code, _symbol, rx, ry, rw, rh, _kind in OVERLAY_BUTTON_DEFS:
            center = self.overlay._button_rect(rx, ry, rw, rh).center()
            self.assertEqual(
                self.overlay._button_at(center),
                code,
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
                        hit,
                        code,
                        f"interior point of {physical_name(code)} at "
                        f"({point.x():.0f},{point.y():.0f}) hit {hit}",
                    )

    def test_all_buttons_present(self):
        codes = {code for code, *_rest in OVERLAY_BUTTON_DEFS}
        for expected in (
            DS4Btn.DPAD_UP,
            DS4Btn.DPAD_DOWN,
            DS4Btn.DPAD_LEFT,
            DS4Btn.DPAD_RIGHT,
            DS4Btn.SOUTH,
            DS4Btn.EAST,
            DS4Btn.NORTH,
            DS4Btn.WEST,
            DS4Btn.TOUCHPAD,
        ):
            self.assertIn(int(expected), codes)

    def test_click_emits_signal(self):
        captured = []
        self.overlay.button_clicked.connect(captured.append)
        code, _s, rx, ry, rw, rh, _k = OVERLAY_BUTTON_DEFS[0]
        center = self.overlay._button_rect(rx, ry, rw, rh).center()
        event = QMouseEvent(
            QEvent.MouseButtonPress,
            center,
            self.overlay.mapToGlobal(center),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        self.overlay.mousePressEvent(event)
        self.assertEqual(captured, [code])

    def test_hat_events_light_up_dpad(self):
        self.overlay.handle_raw_event(3, 16, -1)  # EV_ABS, ABS_HAT0X, left
        self.overlay.handle_raw_event(3, 17, 1)  # ABS_HAT0Y, down
        pressed = {c for c, v in self.overlay._pressed.items() if v}
        self.assertIn(int(DS4Btn.DPAD_LEFT), pressed)
        self.assertIn(int(DS4Btn.DPAD_DOWN), pressed)
        self.overlay.handle_raw_event(3, 16, 0)
        self.overlay.handle_raw_event(3, 17, 0)
        self.assertFalse(any(self.overlay._pressed.values()))

    def test_stick_axis_events_move_both_live_markers(self):
        for side, x_code, y_code in (
            ("left", e.ABS_X, e.ABS_Y),
            ("right", e.ABS_RX, e.ABS_RY),
        ):
            center = self.overlay.stick_marker_position(side)
            for axis_code, value, coordinate, expected in (
                (x_code, 0, "x", -1),
                (x_code, 255, "x", 1),
                (y_code, 0, "y", -1),
                (y_code, 255, "y", 1),
            ):
                self.overlay.handle_raw_event(e.EV_ABS, axis_code, value)
                moved = self.overlay.stick_marker_position(side)
                delta = getattr(moved, coordinate)() - getattr(center, coordinate)()
                self.assertLess(delta, 0) if expected < 0 else self.assertGreater(delta, 0)
                self.overlay.handle_raw_event(e.EV_ABS, axis_code, 127)

            returned = self.overlay.stick_marker_position(side)
            self.assertAlmostEqual(returned.x(), center.x(), delta=1)
            self.assertAlmostEqual(returned.y(), center.y(), delta=1)


class TestApplicationIdentity(unittest.TestCase):
    def test_taskbar_icon_and_desktop_entry_identity_are_set(self):
        from src.main import configure_application_identity

        configure_application_identity(_app)

        self.assertEqual(_app.desktopFileName(), "ds4linux")
        self.assertFalse(_app.windowIcon().isNull())


class TestNameHelpers(unittest.TestCase):
    def test_physical_vs_target_names(self):
        from src.constants import DS4Btn

        self.assertEqual(physical_name(int(DS4Btn.SOUTH)), "✕ Cross")
        self.assertEqual(target_name(int(DS4Btn.SOUTH), VirtualDeviceType.XBOX), "A")
        self.assertEqual(target_name(int(DS4Btn.SOUTH), VirtualDeviceType.PS4), "Cross")


class TestMappingWidget(unittest.TestCase):
    def tearDown(self):
        _destroy_widget(getattr(self, "widget", None))

    def test_mappings_roundtrip(self):
        w = MappingTabWidget()
        self.widget = w
        w.set_mappings({304: 304, 305: 305})
        self.assertEqual(w.get_mappings(), {304: 304, 305: 305})
        w._remove_mapping(304)
        self.assertEqual(w.get_mappings(), {305: 305})

    def test_reset_defaults_fills_everything(self):
        w = MappingTabWidget()
        self.widget = w
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

    def tearDown(self):
        _destroy_widget(getattr(self, "editor", None))

    def test_editor_builds_and_saves(self):
        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        slot = FakeSlot()
        pm = ProfileManager()
        editor = self.editor = ProfileEditorWindow(0, slot, pm)

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
        editor = self.editor = ProfileEditorWindow(0, slot, ProfileManager())
        editor._set_led_color((10, 20, 30))
        self.assertEqual(editor._current_profile.led_color, (10, 20, 30))
        self.assertIsNone(slot.led, "editing a preview must not change the live controller")

    def test_profile_edits_do_not_change_live_virtual_device_before_save(self):
        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        slot = FakeSlot()
        editor = self.editor = ProfileEditorWindow(0, slot, ProfileManager())
        editor.device_type_combo.setCurrentIndex(editor.device_type_combo.findData(VirtualDeviceType.PS4))
        self.assertEqual(slot.virtual_device.device_type, VirtualDeviceType.XBOX)
        self.assertEqual(editor._current_profile.device_type, VirtualDeviceType.XBOX)

    def test_unimplemented_profile_controls_are_disabled_and_explained(self):
        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        editor = self.editor = ProfileEditorWindow(0, FakeSlot(), ProfileManager())
        for control in (
            editor.touchpad_mode,
            editor.touchpad_jitter,
            editor.rumble_enable,
            editor.rumble_intensity,
            editor.gyro_enable,
            editor.gyro_mode,
            editor.gyro_sensitivity,
            editor.gyro_calibrate_btn,
            editor.led_mode,
            editor.auto_reconnect,
        ):
            self.assertFalse(control.isEnabled(), control.objectName() or type(control).__name__)
        self.assertTrue(editor.rumble_test_btn.isEnabled())
        self.assertEqual(editor.led_mode.count(), 1)

    def test_diagnostic_capture_compares_physical_and_virtual_dpad_events(self):
        from evdev import ecodes as e

        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        editor = self.editor = ProfileEditorWindow(0, FakeSlot(), ProfileManager())
        editor.capture_events.setChecked(True)
        editor._on_raw_event(e.EV_KEY, e.BTN_DPAD_UP, 1)
        self.assertIn("Seta ↑ — pressionado", editor.physical_trace.text())
        editor._on_mapped_event(e.EV_ABS, e.ABS_HAT0Y, -1)
        editor._on_raw_event(e.EV_KEY, e.BTN_DPAD_UP, 0)
        editor._on_mapped_event(e.EV_ABS, e.ABS_HAT0Y, 0)

        self.assertIn("Seta ↑ — solto", editor.physical_trace.text())
        self.assertIn("Saída virtual: ABS_HAT0Y = 0", editor.virtual_trace.text())
        capture = editor.capture_text.toPlainText()
        self.assertIn("IN EV_KEY Seta ↑ pressionado", capture)
        self.assertIn("OUT EV_ABS ABS_HAT0Y = -1", capture)
        self.assertIn("IN EV_KEY Seta ↑ solto", capture)
        self.assertNotIn("/dev/input", capture)

    def test_controller_editor_can_stop_and_resume_and_shows_connection_state(self):
        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        slot = FakeSlot()
        editor = self.editor = ProfileEditorWindow(0, slot, ProfileManager())
        self.assertFalse(editor.stop_btn.isEnabled())
        self.assertIn("desconectado", editor.status_label.text())

        slot.connected = True
        slot._worker = FakeRunningWorker(running=True)
        editor._refresh_connection_state()
        self.assertTrue(editor.stop_btn.isEnabled())
        self.assertEqual(editor.stop_btn.text(), "Parar")
        self.assertIn("conectado", editor.connection_status.text().lower())

        editor._toggle_controller_worker()
        self.assertFalse(slot.worker.isRunning())
        self.assertEqual(editor.stop_btn.text(), "Retomar")
        editor._toggle_controller_worker()
        self.assertTrue(slot.worker.isRunning())
        self.assertEqual(slot.started_workers, 1)
        self.assertEqual(editor.stop_btn.text(), "Parar")

    def test_profile_editor_fits_compact_size_and_supports_keyboard_navigation(self):
        from PySide6.QtTest import QTest

        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        editor = self.editor = ProfileEditorWindow(0, FakeSlot(), ProfileManager())
        editor.show()
        editor.resize(800, 600)
        _app.processEvents()

        self.assertEqual((editor.width(), editor.height()), (800, 600))
        self.assertEqual(editor.profile_name_edit.accessibleName(), "Nome do perfil")
        self.assertTrue(editor.stop_btn.accessibleName())
        editor.profile_name_edit.setFocus()
        QTest.keyClick(editor.profile_name_edit, Qt.Key_Tab)
        _app.processEvents()
        self.assertIs(QApplication.focusWidget(), editor.save_btn)

    def test_cleanup_disconnects_raw_worker_signal(self):
        """closeEvent never fires for a widget inside a QTabWidget, so the
        main window calls cleanup() when swapping tabs — without it every
        "edit controller" click leaked one worker.raw_event connection."""
        from PySide6.QtCore import QObject, Signal

        from src.config.profile_manager import ProfileManager
        from src.gui.controller_tab import ProfileEditorWindow

        class FakeWorker(QObject):
            raw_event = Signal(int, int, int)

        worker = FakeWorker()
        slot = FakeSlot()
        editor = self.editor = ProfileEditorWindow(0, slot, ProfileManager())

        received = []
        editor._on_raw_event = lambda t, c, v: received.append((t, c, v))
        worker.raw_event.connect(editor._on_raw_event)
        editor._raw_worker = worker

        worker.raw_event.emit(1, 0x130, 1)
        self.assertEqual(len(received), 1)  # connected

        editor.cleanup()
        worker.raw_event.emit(1, 0x130, 0)
        self.assertEqual(len(received), 1)  # connection dropped
        self.assertIsNone(editor._raw_worker)


class TestSetupDialog(unittest.TestCase):
    def tearDown(self):
        _destroy_widget(getattr(self, "dialog", None))

    def test_setup_dialog_never_collects_or_claims_to_store_password(self):
        from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit

        from src.gui.setup_dialog import SetupDialog

        dialog = self.dialog = SetupDialog()
        self.assertEqual(dialog.findChildren(QLineEdit), [])
        self.assertEqual(dialog.findChildren(QCheckBox), [])
        labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn("opcional", labels)
        self.assertIn("solicitada pelo sistema", labels)
        self.assertNotIn("senha é criptografada", labels.lower())
        self.assertNotIn("lembrar", labels.lower())

    def test_main_window_launch_does_not_wait_for_system_setup(self):
        from src import main

        class SignalStub:
            def connect(self, _callback):
                pass

        class AppStub:
            aboutToQuit = SignalStub()

            def setQuitOnLastWindowClosed(self, _value):
                pass

            def exec(self):
                return 17

        class WindowStub:
            _multi_manager = object()

            def cleanup(self):
                pass

            def show(self):
                pass

        checker = mock.Mock()
        checker.start.return_value = True
        app = AppStub()
        window = WindowStub()
        with (
            mock.patch.object(main, "QApplication", return_value=app),
            mock.patch.object(main, "configure_application_identity"),
            mock.patch.object(main, "InstanceChecker", return_value=checker),
            mock.patch.object(main, "discard_legacy_sudo_secret", return_value=False),
            mock.patch.object(main, "MainWindow", return_value=window),
            mock.patch.object(main.signal, "signal"),
            mock.patch("src.engine.multi_device_manager.MultiDeviceManager.scan_and_assign") as scan,
        ):
            self.assertEqual(main.main(), 17)
        scan.assert_called_once_with(window._multi_manager)

    def test_cancel_waits_for_active_privileged_operation(self):
        from src.gui.setup_dialog import SetupDialog

        class RunningWorker:
            def isRunning(self):
                return True

        dialog = self.dialog = SetupDialog()
        rejected = []
        dialog.rejected.connect(lambda: rejected.append(True))
        dialog._worker = RunningWorker()
        dialog._on_cancel()
        self.assertFalse(dialog._cancel_btn.isEnabled())
        self.assertIn("Aguardando", dialog._status_label.text())
        self.assertEqual(rejected, [])


if __name__ == "__main__":
    unittest.main()
