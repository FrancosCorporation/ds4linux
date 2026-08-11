from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, List
import logging
import struct
import zlib
import os

from . import device_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LED sysfs patterns by driver
# ---------------------------------------------------------------------------
# hid-sony (older kernels):  inputNN:red, inputNN:green, inputNN:blue, inputNN:global
# hid-playstation (kernel 6.2+):  inputNN:rgb:indicator (single "colors" file with hex RGB)
# ---------------------------------------------------------------------------

UDEVS_RULE_HINT = (
    "Permissao negada ao acessar LED/HID. Execute:\n"
    "  sudo cp <projeto>/udev/99-ds4linux.rules /etc/udev/rules.d/\n"
    "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
    "Ou adicione manualmente ao /etc/udev/rules.d/99-ds4linux.rules:\n"
    '  SUBSYSTEM=="leds", KERNEL=="input*:red", MODE="0666", TAG+="uaccess"\n'
    '  SUBSYSTEM=="leds", KERNEL=="input*:green", MODE="0666", TAG+="uaccess"\n'
    '  SUBSYSTEM=="leds", KERNEL=="input*:blue", MODE="0666", TAG+="uaccess"\n'
    '  SUBSYSTEM=="leds", KERNEL=="input*:global", MODE="0666", TAG+="uaccess"\n'
    '  SUBSYSTEM=="leds", KERNEL=="input*:rgb:*", MODE="0666", TAG+="uaccess"\n'
    '  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", MODE="0666", TAG+="uaccess"\n'
)


