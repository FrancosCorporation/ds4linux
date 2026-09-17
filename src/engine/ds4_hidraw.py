from __future__ import annotations

import os
import select
import logging
from typing import Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DS4 input report layout (matches DS4Windows / hid-playstation).
#
# USB report (Report ID 0x01, 64 bytes):
#   [0]  report id (0x01)
#   [1]  left stick X   (0-255, center 128)
#   [2]  left stick Y
#   [3]  right stick X
#   [4]  right stick Y
#   [5]  buttons0: bit7=Triangle, bit6=Circle, bit5=Cross, bit4=Square,
#                  bits0-3 = D-pad (0-7 directions, 8 = neutral)
#   [6]  buttons1: bit7=R3, bit6=L3, bit5=Options, bit4=Share,
#                  bit3=R2, bit2=L2, bit1=R1, bit0=L1
#   [7]  buttons2: bit0=PS, bit1=Touchpad
#   [8]  L2 trigger (0-255)
#   [9]  R2 trigger (0-255)
#
# Bluetooth full report (Report ID 0x11, 78 bytes) is identical, except it has
# two reserved bytes after the report id, so the common fields start at [3].
# ---------------------------------------------------------------------------

DS4_REPORT_ID_USB = 0x01
DS4_REPORT_ID_BT = 0x11

# D-pad "hat switch" value -> (x, y), using the evdev convention (y = -1 == up)
DPAD_HAT_MAP = {
    0: (0, -1),    # Up
    1: (1, -1),    # Up-Right
    2: (1, 0),     # Right
    3: (1, 1),     # Down-Right
    4: (0, 1),     # Down
    5: (-1, 1),    # Down-Left
    6: (-1, 0),    # Left
    7: (-1, -1),   # Up-Left
    8: (0, 0),     # Neutral
}


def parse_ds4_report(report: bytes) -> dict:
    """Parse a raw DS4 HID input report into normalized state.

    Returns a dict with keys: lx, ly, rx, ry, l2, r2, dpad_x, dpad_y,
    buttons (dict of evdev button code -> bool) and ps/touchpad booleans.
    """
    from evdev import ecodes as e

    empty = {
        'lx': 128, 'ly': 128, 'rx': 128, 'ry': 128,
        'l2': 0, 'r2': 0,
        'dpad_x': 0, 'dpad_y': 0,
        'buttons': {}, 'ps': False, 'touchpad': False,
    }

    if not report or len(report) < 2:
        return empty

    report_id = report[0]
    if report_id == DS4_REPORT_ID_BT and len(report) >= 12:
        base = 3
    elif report_id == DS4_REPORT_ID_USB and len(report) >= 10:
        base = 1
    else:
        return empty

    b0 = report[base + 4]
    b1 = report[base + 5]
    b2 = report[base + 6]

    dpad = b0 & 0x0F
    if dpad > 8:
        dpad = 8
    dpad_x, dpad_y = DPAD_HAT_MAP[dpad]

    buttons = {
        e.BTN_WEST:   bool(b0 & 0x10),   # Square
        e.BTN_SOUTH:  bool(b0 & 0x20),   # Cross
        e.BTN_EAST:   bool(b0 & 0x40),   # Circle
        e.BTN_NORTH:  bool(b0 & 0x80),   # Triangle
        e.BTN_TL:     bool(b1 & 0x01),   # L1
        e.BTN_TR:     bool(b1 & 0x02),   # R1
        e.BTN_TL2:    bool(b1 & 0x04),   # L2
        e.BTN_TR2:    bool(b1 & 0x08),   # R2
        e.BTN_SELECT: bool(b1 & 0x10),   # Share
        e.BTN_START:  bool(b1 & 0x20),   # Options
        e.BTN_THUMBL: bool(b1 & 0x40),   # L3
        e.BTN_THUMBR: bool(b1 & 0x80),   # R3
        e.BTN_MODE:   bool(b2 & 0x01),   # PS
    }

    return {
        'lx': report[base + 0],
        'ly': report[base + 1],
        'rx': report[base + 2],
        'ry': report[base + 3],
        'l2': report[base + 7],
        'r2': report[base + 8],
        'dpad_x': dpad_x,
        'dpad_y': dpad_y,
        'buttons': buttons,
        'ps': bool(b2 & 0x01),
        'touchpad': bool(b2 & 0x02),
    }


