from __future__ import annotations

import logging
import os
import struct
import threading
import time
import zlib
from pathlib import Path

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

    def __init__(self, led_path: Path | None = None):
        self._led_path: Path | None = None
        self._hid_device_path: Path | None = None  # Specific hidraw device
        # Old driver (hid-sony) paths
        self._red_path: Path | None = None
        self._green_path: Path | None = None
        self._blue_path: Path | None = None
        self._brightness_path: Path | None = None
        # New driver (hid-playstation) paths
        self._colors_path: Path | None = None       # inputNN:rgb:indicator/colors
        self._multi_intensity_path: Path | None = None
        self._global_path: Path | None = None

        self._max_brightness = 255
        self._current_color: tuple[int, int, int] = (0, 0, 255)
        self._enabled = True
        self._driver: str | None = None  # 'sony' | 'playstation' | None
        # Rumble state (0-255 per motor) mirrored into every output report so
        # color updates never cancel an active vibration (mirrors the kernel's
        # "always send rumble + lightbar together" compatibility rule).
        self._rumble_left = 0    # strong motor (0-65535 -> 0-255)
        self._rumble_right = 0   # weak motor
        # Transport ('usb' | 'bt') of the configured hidraw node; cached.
        self._transport: str | None = None
        # Cached hidraw fd (rumble writes arrive at a high rate).
        # _hid_lock (RLock) serializes open/write/close: the fd is touched
        # from the GUI thread (set_color), the worker (set_rumble) and the
        # DSU rumble handler thread concurrently.
        self._hid_fd = -1
        self._hid_lock = threading.RLock()

        if led_path:
            self.set_led_path(led_path)

    # ------------------------------------------------------------------
    # Driver detection
    # ------------------------------------------------------------------
    @staticmethod
    def detect_driver() -> str | None:
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
    def _find_input_device_name(device_path: str) -> str | None:
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
        with self._hid_lock:
            if self._hid_device_path != hid_path:
                self.close()
                self._transport = None
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
        # Color + rumble share the same HID output report and are written
        # from different threads (GUI set_color, worker/DSU set_rumble).
        # State update, report build and write must be one critical section
        # or a concurrent setter sees a half-updated report (stale motor or
        # stale color). _hid_lock is an RLock, so _send_hid_report re-enters.
        with self._hid_lock:
            self._current_color = (r, g, b)

            # --- Priority 1: HID output report (transport-aware) ---
            if self._send_hid_report(self._make_color_report(r, g, b)):
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

    def _send_hid_report(self, report: bytes, quiet: bool = False) -> bool:
        """Send an output report to the DS4 over hidraw. Returns True on success.

        The fd is cached so high-frequency rumble updates do not pay
        open/close on every write; a failed write invalidates the cache and
        retries once with a fresh open. The whole open/write/retry sequence
        runs under ``_hid_lock`` so concurrent callers (GUI, worker, DSU)
        cannot interleave a close between open and write.
        """
        with self._hid_lock:
            try:
                fd = self._open_hid()
                if fd < 0:
                    if not quiet:
                        logger.debug("No hidraw node available for output report")
                    return False
                try:
                    os.write(fd, report)
                except BlockingIOError:
                    # BT radio busy (EAGAIN, possible with O_NONBLOCK):
                    # short pause + retry WITHOUT invalidating the cached
                    # fd — close/reopen on every EAGAIN would churn
                    # open/close in rumble bursts.
                    time.sleep(0.002)
                    os.write(fd, report)
                if not quiet:
                    logger.info(
                        f"LED color ({self._current_color[0]},{self._current_color[1]},"
                        f"{self._current_color[2]}) via HID output report"
                    )
                return True
            except OSError as ex:
                last_ex = ex
                self._close_hid_fd()
                try:
                    fd = self._open_hid()
                    if fd >= 0:
                        try:
                            os.write(fd, report)
                        except BlockingIOError:
                            # Same EAGAIN dance as the first write: the
                            # retry must not propagate a transient BT stall
                            # to the caller (it would drop that frame's
                            # rumble in the worker loop).
                            time.sleep(0.002)
                            os.write(fd, report)
                        return True
                except OSError as retry_ex:
                    last_ex = retry_ex
                if not quiet:
                    logger.warning(f"HID output report failed: {last_ex}")
                return False

    def _open_hid(self) -> int:
        with self._hid_lock:
            if self._hid_fd >= 0:
                return self._hid_fd
            try:
                if self._hid_device_path:
                    if not self._hid_device_path.exists():
                        return -1
                    # O_NONBLOCK: a BT hidraw write can stall briefly while
                    # the radio is busy; without it the _hid_lock (shared by
                    # GUI/worker/DSU) would be held for the whole stall.
                    self._hid_fd = os.open(
                        str(self._hid_device_path), os.O_RDWR | os.O_NONBLOCK
                    )
                else:
                    self._hid_fd = device_manager.DeviceManager.get_hid_device() or -1
            except OSError as ex:
                logger.debug(f"HID open failed: {ex}")
                self._hid_fd = -1
            return self._hid_fd

    def _close_hid_fd(self):
        with self._hid_lock:
            if self._hid_fd >= 0:
                try:
                    os.close(self._hid_fd)
                except OSError:
                    pass
                self._hid_fd = -1

    def close(self):
        """Release the cached hidraw fd."""
        with self._hid_lock:
            self._close_hid_fd()

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
    # HID output reports (BT 78 bytes / USB 32 bytes)
    # ------------------------------------------------------------------
    def _make_hid_output_report(self, r: int, g: int, b: int) -> bytes:
        """
        Build the DS4 Bluetooth output report (78 bytes).

        Report layout:
          byte 0x00: report_id        = 0x11
          byte 0x01: hw_control       = 0xC4 (HID | CRC32 | 4ms poll)
          byte 0x02: audio_control    = 0x00
          byte 0x03: valid_flag0      = 0x03 (bit0=motor, bit1=LED)
          byte 0x04: valid_flag1      = 0x00
          byte 0x05: reserved         = 0x00
          byte 0x06: motor_right      = weak motor (0-255)
          byte 0x07: motor_left       = strong motor (0-255)
          byte 0x08: lightbar_red     = r
          byte 0x09: lightbar_green   = g
          byte 0x0A: lightbar_blue    = b
          byte 0x0B: lightbar_blink_on      = 0x00
          byte 0x0C: lightbar_blink_off     = 0x00
          bytes 0x0D–0x49: reserved (zero)
          bytes 0x4A–0x4D: CRC32 (seed 0xA2, over bytes 0x00–0x49)
        """
        rep = bytearray(78)
        rep[0]  = 0x11
        rep[1]  = 0x80 | 0x40 | 0x04   # hw_control
        rep[2]  = 0x00                  # audio_control
        rep[3]  = 0x01 | 0x02           # valid_flag0: LED + motor
        rep[4]  = 0x00                  # valid_flag1
        rep[5]  = 0x00                  # reserved
        rep[6]  = self._rumble_right    # motor_right (weak)
        rep[7]  = self._rumble_left     # motor_left (strong)
        rep[8] = r                     # lightbar_red
        rep[9] = g                     # lightbar_green
        rep[10] = b                    # lightbar_blue
        rep[11] = 0x00                  # blink_on
        rep[12] = 0x00                  # blink_off
        # bytes 13..73 remain zero

        # CRC32: seed 0xA2, computed over bytes 0x00..0x49
        crc = zlib.crc32(bytes([0xA2]), 0xFFFFFFFF)
        crc = ~zlib.crc32(bytes(rep[0:74]), crc) & 0xFFFFFFFF
        struct.pack_into("<I", rep, 74, crc)
        return bytes(rep)

    def _make_color_report(self, r: int, g: int, b: int) -> bytes:
        """Output report that updates LED + mirrors the current rumble state.

        USB pads get the 32-byte 0x05 report; Bluetooth (and unknown, for
        backwards compatibility) get the 78-byte 0x11 report with CRC.
        """
        if self.detect_transport() == "usb":
            return self._make_usb_output_report(r, g, b, led=True)
        return self._make_hid_output_report(r, g, b)

    def _make_usb_output_report(
        self,
        r: int | None = None,
        g: int | None = None,
        b: int | None = None,
        led: bool = False,
    ) -> bytes:
        """
        Build the DS4 USB output report (32 bytes, report id 0x05).

        Layout (matches hid-playstation's dualshock4_output_report_usb):
          byte 0: report_id = 0x05
          byte 1: valid_flag0 (bit0 = motor, bit1 = LED)
          byte 2: valid_flag1
          byte 3: reserved
          byte 4: motor_right (weak)
          byte 5: motor_left (strong)
          byte 6-8: lightbar rgb
          bytes 9-10: blink
          bytes 11-31: reserved
        """
        rep = bytearray(32)
        rep[0] = 0x05
        rep[1] = 0x01                # valid_flag0: motor
        rep[4] = self._rumble_right
        rep[5] = self._rumble_left
        if led:
            rep[1] |= 0x02           # valid_flag0: LED
            rep[6] = int(r) & 0xFF
            rep[7] = int(g) & 0xFF
            rep[8] = int(b) & 0xFF
        return bytes(rep)

    def _make_hid_rumble_report(self) -> bytes:
        """Rumble-only output report for the current transport (no LED flag,
        so an active sysfs-managed lightbar is never overridden)."""
        if self.detect_transport() == "usb":
            return self._make_usb_output_report()
        rep = bytearray(self._make_hid_output_report(*self._current_color))
        rep[3] = 0x01                # valid_flag0: motor only
        rep[8] = rep[9] = rep[10] = 0
        # Recompute CRC over the modified payload
        crc = zlib.crc32(bytes([0xA2]), 0xFFFFFFFF)
        crc = ~zlib.crc32(bytes(rep[0:74]), crc) & 0xFFFFFFFF
        struct.pack_into("<I", rep, 74, crc)
        return bytes(rep)

    # ------------------------------------------------------------------
    # Transport detection
    # ------------------------------------------------------------------
    def detect_transport(self) -> str | None:
        """Return 'usb' or 'bt' for the configured hidraw node (cached).

        Uses /sys/class/hidraw/<node>/device/uevent HID_ID: bus 0003 is
        USB, bus 0005 is Bluetooth.
        """
        if self._transport is not None:
            return self._transport
        if not self._hid_device_path:
            return None
        try:
            uevent = (
                Path(f"/sys/class/hidraw/{self._hid_device_path.name}/device/uevent")
            )
            for line in uevent.read_text().splitlines():
                if line.startswith("HID_ID="):
                    bus = line.split("=", 1)[1].split(":", 1)[0]
                    if bus == "0003":
                        self._transport = "usb"
                    elif bus == "0005":
                        self._transport = "bt"
                    break
        except OSError:
            return None
        if self._transport is None:
            logger.debug(f"Could not detect transport for {self._hid_device_path}")
        return self._transport

    # ------------------------------------------------------------------
    # Rumble (fallback backend used when the physical pad exposes no
    # force-feedback input node — drives the motors over hidraw instead)
    # ------------------------------------------------------------------
    def set_rumble(self, strong: int, weak: int) -> bool:
        """Drive the DS4 motors proportionally via a HID output report.

        ``strong``/``weak`` are 0-65535 FF_RUMBLE magnitudes; they map to
        motor_left (strong) and motor_right (weak) at 1/256 resolution,
        matching the kernel's dualshock4_play_effect(). Returns True when
        the report was written to the pad.
        """
        with self._hid_lock:
            # State + build + write in one section (see set_color): the
            # report carries both the motors and the current LED color.
            self._rumble_left = max(0, min(255, int(strong) // 256))
            self._rumble_right = max(0, min(255, int(weak) // 256))
            if self.detect_transport() is None:
                return False
            return self._send_hid_report(self._make_hid_rumble_report(), quiet=True)

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

        # Scale individual color channels proportionally. The color read is
        # inside _hid_lock like every other consumer of _current_color
        # (set_color publishes it under the same lock). Each sysfs path is
        # checked individually: partial drivers (red only, etc.) must not
        # crash on open(None).
        with self._hid_lock:
            color = self._current_color
        if color != (0, 0, 0) and (
            self._red_path or self._green_path or self._blue_path
        ):
            scale = value / self._max_brightness if self._max_brightness else 1.0
            r, g, b = color
            for path, channel in (
                (self._red_path, r), (self._green_path, g), (self._blue_path, b),
            ):
                if path:
                    self._write_sysfs(path, str(int(channel * scale)))

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_color(self) -> tuple[int, int, int]:
        # Same lock discipline as every other _current_color consumer.
        with self._hid_lock:
            return self._current_color

    def set_enabled(self, enabled: bool):
        if enabled == self._enabled:
            return
        if not enabled:
            # Write the "off" color BEFORE flipping the flag: set_color
            # bails out when disabled, so calling it afterwards (the old
            # order) never actually turned the physical LED dark.
            self.set_color(0, 0, 0)
        self._enabled = enabled

    def is_available(self) -> bool:
        """Check if at least one LED path is available."""
        return bool(
            self._red_path or self._green_path or self._blue_path
            or self._colors_path or self._global_path
        )

    def get_driver(self) -> str | None:
        """Return detected driver name: 'sony', 'playstation', or None."""
        return self._driver

    # ------------------------------------------------------------------
    # Static: find DS4 LED sysfs base path
    # ------------------------------------------------------------------
    @staticmethod
    def find_ds4_led(device_path: str) -> Path | None:
        """
        Find the LED sysfs base directory for a DS4 controller.
        """
        from pathlib import Path as P

        from ..constants import SYS_LEDS_BASE

        try:
            input_sysfs = P(f"/sys/class/input/{P(device_path).name}")
            if not input_sysfs.exists():
                return None

            # Resolve to full sysfs path
            try:
                resolved_input = input_sysfs.resolve()
            except (OSError, RuntimeError):
                return None

            # Path looks like: .../0005:054C:05C4.001D/input/input218/event19
            # LED symlinks point to: .../0005:054C:05C4.001D
            # We need to go up 3 levels from resolved_input
            hid_device = resolved_input.parent.parent.parent  # Skip /event19, /input218, /input

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
