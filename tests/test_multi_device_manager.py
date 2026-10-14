"""Device path reservation and reconnect routing regressions."""

import unittest
from unittest import mock

from PySide6.QtCore import QObject, Signal

from src.engine.multi_device_manager import MultiDeviceManager


class FakeSlot(QObject):
    device_disconnected = Signal()

    def __init__(self, slot_id, path=None, uniq=None):
        super().__init__()
        self.slot_id = slot_id
        self.device_path = path
        self._last_device_uniq = uniq
        self._connected = path is not None
        self.stops = 0
        self.detaches = 0
        self.starts = 0
        self.profiles = []

    @property
    def is_connected(self):
        return self._connected

    @property
    def device(self):
        return object() if self._connected else None

    def stop_worker(self):
        self.stops += 1

    def detach_device(self):
        self.detaches += 1
        self._connected = False
        self.device_path = None
        self.device_disconnected.emit()

    def set_profile(self, profile):
        self.profiles.append(profile)
        return True

    def attach_device(self, path):
        self._connected = True
        self.device_path = path
        return True

    def start_worker(self):
        self.starts += 1


class TestSlotReservations(unittest.TestCase):
    def setUp(self):
        self.manager = MultiDeviceManager.__new__(MultiDeviceManager)
        QObject.__init__(self.manager)
        self.first = FakeSlot(0, "/dev/input/event0")
        self.second = FakeSlot(1, "/dev/input/event1")
        self.manager._slots = {0: self.first, 1: self.second}
        self.manager._device_paths_in_use = {
            "/dev/input/event0", "/dev/input/event1",
        }
        self.manager._slot_paths = {
            0: "/dev/input/event0", 1: "/dev/input/event1",
        }
        self.first.device_disconnected.connect(
            self.manager._on_slot_device_disconnected,
        )
        self.second.device_disconnected.connect(
            self.manager._on_slot_device_disconnected,
        )

    def test_unexpected_disconnect_releases_only_its_slot_reservation(self):
        self.first.detach_device()
        self.assertNotIn("/dev/input/event0", self.manager._device_paths_in_use)
        self.assertIn("/dev/input/event1", self.manager._device_paths_in_use)
        self.assertNotIn(0, self.manager._slot_paths)
        self.assertEqual(self.manager._slot_paths[1], "/dev/input/event1")

    def test_manual_assignment_does_not_steal_device_from_other_slot(self):
        self.assertFalse(self.manager.connect_slot_to_device(0, "/dev/input/event1"))
        self.assertEqual(self.first.stops, 0)
        self.assertEqual(self.first.detaches, 0)
        self.assertEqual(self.second.device_path, "/dev/input/event1")

    def test_reconnect_returns_to_slot_with_same_unique_id_and_closes_probe(self):
        self.first._connected = False
        self.first.device_path = None
        self.first._last_device_uniq = "controller-uniq"
        self.second._last_device_uniq = "other-uniq"
        self.manager._device_paths_in_use.clear()
        self.manager._slot_paths.clear()
        self.manager._try_assign_device = mock.Mock(return_value=True)
        probe = mock.Mock(uniq="controller-uniq")

        with mock.patch("evdev.InputDevice", return_value=probe):
            self.manager._on_scan_finished(["/dev/input/event-new"])

        probe.close.assert_called_once()
        self.assertEqual(self.first.device_path, "/dev/input/event-new")
        self.assertEqual(self.first.starts, 1)
        self.assertEqual(self.second.starts, 0)
        self.assertEqual(self.manager._slot_paths[0], "/dev/input/event-new")
        self.manager._try_assign_device.assert_not_called()

    def test_auto_profile_load_does_not_overwrite_last_manual_profile(self):
        from src.engine.input_mapper import ProfileConfig

        profile_manager = mock.Mock()
        profile_manager.list_profiles.return_value = ["Game"]
        profile_manager.load_profile.return_value = ProfileConfig(name="Game")
        self.manager._profile_manager = profile_manager
        self.manager._slots = {0: self.first}

        self.assertTrue(self.manager.apply_profile_to_all("Game"))
        profile_manager.load_profile.assert_called_once_with("Game", remember=False)
        self.assertEqual(self.first.profiles[-1].name, "Game")

    def test_auto_profile_rejects_missing_name_instead_of_loading_fallback(self):
        profile_manager = mock.Mock()
        profile_manager.list_profiles.return_value = ["Default"]
        self.manager._profile_manager = profile_manager
        self.manager._slots = {0: self.first}

        self.assertFalse(self.manager.apply_profile_to_all("Missing"))
        profile_manager.load_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
