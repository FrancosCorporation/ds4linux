"""D-pad (HAT switch) helpers shared by the evdev and HIDRAW input paths.

The DS4 exposes its D-pad in two different ways depending on the kernel
driver:

* ``hid-sony`` (older kernels) reports the four directions as
  ``BTN_DPAD_*`` key events.
* ``hid-playstation`` (newer kernels) reports them as ``ABS_HAT0X`` /
  ``ABS_HAT0Y`` axes with values ``-1/0/1``.

Both must end up as a single HAT axis pair on the virtual device.  The
state machine below keeps the pressed directions in a set so diagonals
work correctly and releasing one direction never gets stuck while
another direction is still held.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)

UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"

DIRECTIONS = (UP, DOWN, LEFT, RIGHT)


def hat_from_directions(directions: Iterable[str]) -> tuple[int, int]:
    """Return the ``(x, y)`` HAT value for a set of pressed directions.

    ``y`` is ``-1`` for UP (evdev/Linux convention) and ``+1`` for DOWN.
    Opposite directions cancel each other out, which is also what the
    kernel does when it converts the DS4's 8-way hat value.
    """
    given = set(directions)
    invalid = given - set(DIRECTIONS)
    if invalid:
        logger.warning("hat_from_directions: ignoring invalid directions %s", invalid)
    pressed = given & set(DIRECTIONS)
    x = -1 if LEFT in pressed and RIGHT not in pressed else (
        1 if RIGHT in pressed and LEFT not in pressed else 0)
    y = -1 if UP in pressed and DOWN not in pressed else (
        1 if DOWN in pressed and UP not in pressed else 0)
    return x, y


class DpadState:
    """Tracks pressed ``BTN_DPAD_*`` directions and exposes HAT values."""

    def __init__(self) -> None:
        self._directions: set[str] = set()
        self._x = 0
        self._y = 0

    @property
    def x(self) -> int:
        return self._x

    @property
    def y(self) -> int:
        return self._y

    @property
    def directions(self) -> set[str]:
        return set(self._directions)

    def update(self, direction: str | None, pressed: bool) -> bool:
        """Apply a direction press/release.

        Returns ``True`` when the resulting HAT value changed, so the
        caller only writes to the virtual device when needed.
        """
        if direction is None:
            return False
        if direction not in DIRECTIONS:
            logger.warning("DpadState.update: invalid direction %r", direction)
            return False
        if pressed:
            self._directions.add(direction)
        else:
            self._directions.discard(direction)
        x, y = hat_from_directions(self._directions)
        changed = (x, y) != (self._x, self._y)
        self._x, self._y = x, y
        return changed

    def reset(self) -> tuple[int, int]:
        """Release every direction, returning the old ``(x, y)`` HAT."""
        old = (self._x, self._y)
        self._directions.clear()
        self._x = self._y = 0
        return old
