"""Shared synthetic DS4 HID report builders for the test-suite.

Keeping the byte offsets in one place means a parser refactor only has to
touch this module (instead of every test that builds a report).
"""

from __future__ import annotations


def make_usb_report(dpad: int = 8, b0_extra: int = 0, b1: int = 0, b2: int = 0,
                    lx: int = 128, ly: int = 128, rx: int = 128, ry: int = 128,
                    l2: int = 0, r2: int = 0, size: int = 64) -> bytes:
    """USB input report (report id 0x01): common fields start at byte 1."""
    report = bytearray(size)
    report[0] = 0x01
    report[1] = lx
    report[2] = ly
    report[3] = rx
    report[4] = ry
    report[5] = (dpad & 0x0F) | b0_extra
    report[6] = b1
    report[7] = b2
    report[8] = l2
    report[9] = r2
    return bytes(report)


def make_bt_report(dpad: int = 8, b0_extra: int = 0, b1: int = 0, b2: int = 0,
                   lx: int = 128, ly: int = 128, rx: int = 128, ry: int = 128,
                   l2: int = 0, r2: int = 0, size: int = 78) -> bytes:
    """Bluetooth input report (report id 0x11): two extra bytes after the id."""
    report = bytearray(size)
    report[0] = 0x11
    report[3] = lx
    report[4] = ly
    report[5] = rx
    report[6] = ry
    report[7] = (dpad & 0x0F) | b0_extra
    report[8] = b1
    report[9] = b2
    report[10] = l2
    report[11] = r2
    return bytes(report)


def make_usb_hidraw_report(dpad: int = 8, b0_extra: int = 0, b1: int = 0,
                           b2: int = 0, lx: int = 128, ly: int = 128,
                           rx: int = 128, ry: int = 128, l2: int = 0,
                           r2: int = 0) -> bytes:
    """Alias kept for readability in worker-level tests."""
    return make_usb_report(dpad=dpad, b0_extra=b0_extra, b1=b1, b2=b2,
                           lx=lx, ly=ly, rx=rx, ry=ry, l2=l2, r2=r2)
