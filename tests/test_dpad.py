"""Regression tests for the D-pad / HAT handling.

The original bug: pressing UP, then LEFT, then releasing UP kept
``HAT0Y == -1`` forever (stuck diagonal) because the release branch
required the other axis to be neutral.
"""

import unittest

from src.engine.dpad import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    DpadState,
    hat_from_directions,
)


class TestHatFromDirections(unittest.TestCase):
    def test_neutral(self):
        self.assertEqual(hat_from_directions([]), (0, 0))

    def test_cardinals(self):
        self.assertEqual(hat_from_directions([UP]), (0, -1))
        self.assertEqual(hat_from_directions([DOWN]), (0, 1))
        self.assertEqual(hat_from_directions([LEFT]), (-1, 0))
        self.assertEqual(hat_from_directions([RIGHT]), (1, 0))

    def test_diagonals(self):
        self.assertEqual(hat_from_directions([UP, LEFT]), (-1, -1))
        self.assertEqual(hat_from_directions([UP, RIGHT]), (1, -1))
        self.assertEqual(hat_from_directions([DOWN, LEFT]), (-1, 1))
        self.assertEqual(hat_from_directions([DOWN, RIGHT]), (1, 1))

    def test_opposites_cancel(self):
        self.assertEqual(hat_from_directions([UP, DOWN]), (0, 0))
        self.assertEqual(hat_from_directions([LEFT, RIGHT]), (0, 0))
        self.assertEqual(hat_from_directions([UP, DOWN, LEFT]), (-1, 0))


class TestDpadState(unittest.TestCase):
    def test_press_release_single(self):
        st = DpadState()
        self.assertTrue(st.update(UP, True))
        self.assertEqual((st.x, st.y), (0, -1))
        self.assertTrue(st.update(UP, False))
        self.assertEqual((st.x, st.y), (0, 0))

    def test_no_change_reports_false(self):
        st = DpadState()
        st.update(UP, True)
        self.assertFalse(st.update(UP, True))
        st.update(UP, False)
        self.assertFalse(st.update(UP, False))

    def test_diagonal_release_does_not_stick(self):
        """The regression that broke the arrows."""
        st = DpadState()
        st.update(UP, True)
        st.update(LEFT, True)
        self.assertEqual((st.x, st.y), (-1, -1))

        self.assertTrue(st.update(UP, False))
        self.assertEqual((st.x, st.y), (-1, 0), "UP must stop when released")

        self.assertTrue(st.update(LEFT, False))
        self.assertEqual((st.x, st.y), (0, 0))

    def test_release_order_reversed(self):
        st = DpadState()
        st.update(DOWN, True)
        st.update(RIGHT, True)
        self.assertTrue(st.update(RIGHT, False))
        self.assertEqual((st.x, st.y), (0, 1), "RIGHT must stop when released")
        st.update(DOWN, False)
        self.assertEqual((st.x, st.y), (0, 0))

    def test_sliding_between_directions(self):
        """A common D-pad gesture: UP -> UP+RIGHT -> RIGHT."""
        st = DpadState()
        st.update(UP, True)
        st.update(RIGHT, True)
        st.update(UP, False)
        self.assertEqual((st.x, st.y), (1, 0))
        st.update(RIGHT, False)
        self.assertEqual((st.x, st.y), (0, 0))

    def test_reset(self):
        st = DpadState()
        st.update(UP, True)
        st.update(LEFT, True)
        self.assertEqual(st.reset(), (-1, -1))
        self.assertEqual((st.x, st.y), (0, 0))
        self.assertEqual(st.directions, set())


if __name__ == "__main__":
    unittest.main()
