"""Physical AbsInfo calibration and paired stick transformations."""

import unittest
from types import SimpleNamespace

from evdev import ecodes as e

from src.constants import MAX_AXIS_VALUE, MAX_TRIGGER_VALUE
from src.engine.input_mapper import AxisConfig, InputMapper, ProfileConfig, TriggerConfig


def abs_info(minimum, maximum, flat=0):
    return SimpleNamespace(min=minimum, max=maximum, flat=flat)


class TestPhysicalAxisRanges(unittest.TestCase):
    def setUp(self):
        self.profile = ProfileConfig()
        self.profile.left_stick = AxisConfig(deadzone=0.0, max_zone=1.0)
        self.profile.right_stick = AxisConfig(deadzone=0.0, max_zone=1.0)
        self.mapper = InputMapper(self.profile)

    def test_signed_range_centers_and_reaches_virtual_extremes(self):
        info = abs_info(-32768, 32767)
        negative = dict(self.mapper.map_axes(e.ABS_X, -32768, info))
        self.assertEqual(negative[e.ABS_X], -MAX_AXIS_VALUE)
        self.mapper.map_axes(e.ABS_X, 0, info)
        positive = dict(self.mapper.map_axes(e.ABS_X, 32767, info))
        self.assertEqual(positive[e.ABS_X], MAX_AXIS_VALUE)
        self.assertEqual(self.mapper.axis_state[e.ABS_X], MAX_AXIS_VALUE)

    def test_asymmetric_range_uses_its_reported_center(self):
        info = abs_info(0, 1023)
        self.mapper.map_axes(e.ABS_X, 512, info)
        self.assertEqual(self.mapper.axis_state[e.ABS_X], 0)
        self.mapper.map_axes(e.ABS_X, 0, info)
        self.assertEqual(self.mapper.axis_state[e.ABS_X], -MAX_AXIS_VALUE)

    def test_rotation_uses_the_other_stick_axis_and_emits_both(self):
        self.profile.left_stick.rotation = 90
        outputs = dict(self.mapper.map_axes(e.ABS_Y, 0, abs_info(0, 255)))
        self.assertEqual(outputs[e.ABS_X], MAX_AXIS_VALUE)
        self.assertEqual(outputs[e.ABS_Y], 0)

    def test_hat_is_discrete_and_not_deadzone_filtered(self):
        self.profile.left_stick.deadzone = 0.99
        self.assertEqual(
            self.mapper.map_axes(e.ABS_HAT0X, -1), [(e.ABS_HAT0X, -1)],
        )

    def test_trigger_uses_physical_range_and_clamps_invalid_profile_values(self):
        self.profile.left_trigger = TriggerConfig(
            deadzone=0, max_zone=0, anti_deadzone=0, sensitivity=1,
        )
        self.mapper.map_axes(e.ABS_Z, 0, abs_info(0, 1023))
        self.assertEqual(self.mapper.axis_state[e.ABS_Z], 0)
        self.mapper.map_axes(e.ABS_Z, 1023, abs_info(0, 1023))
        self.assertEqual(self.mapper.axis_state[e.ABS_Z], MAX_TRIGGER_VALUE)


if __name__ == "__main__":
    unittest.main()
