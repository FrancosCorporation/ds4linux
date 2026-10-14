"""ctypes bindings for the uinput force-feedback upload protocol.

Games that use rumble under Proton/Wine upload an ``FF_RUMBLE`` effect to the
virtual uinput device and then play it with EV_FF events.  The default kernel
uinput handler silently accepts the upload but discards the magnitudes, so a
plain EV_FF forward can only do an on/off rumble.

To capture the actual magnitudes we implement the uinput FF upload handshake
(Documentation/input/uinput.rst):

  1. Wait for an event with ``type == EV_UINPUT`` and ``code == UI_FF_UPLOAD``.
  2. Allocate a ``uinput_ff_upload`` struct, fill in ``request_id`` with the
     event value, and issue ``UI_BEGIN_FF_UPLOAD`` — the kernel fills in
     ``effect`` (with the game's real magnitudes) and ``old``.
  3. Acknowledge with ``UI_END_FF_UPLOAD``, keeping ``retval`` at 0 so the
     game believes the upload succeeded.

The same dance exists for effect erase (``UI_FF_ERASE``), which we answer
with success so games can free effect slots.

Layouts were probed against ``/usr/include/linux/{input,uinput}.h``
(sizeof(ff_effect)==48, sizeof(uinput_ff_upload)==104) and match
UINPUT_VERSION >= 5. The ioctl numbers assume the asm-generic ``_IOWR``
encoding (x86-64, ARM64 and every mainstream Linux architecture).
"""
from __future__ import annotations

import ctypes
import logging
import struct
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (linux/uinput.h, linux/input.h)
# ---------------------------------------------------------------------------
UI_FF_UPLOAD = 1
UI_FF_ERASE = 2
EV_UINPUT = 0x0101          # 257
FF_RUMBLE = 0x50
EF_RUMBLE = 0x50

# _IOWR/_IO computed values for x86-64/ARM64 (dir=2 read+write for _IOWR)
UINPUT_IOCTL_BASE = ord('U')  # 0x55
UI_BEGIN_FF_UPLOAD = 0xC06855C8
UI_END_FF_UPLOAD = 0x406855C9
UI_BEGIN_FF_ERASE = 0xC00C55CA
UI_END_FF_ERASE = 0x400C55CB


# ---------------------------------------------------------------------------
# Struct definitions
# ---------------------------------------------------------------------------
class FFRumbleEffect(ctypes.Structure):
    _fields_ = [
        ("strong_magnitude", ctypes.c_uint16),
        ("weak_magnitude", ctypes.c_uint16),
    ]


class FFEffect(ctypes.Structure):
    """struct ff_effect — must stay 48 bytes on LP64."""

    _fields_ = [
        ("type", ctypes.c_uint16),          # 0
        ("id", ctypes.c_int16),             # 2
        ("direction", ctypes.c_uint16),     # 4
        ("trigger_button", ctypes.c_uint16),   # 6  ff_trigger.button
        ("trigger_interval", ctypes.c_uint16), # 8  ff_trigger.interval
        ("replay_length", ctypes.c_uint16),    # 10 ff_replay.length
        ("replay_delay", ctypes.c_uint16),     # 12 ff_replay.delay
        # union (offset 16, 32 bytes) — we only care about rumble, but keep
        # the full size so ioctl buffers round-trip safely.
        ("u", ctypes.c_uint32 * 8),
    ]


class FFEffectRumbleView:
    """Read strong/weak magnitudes out of the union of an FFEffect."""

    @staticmethod
    def magnitudes(effect: FFEffect) -> tuple[int, int]:
        raw = struct.pack("<8I", *effect.u)
        strong, weak = struct.unpack_from("<HH", raw, 0)
        return strong, weak


class UInputFFUpload(ctypes.Structure):
    """struct uinput_ff_upload — 104 bytes on LP64."""

    _fields_ = [
        ("request_id", ctypes.c_uint32),    # 0
        ("retval", ctypes.c_int32),         # 4
        ("effect", FFEffect),               # 8
        ("old", FFEffect),                  # 56
    ]


class UInputFFErase(ctypes.Structure):
    """struct uinput_ff_erase — 12 bytes."""

    _fields_ = [
        ("request_id", ctypes.c_uint32),
        ("retval", ctypes.c_int32),
        ("effect_id", ctypes.c_uint32),
    ]


