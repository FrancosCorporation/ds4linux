import unittest

from evdev import ecodes as e

from src.engine.input_mapper import InputMapper, ProfileConfig


class TestButtonMapping(unittest.TestCase):
    def test_ev_key_repeat_does_not_release_held_destination(self):
        mapper = InputMapper(ProfileConfig(button_maps={e.BTN_SOUTH: e.BTN_A}))
        self.assertEqual(mapper.map_button(e.BTN_SOUTH, 1), (e.BTN_A, 1))
        self.assertIsNone(mapper.map_button(e.BTN_SOUTH, 2))
        self.assertTrue(mapper.button_state[e.BTN_SOUTH])
        self.assertEqual(mapper.map_button(e.BTN_SOUTH, 0), (e.BTN_A, 0))

    def test_shared_destination_stays_pressed_until_last_source_releases(self):
        mapper = InputMapper(ProfileConfig(button_maps={
            e.BTN_SOUTH: e.BTN_A,
            e.BTN_EAST: e.BTN_A,
        }))
        self.assertEqual(mapper.map_button(e.BTN_SOUTH, 1), (e.BTN_A, 1))
        self.assertIsNone(mapper.map_button(e.BTN_EAST, 1))
        self.assertIsNone(mapper.map_button(e.BTN_SOUTH, 0))
        self.assertEqual(mapper.map_button(e.BTN_EAST, 0), (e.BTN_A, 0))

    def test_release_uses_the_destination_that_was_pressed(self):
        mapper = InputMapper(ProfileConfig(button_maps={e.BTN_SOUTH: e.BTN_A}))
        self.assertEqual(mapper.map_button(e.BTN_SOUTH, 1), (e.BTN_A, 1))
        mapper.profile.button_maps[e.BTN_SOUTH] = e.BTN_B
        self.assertEqual(mapper.map_button(e.BTN_SOUTH, 0), (e.BTN_A, 0))

    def test_unmapped_input_is_suppressed(self):
        mapper = InputMapper(ProfileConfig(button_maps={}))
        self.assertIsNone(mapper.map_button(e.BTN_SOUTH, 1))
        self.assertIsNone(mapper.map_button(e.BTN_SOUTH, 0))


if __name__ == "__main__":
    unittest.main()
