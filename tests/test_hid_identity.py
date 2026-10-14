"""Per-controller sysfs identity matching for HID and LEDs."""

import tempfile
import unittest
from pathlib import Path

from src.engine.ds4_hidraw import find_ds4_hidraw
from src.engine.led_controller import LEDController


class TestHidIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_class = self.root / "class-input"
        self.hidraw_class = self.root / "class-hidraw"
        self.leds = self.root / "leds"
        self.hid_a = self.root / "devices" / "hid-a"
        self.hid_b = self.root / "devices" / "hid-b"
        self.hid_a.mkdir(parents=True)
        self.hid_b.mkdir(parents=True)
        for hid, uniq in ((self.hid_a, ""), (self.hid_b, "")):
            (hid / "uevent").write_text(
                "HID_ID=0003:0000054C:000005C4\n"
                "HID_NAME=Wireless Controller\n"
                f"HID_UNIQ={uniq}\n"
            )
        self._link_input("event0", self.hid_a)
        self._link_input("event1", self.hid_b)
        self._link_hidraw("hidraw0", self.hid_a)
        self._link_hidraw("hidraw1", self.hid_b)
        self._link_led("input0", self.hid_a)
        self._link_led("input1", self.hid_b)

    def tearDown(self):
        self.tmp.cleanup()

    def _link_input(self, event_name, hid):
        target = hid / "input" / "input0" / event_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        self.input_class.mkdir(parents=True, exist_ok=True)
        (self.input_class / event_name).symlink_to(target)

    def _link_hidraw(self, node, hid):
        link = self.hidraw_class / node / "device"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(hid)

    def _link_led(self, base, hid):
        for color in ("red", "green", "blue"):
            link = self.leds / f"{base}:{color}" / "device"
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(hid)

    def test_two_usb_controllers_without_uniq_map_to_their_own_hidraw(self):
        self.assertEqual(
            find_ds4_hidraw(input_device_path="/dev/input/event0",
                            sys_class_input=self.input_class,
                            sys_class_hidraw=self.hidraw_class),
            "/dev/hidraw0",
        )
        self.assertEqual(
            find_ds4_hidraw(input_device_path="/dev/input/event1",
                            sys_class_input=self.input_class,
                            sys_class_hidraw=self.hidraw_class),
            "/dev/hidraw1",
        )

    def test_ambiguous_global_fallback_is_refused(self):
        self.assertIsNone(find_ds4_hidraw(
            sys_class_hidraw=self.hidraw_class,
        ))

    def test_unique_id_match_is_exact(self):
        (self.hid_b / "uevent").write_text(
            "HID_ID=0003:0000054C:000005C4\n"
            "HID_NAME=Wireless Controller\nHID_UNIQ=AA:BB:CC\n"
        )
        self.assertEqual(find_ds4_hidraw(
            "aa:bb:cc", sys_class_hidraw=self.hidraw_class,
        ), "/dev/hidraw1")
        self.assertIsNone(find_ds4_hidraw(
            "ff:ee:dd", sys_class_hidraw=self.hidraw_class,
        ))

    def test_led_selection_matches_parent_and_has_no_first_device_fallback(self):
        self.assertEqual(LEDController.find_ds4_led(
            "/dev/input/event1", sys_class_input=self.input_class,
            sys_leds_base=self.leds,
        ), self.leds / "input1")
        self.assertIsNone(LEDController.find_ds4_led(
            "/dev/input/event2", sys_class_input=self.input_class,
            sys_leds_base=self.leds,
        ))


if __name__ == "__main__":
    unittest.main()