# ---------------------------------------------------------------------------
# Handshake helpers
# ---------------------------------------------------------------------------
class FFUpload(NamedTuple):
    """Result of one UI_FF_UPLOAD round-trip."""

    effect_id: int       # kernel-assigned id of the uploaded effect
    strong: int          # 0-65535 strong (heavy) motor magnitude
    weak: int            # 0-65535 weak (light) motor magnitude
    replay_length: int   # ms the effect should run per play count (0 = until stopped)
    replay_delay: int    # ms delay before playback starts


def handle_ff_upload(uinput_fd: int, request_id: int) -> FFUpload | None:
    """Complete one UI_FF_UPLOAD round-trip.

    Returns the uploaded effect (id, magnitudes and replay timing), or None
    on failure (unknown ioctl ABI, EINVAL, non-rumble effect, ...). The
    kernel's ``old`` struct is echoed back unchanged and ``retval`` stays
    0 = success, so the game proceeds normally.
    """
    upload = UInputFFUpload()
    upload.request_id = request_id
    upload.retval = 0

    try:
        fcntl_result = _ioctl(uinput_fd, UI_BEGIN_FF_UPLOAD, upload)
    except OSError as ex:
        logger.debug("FF upload: UI_BEGIN_FF_UPLOAD failed: %s", ex)
        return None
    if fcntl_result != 0:
        return None

    result = None
    if upload.effect.type == FF_RUMBLE:
        strong, weak = FFEffectRumbleView.magnitudes(upload.effect)
        result = FFUpload(
            effect_id=int(upload.effect.id),
            strong=strong,
            weak=weak,
            replay_length=int(upload.effect.replay_length),
            replay_delay=int(upload.effect.replay_delay),
        )
        logger.debug("FF upload: id=%d strong=%d weak=%d len=%d",
                     result.effect_id, strong, weak, result.replay_length)
    else:
        # Non-rumble effects are answered with retval=0 (handshake completes
        # normally) and simply not forwarded: the kernel drops them, the
        # game believes the effect was accepted. Intentional, not an ack bug.
        logger.debug("FF upload: non-rumble effect type 0x%02x", upload.effect.type)

    # Acknowledge — retval 0 tells the kernel (and the game) all went well.
    try:
        _ioctl(uinput_fd, UI_END_FF_UPLOAD, upload)
    except OSError as ex:
        logger.debug("FF upload: UI_END_FF_UPLOAD failed: %s", ex)

    return result


def handle_ff_erase(uinput_fd: int, request_id: int) -> int | None:
    """Complete one UI_FF_ERASE round-trip (always answers success).

    Returns the erased effect id so callers can drop cached magnitudes, or
    None on ioctl failure.
    """
    erase = UInputFFErase()
    erase.request_id = request_id
    erase.retval = 0
    try:
        if _ioctl(uinput_fd, UI_BEGIN_FF_ERASE, erase) != 0:
            return None
        effect_id = int(erase.effect_id)
        _ioctl(uinput_fd, UI_END_FF_ERASE, erase)
        return effect_id
    except OSError as ex:
        logger.debug("FF erase: ioctl failed: %s", ex)
        return None


def build_rumble_effect(strong: int, weak: int, replay_length: int = 0,
                        replay_delay: int = 0, effect_id: int = -1):
    """Build an ``evdev.ff.Effect`` for FF_RUMBLE (upload via EVIOCSFF).

    ``replay_length`` 0 means "play until stopped" (ff-memless semantics).
    """
    from evdev import ecodes as e
    from evdev import ff as evdev_ff

    return evdev_ff.Effect(
        type=e.FF_RUMBLE,
        id=effect_id,
        direction=0,
        ff_trigger=evdev_ff.Trigger(button=0, interval=0),
        ff_replay=evdev_ff.Replay(length=max(0, min(0xFFFF, int(replay_length))),
                                  delay=max(0, min(0xFFFF, int(replay_delay)))),
        u=evdev_ff.EffectType(
            ff_rumble_effect=evdev_ff.Rumble(
                strong_magnitude=max(0, min(0xFFFF, int(strong))),
                weak_magnitude=max(0, min(0xFFFF, int(weak))),
            )
        ),
    )


# Small indirection so tests can monkeypatch the raw ioctl.
def _ioctl(fd: int, request: int, arg):
    import fcntl
    return fcntl.ioctl(fd, request, arg)
