from __future__ import annotations

import os
import struct
import logging
from typing import Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


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
        """Read a single 64-byte input report."""
        if self._fd < 0:
            return None
        
        try:
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
        """Parse button state from input report."""
        # Byte 0: report ID
        # Byte 1: buttons (lower 12 bits)
        # Bit 0: Cross (SOUTH)
        # Bit 1: Circle (EAST)
        # Bit 2: Triangle (NORTH)
        # Bit 3: Square (WEST)
        # Bit 4: L1 (TL)
        # Bit 5: R1 (TR)
        # Bit 6: L2 (TL2) - actually bit 6 is share, bit 7 is options
        # Bit 7: Options (START)
        # Bit 8: Share (SELECT)
        # Bit 9: Options (actually bit 8 is share, bit 9 is options)
        # Bit 10: L3 (THUMBL)
        # Bit 11: R3 (THUMBR)
        # Bit 12: PS (MODE)
        
        buttons_byte = report[1]
        buttons_byte2 = report[2] if len(report) > 2 else 0
        
        return {
            'SOUTH': bool(buttons_byte & 0x01),      # Cross
            'EAST': bool(buttons_byte & 0x02),        # Circle
            'NORTH': bool(buttons_byte & 0x04),       # Triangle
            'WEST': bool(buttons_byte & 0x08),        # Square
            'TL': bool(buttons_byte & 0x10),          # L1
            'TR': bool(buttons_byte & 0x20),          # R1
            'SELECT': bool(buttons_byte & 0x40),      # Share
            'START': bool(buttons_byte & 0x80),       # Options
            'THUMBL': bool(buttons_byte2 & 0x01),     # L3
            'THUMBR': bool(buttons_byte2 & 0x02),     # R3
            'PS': bool(buttons_byte2 & 0x04),         # PS
            'TOUCHPAD': bool(buttons_byte2 & 0x08),   # Touchpad
        }
    
    def parse_sticks(self, report: bytes) -> dict:
        """Parse stick positions from input report."""
        # Bytes 2-3: Left Stick X (little-endian, 0-255, center=128)
        # Bytes 4-5: Left Stick Y
        # Bytes 6-7: Right Stick X
        # Bytes 8-9: Right Stick Y
        # Bytes 10-11: L2 trigger
        # Bytes 12-13: R2 trigger
        
        if len(report) < 14:
            return {}
        
        return {
            'LX': struct.unpack('<H', report[2:4])[0],
            'LY': struct.unpack('<H', report[4:6])[0],
            'RX': struct.unpack('<H', report[6:8])[0],
            'RY': struct.unpack('<H', report[8:10])[0],
            'L2': struct.unpack('<H', report[10:12])[0],
            'R2': struct.unpack('<H', report[12:14])[0],
        }
    
    def parse_dpad(self, report: bytes) -> dict:
        """Parse D-pad state from input report."""
        # Byte 3 contains D-pad information in the upper nibble
        if len(report) < 4:
            return {}
        
        dpad_byte = report[3] >> 4  # Upper nibble
        
        # D-pad encoding (8 directions + neutral)
        dpad_map = {
            0: None,      # Neutral
            1: ('RIGHT', 'DOWN'),   # Down-Right
            2: ('DOWN', 'RIGHT'),   # Same as above (different encoding)
            3: ('DOWN',),           # Down
            4: ('LEFT', 'DOWN'),    # Down-Left
            5: ('DOWN', 'LEFT'),    # Same as above
            6: ('LEFT',),           # Left
            7: ('UP', 'LEFT'),      # Up-Left
            8: ('UP',),             # Up
            9: ('UP', 'RIGHT'),     # Up-Right
            10: ('RIGHT', 'UP'),    # Same as above
            11: ('RIGHT',),         # Right
            12: ('LEFT', 'UP'),     # Up-Left (alternative)
            13: ('UP', 'LEFT'),     # Same
            14: ('LEFT',),          # Left (alternative)
            15: ('LEFT', 'DOWN'),   # Down-Left (alternative)
        }
        
        return dpad_map.get(dpad_byte, (None,))


def find_ds4_hidraw() -> Optional[str]:
    """Find the hidraw device for a DS4/Wireless Controller."""
    import pyudev
    
    try:
        ctx = pyudev.Context()
        for dev in ctx.list_devices(subsystem='hidraw'):
            try:
                sysfs_path = dev.device_path.replace('/dev/hidraw', '/sys/class/hidraw')
                uevent_path = os.path.join(sysfs_path, 'device', 'uevent')
                if os.path.exists(uevent_path):
                    uevent = open(uevent_path).read()
                    # Match Sony vendor (054C) or Generic Wireless Controller
                    if '054C' in uevent or '054c' in uevent or 'Wireless Controller' in uevent:
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
