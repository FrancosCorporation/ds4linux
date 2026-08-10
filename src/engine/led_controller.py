from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class LEDController:
    def __init__(self, led_path: Optional[Path] = None):
        self._led_path = led_path
        self._brightness_path: Optional[Path] = None
        self._color_paths: dict = {}
        self._max_brightness = 255
        self._current_color = (0, 0, 255)
        self._enabled = True
        if led_path:
            self._discover_led_files()

    def _discover_led_files(self):
        if not self._led_path or not self._led_path.exists():
            return
        try:
            brightness_file = self._led_path / "brightness"
            if brightness_file.exists():
                self._brightness_path = brightness_file
                with open(self._led_path / "max_brightness", "r") as f:
                    self._max_brightness = int(f.read().strip())
            for color in ("red", "green", "blue"):
                color_file = self._led_path / f"color_{color}"
                if color_file.exists():
                    self._color_paths[color] = color_file
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to discover LED files: {e}")

    def set_led_path(self, led_path: Path):
        self._led_path = led_path
        self._discover_led_files()

    def set_color(self, r: int, g: int, b: int):
        if not self._enabled:
            return
        self._current_color = (r, g, b)
        if not self._color_paths:
            return
        try:
            for color, value in zip(("red", "green", "blue"), (r, g, b)):
                path = self._color_paths.get(color)
                if path:
                    with open(path, "w") as f:
                        f.write(str(value))
        except OSError as e:
            logger.error(f"Failed to set LED color: {e}")

    def set_brightness(self, brightness: int):
        if not self._enabled or not self._brightness_path:
            return
        try:
            value = max(0, min(brightness, self._max_brightness))
            with open(self._brightness_path, "w") as f:
                f.write(str(value))
        except OSError as e:
            logger.error(f"Failed to set LED brightness: {e}")

    def get_color(self) -> Tuple[int, int, int]:
        return self._current_color

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self.set_color(0, 0, 0)

    def is_available(self) -> bool:
        return bool(self._color_paths)

    @staticmethod
    def find_ds4_led(device_path: str) -> Optional[Path]:
        try:
            name = Path(device_path).name
            for led in Path("/sys/class/leds").glob(f"*{name}*"):
                if led.is_dir() and (led / "color_red").exists():
                    return led
        except OSError:
            pass
        return None