class DS4HIDRAWReader:
    """
    Reads DS4 input reports directly from hidraw device.

    This bypasses the evdev grab issue by reading raw HID reports.
    The DS4 sends 64-byte reports on the interrupt endpoint.
    """

    # DS4 report IDs
    REPORT_ID_INPUT = 0x01
    REPORT_ID_OUTPUT = 0x11

    def __init__(self, hidraw_path: str):
        self._hidraw_path = hidraw_path
        self._fd = -1

    def open(self) -> bool:
        """Open the hidraw device."""
        try:
            self._fd = os.open(self._hidraw_path, os.O_RDWR | os.O_NONBLOCK)
            logger.info(f"DS4HIDRAWReader: Opened {self._hidraw_path}")
            return True
        except Exception as e:
            logger.error(f"DS4HIDRAWReader: Failed to open {self._hidraw_path}: {e}")
            return False

    def close(self):
        """Close the hidraw device."""
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = -1

    def is_open(self) -> bool:
        return self._fd >= 0

    def read_report(self) -> Optional[bytes]:
        """Read a single 64-byte input report using select() to wait for data."""
        if self._fd < 0:
            return None

        try:
            # Wait for data to be available
            readable, _, _ = select.select([self._fd], [], [], 0.05)
            if not readable:
                return None

            data = os.read(self._fd, 64)
            if len(data) == 64:
                return data
            elif len(data) > 0:
                # Partial report, try to read more
                remaining = 64 - len(data)
                extra = os.read(self._fd, remaining)
                return data + extra
            return None
        except BlockingIOError:
            return None
        except Exception as e:
            logger.warning(f"DS4HIDRAWReader: Read error: {e}")
            return None
    
    def parse_buttons(self, report: bytes) -> dict:
        """Parse button state (evdev code -> bool) from an input report."""
        return parse_ds4_report(report)['buttons']

    def parse_sticks(self, report: bytes) -> dict:
        """Parse stick/trigger positions from an input report."""
        parsed = parse_ds4_report(report)
        return {
            'LX': parsed['lx'],
            'LY': parsed['ly'],
            'RX': parsed['rx'],
            'RY': parsed['ry'],
            'L2': parsed['l2'],
            'R2': parsed['r2'],
        }

    def parse_dpad(self, report: bytes) -> dict:
        """Parse D-pad state (hat x/y) from an input report."""
        parsed = parse_ds4_report(report)
        return {'x': parsed['dpad_x'], 'y': parsed['dpad_y']}


def find_ds4_hidraw() -> Optional[str]:
    """Find the hidraw device for a DS4/Wireless Controller."""
    import pyudev
    
    try:
        ctx = pyudev.Context()
        for dev in ctx.list_devices(subsystem='hidraw'):
            try:
                # dev.device_path is the kernel path, prepend /sys for sysfs
                sysfs_path = '/sys' + dev.device_path
                uevent_path = os.path.join(sysfs_path, 'device', 'uevent')
                if os.path.exists(uevent_path):
                    uevent = open(uevent_path).read()
                    # Match Sony vendor (054C) or Wireless Controller
                    if '054C' in uevent or 'Wireless Controller' in uevent:
                        return dev.device_node
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"find_ds4_hidraw: {e}")
    
    return None


def is_ds4_hidraw(hidraw_path: str) -> bool:
    """Check if a hidraw device is for a DS4."""
    try:
        sysfs_path = hidraw_path.replace('/dev/hidraw', '/sys/class/hidraw')
        device_link = os.path.join(sysfs_path, 'device')
        if os.path.islink(device_link):
            target = os.readlink(device_link)
            return '054c' in target
    except Exception:
        pass
    return False