class LEDController:
    """
    Controls DS4 LED via multiple backends depending on kernel driver:

    Priority 1: HID output report (78 bytes, BT format) — primary for BT controllers.
    Priority 2: sysfs `colors` file (hid-playstation driver, hex RGB like "FF0000").
    Priority 3: sysfs `multi_intensity` file (hid-playstation, intensity per channel).
    Priority 4: sysfs individual brightness files (hid-sony driver, :red/:green/:blue).
    Priority 5: sysfs global brightness (on/off only, works as last resort).

    The GUI virtual LED display is always driven by sysfs brightness files.
    """

    def __init__(self, led_path: Optional[Path] = None):
        self._led_path: Optional[Path] = None
        self._hid_device_path: Optional[Path] = None  # Specific hidraw device
        # Old driver (hid-sony) paths
        self._red_path: Optional[Path] = None
        self._green_path: Optional[Path] = None
        self._blue_path: Optional[Path] = None
        self._brightness_path: Optional[Path] = None
        # New driver (hid-playstation) paths
        self._colors_path: Optional[Path] = None       # inputNN:rgb:indicator/colors
        self._multi_intensity_path: Optional[Path] = None
        self._global_path: Optional[Path] = None

        self._max_brightness = 255
        self._current_color: Tuple[int, int, int] = (0, 0, 255)
        self._enabled = True
        self._driver: Optional[str] = None  # 'sony' | 'playstation' | None

        if led_path:
            self.set_led_path(led_path)

    # ------------------------------------------------------------------
    # Driver detection
    # ------------------------------------------------------------------
    @staticmethod
    def detect_driver() -> Optional[str]:
        """Detect whether hid-sony or hid-playstation driver is active."""
        drivers_dir = Path("/sys/bus/hid/drivers")
        if not drivers_dir.exists():
            return None
        for entry in drivers_dir.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name.lower()
            if name == "playstation":
                return "playstation"
            if name == "sony":
                return "sony"
        return None

    @staticmethod
    def _find_input_device_name(device_path: str) -> Optional[str]:
        """Extract the input device name (e.g. 'input171') from an event path."""
        from pathlib import Path as P
        try:
            event_name = P(device_path).name  # e.g. "event19"
            input_sysfs = P(f"/sys/class/input/{event_name}")
            if input_sysfs.exists():
                resolved = input_sysfs.resolve()
                return resolved.name  # e.g. "input171"
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # LED path discovery
    # ------------------------------------------------------------------
    def _discover_led_paths(self, led_base: Path):
        """Discover all available LED sysfs paths under the given base directory."""
        from ..constants import SYS_LEDS_BASE

        self._led_path = led_base
        base_name = led_base.name

        # --- New driver format: inputNN:rgb:indicator ---
        rgb_indicator = SYS_LEDS_BASE / f"{base_name}:rgb:indicator"
        if rgb_indicator.exists():
            colors_file = rgb_indicator / "colors"
            if colors_file.exists():
                self._colors_path = colors_file
            multi_file = rgb_indicator / "multi_intensity"
            if multi_file.exists():
                self._multi_intensity_path = multi_file
            logger.info(f"Detected hid-playstation driver: rgb:indicator at {rgb_indicator}")

        # --- Old driver format: inputNN:red, inputNN:green, inputNN:blue ---
        red_dir = SYS_LEDS_BASE / f"{base_name}:red"
        green_dir = SYS_LEDS_BASE / f"{base_name}:green"
        blue_dir = SYS_LEDS_BASE / f"{base_name}:blue"
        global_dir = SYS_LEDS_BASE / f"{base_name}:global"
        brightness_dir = SYS_LEDS_BASE / f"{base_name}:brightness"

        for d, attr in [
            (red_dir, "_red_path"),
            (green_dir, "_green_path"),
            (blue_dir, "_blue_path"),
        ]:
            if d.exists():
                bf = d / "brightness"
                if bf.exists():
                    setattr(self, attr, bf)

        # global/brightness — used for virtual display and on/off
        if global_dir.exists():
            gb = global_dir / "brightness"
            if gb.exists():
                self._global_path = gb
        elif brightness_dir.exists():
            bb = brightness_dir / "brightness"
            if bb.exists():
                self._brightness_path = bb

        # Read max_brightness from any available channel
        for probe_dir in [red_dir, green_dir, blue_dir]:
            if probe_dir.exists():
                mb = probe_dir / "max_brightness"
                if mb.exists():
                    try:
                        self._max_brightness = int(mb.read_text().strip())
                    except (OSError, ValueError):
                        pass
                    break

        # Detect driver from sysfs
        self._driver = self.detect_driver()
        if not self._driver:
            if self._colors_path:
                self._driver = "playstation"
            elif self._red_path or self._green_path or self._blue_path:
                self._driver = "sony"

        logger.info(
            f"LED paths discovered: colors={self._colors_path}, "
            f"red={self._red_path}, green={self._green_path}, blue={self._blue_path}, "
            f"global={self._global_path}, driver={self._driver}"
        )

    def set_led_path(self, led_path: Path):
        """Set LED path — the base LED directory (e.g. /sys/class/leds/input171)."""
        self._discover_led_paths(led_path)

    def set_hid_device(self, hid_path: Path):
        """Set the specific HID device path for this controller (e.g. /dev/hidraw3)."""
        self._hid_device_path = hid_path
        logger.info(f"LEDController HID device set to: {hid_path}")

    # ------------------------------------------------------------------
    # Color setting — multi-fallback cascade
    # ------------------------------------------------------------------
    def set_color(self, r: int, g: int, b: int):
        """
        Set LED color using the best available method:
          1. HID output report (78 bytes BT format)
          2. sysfs `colors` (hid-playstation, hex RGB)
          3. sysfs individual brightness (hid-sony, :red/:green/:blue)
          4. sysfs global brightness (on/off)
        """
        if not self._enabled:
            logger.debug("set_color: LED disabled, skipping")
            return
        self._current_color = (r, g, b)

        # --- Priority 1: HID output report ---
        if self._send_hid_report(self._make_hid_output_report(r, g, b)):
            return

        # --- Priority 2: hid-playstation `colors` file (hex RRGGBB) ---
        if self._colors_path:
            hex_color = f"{r:02X}{g:02X}{b:02X}"
            if self._write_sysfs(self._colors_path, hex_color):
                logger.info(f"LED color ({r},{g},{b}) via sysfs colors ({hex_color})")
                return

        # --- Priority 3: hid-sony individual brightness files ---
        if self._red_path or self._green_path or self._blue_path:
            written_any = False
            for path, val in [
                (self._red_path, r),
                (self._green_path, g),
                (self._blue_path, b),
            ]:
                if path and self._write_sysfs(path, str(val)):
                    written_any = True
            if written_any:
                logger.info(f"LED color ({r},{g},{b}) via sysfs brightness channels")
                return

        # --- Priority 4: global brightness (on/off only) ---
        if self._global_path:
            luminance = (r + g + b) // 3
            self._write_sysfs(self._global_path, "1" if luminance > 85 else "0")

        # No successful write — log helpful hint
        logger.warning(
            f"LED color ({r},{g},{b}) — all write methods failed. "
            f"{UDEVS_RULE_HINT.strip()}"
        )

    def _send_hid_report(self, report: bytes) -> bool:
        """Send HID output report to DS4. Returns True on success."""
        try:
            # Use specific HID device if set, otherwise find first available
            if self._hid_device_path:
                hid_path = self._hid_device_path
            else:
                # Fallback: find any HID device
                hid_devs = device_manager.DeviceManager.get_all_hid_devices()
                if not hid_devs:
                    return False
                hid_path = Path("/dev/hidraw0")  # Will be opened/closed
                # Find the actual path
                for fd in hid_devs:
                    import os
                    # We can't get path from fd, so just use get_hid_device
                    pass
                hid_fd = device_manager.DeviceManager.get_hid_device()
                if hid_fd is None:
                    return False
                os.write(hid_fd, report)
                os.close(hid_fd)
                logger.info(f"LED color ({self._current_color[0]},{self._current_color[1]},{self._current_color[2]}) via HID output report")
                return True

            # Open the specific HID device
            if not hid_path.exists():
                logger.warning(f"HID device not found: {hid_path}")
                return False

            fd = os.open(str(hid_path), os.O_RDWR)
            os.write(fd, report)
            os.close(fd)
            logger.info(f"LED color ({self._current_color[0]},{self._current_color[1]},{self._current_color[2]}) via {hid_path}")
            return True
        except Exception as e:
            logger.warning(f"HID output report failed: {e}")
            return False

    def _write_sysfs(self, path: Path, value: str) -> bool:
        """Write to a sysfs file with proper PermissionError handling."""
        try:
            with open(path, "w") as f:
                f.write(value)
            return True
        except PermissionError:
            logger.error(
                f"Permission denied writing {path}. "
                f"{UDEVS_RULE_HINT.strip()}"
            )
            return False
        except OSError as e:
            logger.warning(f"Failed to write {path}: {e}")
            return False

    # ------------------------------------------------------------------
    # HID output report (78 bytes, BT format)
    # ------------------------------------------------------------------
    def _make_hid_output_report(self, r: int, g: int, b: int) -> bytes:
        """
        Build the DS4 Bluetooth output report (78 bytes) for color setting.

        Report layout:
          byte 0x00: report_id        = 0x11
          byte 0x01: hw_control       = 0xC4 (HID | CRC32 | 4ms poll)
          byte 0x02: audio_control    = 0x00
          byte 0x03: valid_flag0      = 0x03 (bit0=motor, bit1=LED)
          byte 0x04: valid_flag1      = 0x00
          byte 0x05: reserved         = 0x00
          byte 0x06: motor_right      = 0x00
          byte 0x07: motor_left       = 0x00
          byte 0x08: lightbar_red     = r
          byte 0x09: lightbar_green   = g
          byte 0x0A: lightbar_blue    = b
          byte 0x0B: lightbar_blink_on      = 0x00
          byte 0x0C: lightbar_blink_off     = 0x00
          bytes 0x0D–0x49: reserved (zero)
          bytes 0x4A–0x4D: CRC32 (seed 0xA2, over bytes 0x00–0x49)
          bytes 0x4E–0x4D: padding to 78
        """
        rep = bytearray(78)
        rep[0]  = 0x11
        rep[1]  = 0x80 | 0x40 | 0x04   # hw_control
        rep[2]  = 0x00                  # audio_control
        rep[3]  = 0x01 | 0x02           # valid_flag0: LED + motor
        rep[4]  = 0x00                  # valid_flag1
        rep[5]  = 0x00                  # reserved
        rep[6]  = 0x00                  # motor_right
        rep[7]  = 0x00                  # motor_left
        rep[8]  = r                     # lightbar_red
        rep[9]  = g                     # lightbar_green
        rep[10] = b                     # lightbar_blue
        rep[11] = 0x00                  # blink_on
        rep[12] = 0x00                  # blink_off
        # bytes 13..73 remain zero

        # CRC32: seed 0xA2, computed over bytes 0x00..0x49
        crc = zlib.crc32(bytes([0xA2]), 0xFFFFFFFF)
        crc = ~zlib.crc32(bytes(rep[0:74]), crc) & 0xFFFFFFFF
        struct.pack_into("<I", rep, 74, crc)
        return bytes(rep)

    # ------------------------------------------------------------------
    # Brightness (virtual display)
    # ------------------------------------------------------------------
    def set_brightness(self, brightness: int):
        """
        Set overall LED brightness.
        Writes to global/brightness for virtual display.
        Also scales individual channels proportionally for physical LED.
        """
        if not self._enabled:
            return
        value = max(0, min(brightness, self._max_brightness))

        # Update virtual display (global/brightness)
        target = self._brightness_path or self._global_path
        if target:
            self._write_sysfs(target, str(value))

        # Scale individual color channels proportionally
        if self._red_path and self._current_color != (0, 0, 0):
            scale = value / self._max_brightness if self._max_brightness else 1.0
            r, g, b = self._current_color
            self._write_sysfs(self._red_path, str(int(r * scale)))
            self._write_sysfs(self._green_path, str(int(g * scale)))
            self._write_sysfs(self._blue_path, str(int(b * scale)))

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_color(self) -> Tuple[int, int, int]:
        return self._current_color

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self.set_color(0, 0, 0)

    def is_available(self) -> bool:
        """Check if at least one LED path is available."""
        return bool(
            self._red_path or self._green_path or self._blue_path
            or self._colors_path or self._global_path
        )

    def get_driver(self) -> Optional[str]:
        """Return detected driver name: 'sony', 'playstation', or None."""
        return self._driver

    # ------------------------------------------------------------------
    # Static: find DS4 LED sysfs base path
    # ------------------------------------------------------------------
    @staticmethod
    def find_ds4_led(device_path: str) -> Optional[Path]:
        """
        Find the LED sysfs base directory for a DS4 controller.
        """
        from ..constants import SYS_LEDS_BASE
        from pathlib import Path as P

        try:
            input_sysfs = P(f"/sys/class/input/{P(device_path).name}")
            if not input_sysfs.exists():
                return None

            # Resolve to full sysfs path
            try:
                resolved_input = input_sysfs.resolve()
            except (OSError, RuntimeError):
                return None

            # Path looks like: .../hci0:1/0005:054C:05C4.001A/input/input185
            # LED symlinks point to: .../hci0:1/0005:054C:05C4.001A
            # We need to go up 2 levels from resolved_input
            hid_device = resolved_input.parent.parent  # Skip /input/input185

            # Search for LED directories pointing to this HID device
            for entry in SYS_LEDS_BASE.iterdir():
                if not entry.is_dir():
                    continue

                name = entry.name
                if ":" not in name:
                    continue

                # Extract base name (e.g., "input185" from "input185:red")
                base = name.split(":")[0]

                # Check if red/green/blue exist
                red_dir = SYS_LEDS_BASE / f"{base}:red"
                green_dir = SYS_LEDS_BASE / f"{base}:green"
                blue_dir = SYS_LEDS_BASE / f"{base}:blue"

                if not (red_dir.exists() and green_dir.exists() and blue_dir.exists()):
                    continue

                # Check device symlink
                dev_link = red_dir / "device"
                if not dev_link.exists():
                    continue

                try:
                    led_device = dev_link.resolve()
                    if str(led_device) == str(hid_device):
                        return SYS_LEDS_BASE / base
                except (OSError, RuntimeError):
                    continue

            # Fallback: return first LED tree
            for entry in SYS_LEDS_BASE.iterdir():
                if not entry.is_dir():
                    continue
                name = entry.name
                if ":red" in name:
                    base = name.replace(":red", "")
                    if (SYS_LEDS_BASE / f"{base}:green").exists() and \
                       (SYS_LEDS_BASE / f"{base}:blue").exists():
                        return SYS_LEDS_BASE / base

        except Exception as e:
            logger.debug(f"Error finding DS4 LED for {device_path}: {e}")

        return None