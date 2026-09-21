"""Tests for the DS4 HID report parser (D-pad, buttons, sticks)."""

import unittest

from evdev import ecodes as e

from src.engine.ds4_hidraw import DPAD_HAT_MAP, parse_ds4_report
from tests.helpers import make_bt_report, make_usb_report


class TestDpadParsing(unittest.TestCase):
    def test_usb_all_hat_values(self):
        for value, (ex, ey) in DPAD_HAT_MAP.items():
            state = parse_ds4_report(make_usb_report(dpad=value))
            self.assertEqual(
                (state['dpad_x'], state['dpad_y']), (ex, ey),
                f"USB hat value {value} parsed wrong",
            )

    def test_bt_all_hat_values(self):
        for value, (ex, ey) in DPAD_HAT_MAP.items():
            state = parse_ds4_report(make_bt_report(dpad=value))
            self.assertEqual(
                (state['dpad_x'], state['dpad_y']), (ex, ey),
                f"BT hat value {value} parsed wrong",
            )

    def test_neutral_is_eight_not_zero(self):
        state = parse_ds4_report(make_usb_report(dpad=8))
        self.assertEqual((state['dpad_x'], state['dpad_y']), (0, 0))

    def test_up_is_zero(self):
        state = parse_ds4_report(make_usb_report(dpad=0))
        self.assertEqual((state['dpad_x'], state['dpad_y']), (0, -1))

    def test_invalid_hat_values_clamped_to_neutral(self):
        for value in range(9, 16):
            state = parse_ds4_report(make_usb_report(dpad=value))
            self.assertEqual((state['dpad_x'], state['dpad_y']), (0, 0))


class TestButtonParsing(unittest.TestCase):
    def test_face_buttons_usb(self):
        state = parse_ds4_report(make_usb_report(b0_extra=0xF0))
        self.assertTrue(state['buttons'][e.BTN_WEST])   # Square
        self.assertTrue(state['buttons'][e.BTN_SOUTH])  # Cross
        self.assertTrue(state['buttons'][e.BTN_EAST])   # Circle
        self.assertTrue(state['buttons'][e.BTN_NORTH])  # Triangle

    def test_shoulders_and_share_options(self):
        state = parse_ds4_report(make_usb_report(b1=0x0F))
        self.assertTrue(state['buttons'][e.BTN_TL])
        self.assertTrue(state['buttons'][e.BTN_TR])
        self.assertTrue(state['buttons'][e.BTN_TL2])
        self.assertTrue(state['buttons'][e.BTN_TR2])
        state = parse_ds4_report(make_usb_report(b1=0xF0))
        self.assertTrue(state['buttons'][e.BTN_SELECT])
        self.assertTrue(state['buttons'][e.BTN_START])
        self.assertTrue(state['buttons'][e.BTN_THUMBL])
        self.assertTrue(state['buttons'][e.BTN_THUMBR])

    def test_ps_and_touchpad(self):
        state = parse_ds4_report(make_usb_report(b2=0x03))
        self.assertTrue(state['buttons'][e.BTN_MODE])
        self.assertTrue(state['touchpad'])
        self.assertTrue(state['buttons'][e.BTN_TOUCH])  # click is a button too

    def test_release_all(self):
        state = parse_ds4_report(make_usb_report())
        self.assertFalse(any(state['buttons'].values()))

    def test_bt_buttons_match_usb(self):
        usb = parse_ds4_report(make_usb_report(dpad=2, b0_extra=0xF0, b1=0xAA, b2=0x01))
        bt = parse_ds4_report(make_bt_report(dpad=2, b0_extra=0xF0, b1=0xAA, b2=0x01))
        self.assertEqual(usb['buttons'], bt['buttons'])
        self.assertEqual((usb['dpad_x'], usb['dpad_y']), (bt['dpad_x'], bt['dpad_y']))


class TestStickAndTriggerParsing(unittest.TestCase):
    def test_sticks_and_triggers_offsets(self):
        state = parse_ds4_report(make_usb_report(lx=10, ly=20, rx=30, ry=40, l2=50, r2=60))
        self.assertEqual(
            (state['lx'], state['ly'], state['rx'], state['ry'], state['l2'], state['r2']),
            (10, 20, 30, 40, 50, 60),
        )

    def test_bt_sticks(self):
        state = parse_ds4_report(make_bt_report(lx=1, ly=2, rx=3, ry=4, l2=5, r2=6))
        self.assertEqual(
            (state['lx'], state['ly'], state['rx'], state['ry'], state['l2'], state['r2']),
            (1, 2, 3, 4, 5, 6),
        )

    def test_empty_and_invalid_reports(self):
        for report in (b"", b"\x00", b"\x99" * 64):
            state = parse_ds4_report(report)
            self.assertEqual((state['dpad_x'], state['dpad_y']), (0, 0))
            self.assertEqual(state['lx'], 128)


class TestReadReport(unittest.TestCase):
    def test_read_report_full_and_short_frames(self):
        """read_report is a plain non-blocking read: whole reports pass,
        anything shorter than MIN_REPORT_SIZE is dropped, and an empty
        queue returns None instead of blocking."""
        import os as _os

        from src.engine.ds4_hidraw import DS4HIDRAWReader

        read_fd, write_fd = _os.pipe()
        _os.set_blocking(read_fd, False)
        reader = DS4HIDRAWReader("/dev/null")
        reader._fd = read_fd
        try:
            _os.write(write_fd, b"\x01" + bytes(63))  # full 64 B USB report
            report = reader.read_report()
            self.assertIsNotNone(report)
            self.assertEqual(len(report), 64)

            self.assertIsNone(reader.read_report())  # empty queue, no block

            _os.write(write_fd, b"\x01\x02")  # 2 B fragment -> dropped
            self.assertIsNone(reader.read_report())
        finally:
            _os.close(read_fd)
            _os.close(write_fd)


class TestVirtualDeviceHelpers(unittest.TestCase):
    def test_event_device_path_none_when_inactive(self):
        from src.engine.virtual_device import VirtualDevice

        vdev = VirtualDevice()
        self.assertIsNone(vdev.event_device_path)
        self.assertLess(vdev.uinput_fd, 0)


if __name__ == "__main__":
    unittest.main()
