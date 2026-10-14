"""Resource and profile-switch lifecycle regressions."""

import unittest
from unittest import mock

from PySide6.QtCore import QObject

from src.engine.controller_slot import ControllerSlot, SlotStatus
from src.engine.input_mapper import ProfileConfig
from src.engine.virtual_device import VirtualDeviceType


class FakeInputDevice:
    def __init__(self, path):
        self.path = path
        self.name = "Fake DS4"
        self.uniq = "00:11:22:33:44:55"
        self.ungrabbed = False
        self.closed = False

    def grab(self):
        pass

    def ungrab(self):
        self.ungrabbed = True

    def close(self):
        self.closed = True


class BusyInputDevice(FakeInputDevice):
    def grab(self):
        raise OSError("device is already grabbed by Steam Input")


class FakeProfileManager:
    def get_current_profile_name(self):
        return "Default"

    def load_profile(self, name):
        return ProfileConfig(name=name)


class FakeVirtualDevice:
    def __init__(self, device_type, slot_id):
        self.device_type = device_type
        self.active = False
        self.create_calls = 0

    def is_active(self):
        return self.active

    def create(self):
        self.create_calls += 1
        return False


class TestAttachRollback(unittest.TestCase):
    def test_failed_uinput_creation_ungrabs_and_closes_physical_device(self):
        physical = FakeInputDevice("/dev/input/event-test")
        with (
            mock.patch("src.engine.controller_slot.InputDevice", return_value=physical),
            mock.patch("src.engine.controller_slot.VirtualDevice", FakeVirtualDevice),
        ):
            slot = ControllerSlot(0, profile_manager=FakeProfileManager())
            self.assertFalse(slot.attach_device(physical.path))

        self.assertTrue(physical.ungrabbed)
        self.assertTrue(physical.closed)
        self.assertIsNone(slot.device)
        self.assertIsNone(slot.device_path)
        self.assertEqual(slot.status, SlotStatus.ERROR)
        slot.cleanup()

    def test_failed_exclusive_grab_closes_device_without_creating_virtual_duplicate(self):
        physical = BusyInputDevice("/dev/input/event-busy")
        with (
            mock.patch("src.engine.controller_slot.InputDevice", return_value=physical),
            mock.patch("src.engine.controller_slot.VirtualDevice", FakeVirtualDevice),
        ):
            slot = ControllerSlot(0, profile_manager=FakeProfileManager())
            messages = []
            slot.log_message.connect(messages.append)
            self.assertFalse(slot.attach_device(physical.path))

        self.assertTrue(physical.closed)
        self.assertFalse(physical.ungrabbed)
        self.assertIsNone(slot.device)
        self.assertEqual(slot.status, SlotStatus.ERROR)
        self.assertEqual(slot.virtual_device.create_calls, 0)
        self.assertIn("Disable Steam Input", messages[0])
        slot.cleanup()


class TestProfileSwitchGuard(unittest.TestCase):
    def test_does_not_swap_profile_while_worker_is_still_running(self):
        slot = ControllerSlot.__new__(ControllerSlot)
        QObject.__init__(slot)
        old_profile = ProfileConfig(name="old")
        new_profile = ProfileConfig(name="new", device_type=VirtualDeviceType.PS4)
        slot._profile = old_profile
        slot._slot_id = 0
        slot._virtual_device = mock.Mock()
        slot._virtual_device.is_active.return_value = True
        slot._input_mapper = mock.Mock()
        slot._led_controller = mock.Mock()
        slot._macro_engine = mock.Mock()
        slot._macro_engine.pause_and_cancel.return_value = True
        slot._worker = mock.Mock()
        slot._worker.isRunning.return_value = True
        slot._worker.wait.return_value = False
        slot._worker.stop.return_value = None
        slot._worker.isRunning.side_effect = [True, True, True]
        slot._device = None

        self.assertFalse(slot.apply_profile(new_profile))
        self.assertIs(slot.profile, old_profile)
        slot._virtual_device.set_device_type.assert_not_called()
        slot._input_mapper.set_profile.assert_not_called()
        slot._macro_engine.resume.assert_called_once()


if __name__ == "__main__":
    unittest.main()
