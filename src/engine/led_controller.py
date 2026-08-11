from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class LEDController:
    """
    Controls DS4 LED via the kernel's LED sysfs interface.

    For DS4 controllers, the kernel creates LED directories under
    /sys/class/leds/ named like:
      - input33:red   (controls red channel brightness)
      - input33:green
      - input33:blue
      - input33:brightness (overall brightness)

    Each directory contains a 'brightness' file we can write 0-255 to.
    """

    def __init__(self, led_path: Optional[Path] = None):
        self._led_path: Optional[Path] = None
        self._red_path: Optional[Path] = None
        self._green_path: Optional[Path] = None
        self._blue_path: Optional[Path] = None
        self._brightness_path: Optional[Path] = None
        self._max_brightness = 255
        self._current_color: Tuple[int, int, int] = (0, 0, 255)
        self._enabled = True

        if led_path:
            self.set_led_path(led_path)
        # Do not auto-discover here - let ControllerSlot.set_led_path()
        # explicitly set the correct LED path for each device

    def _auto_discover(self):
        """Discover LED sysfs paths for any DS4 controller."""
        from ..constants import SYS_LEDS_BASE

        try:
            for entry in SYS_LEDS_BASE.iterdir():
                if not entry.is_dir():
                    continue
                name = entry.name.lower()
                # Match patterns like input33:red, sony-controller:red
                if name.endswith(":red") or ":red" in name:
                    # Check for sibling green/blue dirs
                    base = entry.name[:-3]  # Remove ":red" suffix
                    green = SYS_LEDS_BASE / f"{base}:green"
                    blue = SYS_LEDS_BASE / f"{base}:blue"
                    brightness = SYS_LEDS_BASE / f"{base}:brightness"

                    if green.exists() and blue.exists():
                        self._red_path = entry / "brightness"
                        self._green_path = green / "brightness"
                        self._blue_path = blue / "brightness"
                        if brightness.exists():
                            self._brightness_path = brightness / "brightness"
                        self._led_path = SYS_LEDS_BASE / base

                        # Read max brightness
                        max_bright = entry / "max_brightness"
                        if max_bright.exists():
                            try:
                                with open(max_bright, "r") as f:
                                    self._max_brightness = int(f.read().strip())
                            except (OSError, ValueError):
                                pass
                        logger.info(f"Found DS4 LED at {base}")
                        return
        except Exception as e:
            logger.debug(f"Auto-discovery failed: {e}")

    def _init_from_path(self, led_path: Path):
        """Initialize from the input base directory (without :red/:green/:blue suffix)."""
        from ..constants import SYS_LEDS_BASE

        self._led_path = led_path

        # Look for the three color subdirectories
        red_dir = SYS_LEDS_BASE / f"{led_path.name}:red"
        green_dir = SYS_LEDS_BASE / f"{led_path.name}:green"
        blue_dir = SYS_LEDS_BASE / f"{led_path.name}:blue"
        brightness_dir = SYS_LEDS_BASE / f"{led_path.name}:brightness"

        # Also try just appending the path
        if not red_dir.exists():
            red_dir = led_path / "red"
        if not green_dir.exists():
            green_dir = led_path / "green"
        if not blue_dir.exists():
            blue_dir = led_path / "blue"

        if red_dir.exists() and (red_dir / "brightness").exists():
            self._red_path = red_dir / "brightness"
        if green_dir.exists() and (green_dir / "brightness").exists():
            self._green_path = green_dir / "brightness"
        if blue_dir.exists() and (blue_dir / "brightness").exists():
            self._blue_path = blue_dir / "brightness"
        if brightness_dir.exists() and (brightness_dir / "brightness").exists():
            self._brightness_path = brightness_dir / "brightness"

        # Read max brightness
        max_file = red_dir / "max_brightness" if red_dir.exists() else None
        if max_file and max_file.exists():
            try:
                with open(max_file, "r") as f:
                    self._max_brightness = int(f.read().strip())
            except (OSError, ValueError):
                pass

    def set_led_path(self, led_path: Path):
        """Set LED path - should be the input device base dir or the parent of color dirs."""
        self._led_path = led_path
        self._init_from_path(led_path)

    def set_color(self, r: int, g: int, b: int):
        """Set LED color by writing to sysfs brightness files."""
        if not self._enabled:
            return
        self._current_color = (r, g, b)

        # Try writing to color-specific brightness files
        success = False
        for path, val in [
            (self._red_path, r),
            (self._green_path, g),
            (self._blue_path, b),
        ]:
            if path:
                try:
                    with open(path, "w") as f:
                        f.write(str(val))
                    success = True
                except PermissionError:
                    logger.warning("Permission denied writing to LED sysfs - check udev rules")
                except OSError as e:
                    logger.debug(f"Failed to write {path}: {e}")

        if not success and not (self._red_path or self._green_path or self._blue_path):
            logger.debug(f"LED color set to ({r}, {g}, {b}) - no hardware interface")

    def set_brightness(self, brightness: int):
        """Set overall LED brightness via sysfs."""
        if not self._enabled or not self._brightness_path:
            return
        try:
            value = max(0, min(brightness, self._max_brightness))
            with open(self._brightness_path, "w") as f:
                f.write(str(value))
        except PermissionError:
            logger.warning("Permission denied writing brightness to LED sysfs")
        except OSError as e:
            logger.error(f"Failed to set LED brightness: {e}")

    def get_color(self) -> Tuple[int, int, int]:
        return self._current_color

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self.set_color(0, 0, 0)

    def is_available(self) -> bool:
        """Check if at least one LED color path is available."""
        return bool(self._red_path or self._green_path or self._blue_path)

    @staticmethod
    def find_ds4_led(device_path: str) -> Optional[Path]:
        """
        Find the LED sysfs directory for a DS4 controller.
        
        Method: Follow the sysfs symlink from /sys/class/input/eventN/device
        to find the HID device, then look for LED dirs in /sys/class/leds/
        that point to the same HID device.
        """
        from ..constants import SYS_LEDS_BASE
        from pathlib import Path as P

        try:
            event_name = P(device_path).name  # "event19"
            
            # Follow the device symlink: /sys/class/input/event19/device -> ../../input52
            input_link = P(f"/sys/class/input/{event_name}/device")
            if not input_link.exists():
                # Try alternative path
                input_link = P(f"/sys/class/input/{event_name}")
            
            if input_link.exists():
                # Resolve the symlink to find the actual device path
                device_sysfs = input_link.resolve()
                # Extract input device name (e.g., "input52" from path)
                device_name = device_sysfs.name
                
                # Look for LED dirs that have this device as parent
                # LED dirs are like input52:red, input52:green, input52:blue
                base_name = device_name  # e.g., "input52"
                red_dir = SYS_LEDS_BASE / f"{base_name}:red"
                if red_dir.exists():
                    return SYS_LEDS_BASE / base_name

            # Fallback: scan all LED directories and match by device symlink
            input_sysfs = P(f"/sys/class/input/{event_name}")
            if input_sysfs.exists():
                try:
                    resolved_input = input_sysfs.resolve()
                except (OSError, RuntimeError):
                    return None

            for entry in SYS_LEDS_BASE.iterdir():
                if not entry.is_dir():
                    continue
                name_lower = entry.name.lower()
                if ":red" not in name_lower and ":green" not in name_lower and ":blue" not in name_lower:
                    continue
                
                # Check if this LED's device matches our input device
                device_link = entry / "device"
                if device_link.exists():
                    try:
                        led_device = device_link.resolve()
                        # Match by checking if the HID device path matches
                        if input_sysfs.exists():
                            # The LED device symlink points to something like
                            # ../../../0005:054C:05C4.0006 which should match
                            # the input device's parent directory
                            led_parent = led_device.parent
                            if str(led_parent) == str(resolved_input):
                                base = entry.name.split(":")[0]
                                return SYS_LEDS_BASE / base
                    except (OSError, RuntimeError):
                        continue

            # Second fallback: just look for any LED with red/green/blue trio
            for entry in SYS_LEDS_BASE.iterdir():
                if not entry.is_dir():
                    continue
                if ":red" in entry.name:
                    base = entry.name.replace(":red", "")
                    green = SYS_LEDS_BASE / f"{base}:green"
                    blue = SYS_LEDS_BASE / f"{base}:blue"
                    if green.exists() and blue.exists():
                        return SYS_LEDS_BASE / base

        except Exception as e:
            logger.debug(f"Error finding DS4 LED for {device_path}: {e}")

        return None