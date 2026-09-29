"""Tests for the new v1.4 features:

- Macro persistence in ProfileManager (JSON round-trip)
- Profile import/export (.ds4profile)
- FF upload ABI structs (uinput force-feedback handshake)
- MacroEditorDialog / OSDOverlay smoke tests
"""

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.engine.ff_upload import (  # noqa: E402
    FFEffect,
    FFEffectRumbleView,
    FFUpload,
    UInputFFErase,
    UInputFFUpload,
    build_rumble_effect,
    handle_ff_erase,
    handle_ff_upload,
)


# ---------------------------------------------------------------------------
# ProfileManager: macros + import/export
# ---------------------------------------------------------------------------
class TestMacroPersistence(unittest.TestCase):
    def setUp(self):
        import src.config.profile_manager as pm_mod
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = pm_mod.PROFILE_DIR
        self._old_config = pm_mod.CONFIG_FILE
        pm_mod.PROFILE_DIR = Path(self._tmp.name) / "profiles"
        pm_mod.CONFIG_FILE = Path(self._tmp.name) / "config.json"
        # Reload so module-level constants bind to the temp dir
        from src.config.profile_manager import ProfileManager
        self.pm = ProfileManager()

    def tearDown(self):
        import src.config.profile_manager as pm_mod
        pm_mod.PROFILE_DIR = self._old_dir
        pm_mod.CONFIG_FILE = self._old_config
        self._tmp.cleanup()

    def test_macro_roundtrip(self):
        from src.engine.input_mapper import MacroAction, ProfileConfig

        profile = ProfileConfig(name="MacroTest")
        profile.macros[0x130] = [
            MacroAction("key", 0x130, 1),
            MacroAction("wait", 0, 0, 0.05),
            MacroAction("key", 0x130, 0),
        ]
        self.assertTrue(self.pm.save_profile("MacroTest", profile))
        loaded = self.pm.load_profile("MacroTest")
        self.assertIn(0x130, loaded.macros)
        actions = loaded.macros[0x130]
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0].action_type, "key")
        self.assertEqual(actions[0].code, 0x130)
        self.assertEqual(actions[0].value, 1)
        self.assertEqual(actions[1].action_type, "wait")
        self.assertAlmostEqual(actions[1].delay, 0.05)
        self.assertEqual(actions[2].value, 0)

    def test_macro_invalid_entries_skipped(self):

        raw = {
            "name": "Broken",
            "device_type": "xbox",
            "macros": {
                "304": [  # 0x130 == 304; JSON keys are strings
                    {"action_type": "key", "code": 304, "value": 1, "delay": 0},
                    {"bogus": True},               # fills defaults, kept
                    "not-a-dict",                   # invalid: skipped
                ],
                "not-an-int": [],                   # invalid key: skipped
            },
        }
        path = self.pm.get_profile_path("Broken")
        with open(path, "w") as f:
            json.dump(raw, f)
        loaded = self.pm.load_profile("Broken")
        self.assertIn(0x130, loaded.macros)
        self.assertEqual(len(loaded.macros[0x130]), 1)


class TestProfileImportExport(unittest.TestCase):
    def setUp(self):
        import src.config.profile_manager as pm_mod
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = pm_mod.PROFILE_DIR
        self._old_config = pm_mod.CONFIG_FILE
        pm_mod.PROFILE_DIR = Path(self._tmp.name) / "profiles"
        pm_mod.CONFIG_FILE = Path(self._tmp.name) / "config.json"
        from src.config.profile_manager import ProfileManager
        self.pm = ProfileManager()

    def tearDown(self):
        import src.config.profile_manager as pm_mod
        pm_mod.PROFILE_DIR = self._old_dir
        pm_mod.CONFIG_FILE = self._old_config
        self._tmp.cleanup()

    def test_export_import_roundtrip(self):
        from src.engine.input_mapper import ProfileConfig
        from src.engine.virtual_device import VirtualDeviceType

        profile = ProfileConfig(
            name="Shared", device_type=VirtualDeviceType.PS4,
            led_color=(255, 0, 100),
        )
        self.pm.save_profile("Shared", profile)

        dest = Path(self._tmp.name) / "out.ds4profile"
        self.assertTrue(self.pm.export_profile("Shared", dest))
        data = json.loads(dest.read_text())
        self.assertTrue(data["_ds4linux_profile"])

        # Import under a different name
        imported = self.pm.import_profile(dest, "SharedCopy")
        self.assertEqual(imported, "SharedCopy")
        loaded = self.pm.load_profile("SharedCopy")
        self.assertEqual(loaded.device_type, VirtualDeviceType.PS4)
        self.assertEqual(tuple(loaded.led_color), (255, 0, 100))

    def test_import_rejects_garbage(self):
        junk = Path(self._tmp.name) / "junk.ds4profile"
        junk.write_text("not json at all")
        self.assertIsNone(self.pm.import_profile(junk))

        empty = Path(self._tmp.name) / "empty.ds4profile"
        empty.write_text(json.dumps({"foo": 1}))
        self.assertIsNone(self.pm.import_profile(empty))

    def test_export_missing_profile_fails(self):
        dest = Path(self._tmp.name) / "nope.ds4profile"
        self.assertFalse(self.pm.export_profile("DoesNotExist", dest))


# ---------------------------------------------------------------------------
# Profile import hardening (adversarial inputs)
# ---------------------------------------------------------------------------
class TestProfileImportHardening(unittest.TestCase):
    """Attacks against sanitize_profile_name / import_profile / _unique_name."""

    def setUp(self):
        import src.config.profile_manager as pm_mod
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = pm_mod.PROFILE_DIR
        self._old_config = pm_mod.CONFIG_FILE
        pm_mod.PROFILE_DIR = Path(self._tmp.name) / "profiles"
        pm_mod.CONFIG_FILE = Path(self._tmp.name) / "config.json"
        from src.config.profile_manager import ProfileManager
        self.pm = ProfileManager()

    def tearDown(self):
        import src.config.profile_manager as pm_mod
        pm_mod.PROFILE_DIR = self._old_dir
        pm_mod.CONFIG_FILE = self._old_config
        self._tmp.cleanup()

    def test_sanitize_blocks_attacks(self):
        from src.config.profile_manager import (
            MAX_PROFILE_NAME_LEN,
            sanitize_profile_name,
        )
        attacks = [
            "../../etc/x", "/etc/passwd", "..", ".", ".hidden",
            "a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b",
            "nul\x00byte", "ctrl\x01char", "\x7f",
            "x" * (MAX_PROFILE_NAME_LEN + 1),
            "", "   ", None, 123, [],
        ]
        for name in attacks:
            self.assertIsNone(sanitize_profile_name(name), repr(name))
        self.assertEqual(sanitize_profile_name("  My Profile  "), "My Profile")

    def test_import_rejects_traversal_name(self):
        from src.engine.input_mapper import ProfileConfig

        self.pm.save_profile("Legit", ProfileConfig(name="Legit"))
        dest = Path(self._tmp.name) / "evil.ds4profile"
        self.assertTrue(self.pm.export_profile("Legit", dest))
        data = json.loads(dest.read_text())
        data["name"] = "../../pwned"
        dest.write_text(json.dumps(data))
        self.assertIsNone(self.pm.import_profile(dest))
        self.assertFalse((Path(self._tmp.name) / "pwned").exists())
        self.assertFalse(Path(self._tmp.name).parent.joinpath("pwned").exists())

    def test_import_rejects_fifo_without_blocking(self):
        import signal

        fifo = Path(self._tmp.name) / "fifo.ds4profile"
        os.mkfifo(fifo)

        def timed_out(signum, frame):
            raise AssertionError("import_profile blocked on a FIFO")

        old = signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(5)
        try:
            self.assertIsNone(self.pm.import_profile(fifo))
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def test_import_rejects_oversized_file(self):
        from src.config.profile_manager import MAX_IMPORT_BYTES

        big = Path(self._tmp.name) / "big.ds4profile"
        # Content is irrelevant: the size cap fires before parsing.
        big.write_bytes(b'{"_ds4linux_profile": true, "pad": "' + b"A" * MAX_IMPORT_BYTES)
        self.assertIsNone(self.pm.import_profile(big))

    def test_import_never_overwrites_long_name(self):
        """61-64 char name + import must pick a fresh name, not overwrite."""
        from src.config.profile_manager import MAX_PROFILE_NAME_LEN
        from src.engine.input_mapper import ProfileConfig
        from src.engine.virtual_device import VirtualDeviceType

        long_name = "L" * MAX_PROFILE_NAME_LEN
        original = ProfileConfig(name=long_name, device_type=VirtualDeviceType.XBOX)
        self.assertTrue(self.pm.save_profile(long_name, original))

        dest = Path(self._tmp.name) / "conflict.ds4profile"
        self.assertTrue(self.pm.export_profile(long_name, dest))
        data = json.loads(dest.read_text())
        data["device_type"] = "ps4"
        dest.write_text(json.dumps(data))

        imported = self.pm.import_profile(dest)
        # Either a truncated unique variant or a refusal — never a fallback
        # to the existing name (which would silently overwrite it).
        if imported is not None:
            self.assertNotEqual(imported, long_name)
        reloaded = self.pm.load_profile(long_name)
        self.assertEqual(reloaded.device_type, VirtualDeviceType.XBOX)
        # _unique_name itself must never hand back a name that exists
        self.assertNotEqual(self.pm._unique_name(long_name), long_name)

    def test_import_conflicting_explicit_name_gets_unique_variant(self):
        """import_profile(new_name=...) used to skip _unique_name entirely
        and clobbered whatever profile already used that name."""
        from src.engine.input_mapper import ProfileConfig

        self.pm.save_profile("Dup", ProfileConfig(name="Dup"))
        self.pm.save_profile("Other", ProfileConfig(name="Other"))
        dest = Path(self._tmp.name) / "other.ds4profile"
        self.assertTrue(self.pm.export_profile("Other", dest))

        imported = self.pm.import_profile(dest, "Dup")
        self.assertIsNotNone(imported)
        self.assertNotEqual(imported, "Dup")
        # The pre-existing "Dup" profile is untouched.
        self.assertEqual(self.pm.load_profile("Dup").name, "Dup")

    def test_failed_save_keeps_previous_file_intact(self):
        """Atomic write: a crash mid-save must never truncate the profile."""
        from src.engine.input_mapper import ProfileConfig

        self.pm.save_profile("Stable", ProfileConfig(name="Stable"))
        path = self.pm.get_profile_path("Stable")
        before = path.read_text()

        with mock.patch(
            "src.config.profile_manager.json.dump",
            side_effect=OSError("disk full"),
        ):
            self.assertFalse(
                self.pm.save_profile("Stable", ProfileConfig(name="Changed"))
            )

        self.assertEqual(path.read_text(), before)  # not truncated
        self.assertEqual(self.pm.load_profile("Stable").name, "Stable")
        # No temp file left behind (mkstemp names are .<name>.<rand>.tmp)
        leftovers = list(path.parent.glob(f".{path.name}.*.tmp"))
        self.assertEqual(leftovers, [])


# ---------------------------------------------------------------------------
# ff_upload ABI
# ---------------------------------------------------------------------------
class TestFFUploadABI(unittest.TestCase):
    def test_struct_sizes(self):
        # Validated against /usr/include/linux/{input,uinput}.h on x86-64.
        import ctypes
        self.assertEqual(ctypes.sizeof(FFEffect), 48)
        self.assertEqual(ctypes.sizeof(UInputFFUpload), 104)
        self.assertEqual(ctypes.sizeof(UInputFFErase), 12)

    def test_rumble_view(self):
        eff = FFEffect()
        eff.type = 0x50  # FF_RUMBLE
        # Write strong=0x1234, weak=0x5678 into the union (little-endian)
        import ctypes
        raw = struct.pack("<HH", 0x1234, 0x5678) + b"\x00" * 28
        ctypes.memmove(
            ctypes.addressof(eff) + FFEffect.u.offset, raw, 32
        )
        strong, weak = FFEffectRumbleView.magnitudes(eff)
        self.assertEqual((strong, weak), (0x1234, 0x5678))

    def test_handle_upload_success(self):
        import ctypes
        eff = FFEffect(type=0x50, id=3, replay_length=500, replay_delay=10)
        ctypes.memmove(
            ctypes.addressof(eff) + FFEffect.u.offset,
            struct.pack("<HH", 1000, 2000) + b"\x00" * 28, 32,
        )

        def kernel_fills_effect(fd, request, upload):
            # Simulate the kernel: UI_BEGIN_FF_UPLOAD copies the uploaded
            # effect into the caller's struct.
            if upload.request_id == 7:
                ctypes.memmove(
                    ctypes.addressof(upload) + UInputFFUpload.effect.offset,
                    ctypes.addressof(eff), ctypes.sizeof(FFEffect),
                )
            return 0

        with mock.patch("src.engine.ff_upload._ioctl") as ioctl:
            ioctl.side_effect = kernel_fills_effect
            mags = handle_ff_upload(9, 7)
        self.assertEqual(
            mags,
            FFUpload(effect_id=3, strong=1000, weak=2000,
                     replay_length=500, replay_delay=10),
        )
        # Two ioctls: BEGIN then END
        self.assertEqual(ioctl.call_count, 2)

    def test_handle_upload_non_rumble(self):
        import ctypes
        eff = FFEffect(type=0x52)  # FF_CONSTANT

        def kernel_fills_effect(fd, request, upload):
            ctypes.memmove(
                ctypes.addressof(upload) + UInputFFUpload.effect.offset,
                ctypes.addressof(eff), ctypes.sizeof(FFEffect),
            )
            return 0

        with mock.patch("src.engine.ff_upload._ioctl") as ioctl:
            ioctl.side_effect = kernel_fills_effect
            mags = handle_ff_upload(9, 1)
        self.assertIsNone(mags)

    def test_handle_upload_ioctl_error(self):
        with mock.patch("src.engine.ff_upload._ioctl") as ioctl:
            ioctl.side_effect = OSError(22, "EINVAL")
            mags = handle_ff_upload(9, 1)
        self.assertIsNone(mags)

    def test_handle_erase(self):
        from src.engine.ff_upload import UI_BEGIN_FF_ERASE

        def kernel_fills_erase(fd, request, erase):
            # The kernel echoes back the effect id the game asked to erase.
            if request == UI_BEGIN_FF_ERASE:
                erase.effect_id = 7
            return 0

        with mock.patch("src.engine.ff_upload._ioctl") as ioctl:
            ioctl.side_effect = kernel_fills_erase
            erased_id = handle_ff_erase(9, 4)
        # Returns the erased effect id so callers can drop cached magnitudes
        self.assertEqual(erased_id, 7)
        self.assertEqual(ioctl.call_count, 2)

    def test_upload_struct_layout(self):
        # request_id at 0, retval at 4, effect at 8, old at 56 (matches ABI probe)
        self.assertEqual(UInputFFUpload.request_id.offset, 0)
        self.assertEqual(UInputFFUpload.retval.offset, 4)
        self.assertEqual(UInputFFUpload.effect.offset, 8)
        self.assertEqual(UInputFFUpload.old.offset, 56)
        self.assertEqual(FFEffect.u.offset, 16)

    def test_build_rumble_effect(self):
        from evdev import ecodes as e

        eff = build_rumble_effect(0x1234, 0x5678, replay_length=500,
                                  replay_delay=10, effect_id=-1)
        self.assertEqual(eff.type, e.FF_RUMBLE)
        self.assertEqual(eff.id, -1)
        self.assertEqual(eff.ff_replay.length, 500)
        self.assertEqual(eff.ff_replay.delay, 10)
        self.assertEqual(eff.u.ff_rumble_effect.strong_magnitude, 0x1234)
        self.assertEqual(eff.u.ff_rumble_effect.weak_magnitude, 0x5678)

    def test_build_rumble_effect_clamps(self):
        eff = build_rumble_effect(99999, -5, replay_length=999999)
        self.assertEqual(eff.u.ff_rumble_effect.strong_magnitude, 0xFFFF)
        self.assertEqual(eff.u.ff_rumble_effect.weak_magnitude, 0)
        self.assertEqual(eff.ff_replay.length, 0xFFFF)


# ---------------------------------------------------------------------------
# HID rumble fallback (LEDController)
# ---------------------------------------------------------------------------
class TestLEDControllerRumble(unittest.TestCase):
    def _make_led(self, transport="usb"):
        from src.engine.led_controller import LEDController

        led = LEDController()
        led._hid_device_path = Path("/dev/hidraw7")
        led._transport = transport
        return led

    def test_usb_rumble_report_layout(self):
        led = self._make_led("usb")
        led._rumble_left, led._rumble_right = 0xFF, 0x80
        report = led._make_usb_output_report()
        self.assertEqual(len(report), 32)
        self.assertEqual(report[0], 0x05)          # report id
        self.assertEqual(report[1] & 0x01, 0x01)   # motor flag valid
        self.assertEqual(report[1] & 0x02, 0x00)   # LED flag NOT set
        self.assertEqual(report[5], 0xFF)          # motor_left (strong)
        self.assertEqual(report[4], 0x80)          # motor_right (weak)

    def test_bt_rumble_report_layout_and_crc(self):
        import zlib

        led = self._make_led("bt")
        led._rumble_left, led._rumble_right = 0x7F, 0x3F
        report = led._make_hid_rumble_report()
        self.assertEqual(len(report), 78)
        self.assertEqual(report[0], 0x11)
        self.assertEqual(report[3], 0x01)          # motor flag only
        self.assertEqual(report[6], 0x3F)          # motor_right (weak)
        self.assertEqual(report[7], 0x7F)          # motor_left (strong)
        # Lightbar bytes must be zeroed so a sysfs-managed LED is untouched
        self.assertEqual(report[8:11], b"\x00\x00\x00")
        # CRC32 (seed 0xA2) over bytes 0..73, stored little-endian at 74
        crc = zlib.crc32(bytes([0xA2]), 0xFFFFFFFF)
        crc = ~zlib.crc32(bytes(report[0:74]), crc) & 0xFFFFFFFF
        self.assertEqual(struct.unpack_from("<I", report, 74)[0], crc)

    def test_set_rumble_writes_and_scales(self):
        led = self._make_led("usb")
        with mock.patch.object(led, "_send_hid_report", return_value=True) as send:
            self.assertTrue(led.set_rumble(0xFFFF, 0x8000))
        report = send.call_args[0][0]
        self.assertEqual(report[5], 255)   # strong / 256
        self.assertEqual(report[4], 128)   # weak / 256
        self.assertTrue(send.call_args.kwargs.get("quiet"))

    def test_set_rumble_requires_transport(self):
        led = self._make_led()
        led._transport = None
        led._hid_device_path = None
        with mock.patch.object(led, "_send_hid_report") as send:
            self.assertFalse(led.set_rumble(0xFFFF, 0xFFFF))
        send.assert_not_called()

    def test_detect_transport_sysfs(self):
        from src.engine.led_controller import LEDController

        led = LEDController()
        led._hid_device_path = Path("/dev/hidraw7")
        uevent = "DRIVER=hid-playstation\nHID_ID=0005:0000054C:000009CC\nHID_NAME=Wireless Controller\n"
        with mock.patch.object(Path, "read_text", return_value=uevent):
            self.assertEqual(led.detect_transport(), "bt")
        # Cached on the second call
        with mock.patch.object(Path, "read_text") as read:
            self.assertEqual(led.detect_transport(), "bt")
        read.assert_not_called()

    def test_color_report_keeps_active_rumble(self):
        led = self._make_led("usb")
        led._rumble_left, led._rumble_right = 42, 17
        report = led._make_color_report(255, 0, 0)
        self.assertEqual(report[1] & 0x03, 0x03)  # motor + LED both valid
        self.assertEqual(report[5], 42)
        self.assertEqual(report[4], 17)
        self.assertEqual(report[6:9], b"\xff\x00\x00")

    def test_setters_publish_state_inside_hid_lock(self):
        """Color and motors feed the same HID output report and are written
        from different threads (GUI set_color, worker/DSU set_rumble): the
        state update + report build + write must be one critical section,
        otherwise a setter can read a half-updated state."""
        led = self._make_led("usb")
        seen = {}

        def capture(report, quiet=False):
            seen["owned"] = led._hid_lock._is_owned()  # inside the section
            seen["color"] = led._current_color
            seen["rumble"] = (led._rumble_left, led._rumble_right)
            return True

        with mock.patch.object(led, "_send_hid_report", side_effect=capture):
            self.assertTrue(led.set_rumble(0xFFFF, 0x8000))
            self.assertEqual(seen["owned"], True)
            self.assertEqual(seen["rumble"], (255, 128))  # already updated

            led.set_color(10, 20, 30)
            self.assertEqual(seen["owned"], True)
            self.assertEqual(seen["color"], (10, 20, 30))  # already updated

    def test_disable_writes_off_color(self):
        """set_enabled(False) must actually turn the LED dark: set_color
        bails out when disabled, so the off-write must happen BEFORE the
        flag flips (the old order never wrote it)."""
        led = self._make_led("usb")
        sent = []
        with mock.patch.object(
            led, "_send_hid_report", side_effect=lambda r, quiet=False: sent.append(r) or True
        ):
            led.set_enabled(False)
        self.assertEqual(sent[-1], led._make_color_report(0, 0, 0))
        self.assertFalse(led._enabled)

    def test_disable_is_idempotent(self):
        led = self._make_led("usb")
        sent = []
        with mock.patch.object(
            led, "_send_hid_report", side_effect=lambda r, quiet=False: sent.append(r) or True
        ):
            led.set_enabled(False)
            led.set_enabled(False)  # second call: no extra report
        self.assertEqual(len(sent), 1)

    def test_brightness_with_partial_sysfs_paths(self):
        """red-only drivers must not crash on open(None) (green/blue None)."""
        led = self._make_led("usb")
        led._colors_path = None
        led._red_path = Path("/tmp/fake-red")
        led._green_path = None
        led._blue_path = None
        led._current_color = (255, 0, 100)
        written = []
        with mock.patch.object(
            led, "_write_sysfs",
            side_effect=lambda p, v: written.append((p, v)) or True,
        ):
            led.set_brightness(128)  # must not raise
        self.assertEqual(len(written), 1)
        path, val = written[0]
        self.assertEqual(path, Path("/tmp/fake-red"))
        self.assertEqual(val, str(int(255 * 128 / led._max_brightness)))


# ---------------------------------------------------------------------------
# Worker rumble path (EV_FF play events -> physical backends)
# ---------------------------------------------------------------------------
class TestWorkerRumble(unittest.TestCase):
    def setUp(self):
        from src.engine.worker_thread import WorkerThread

        self.worker = WorkerThread()

    def test_play_event_uses_uploaded_magnitudes(self):
        from src.engine.ff_upload import FFUpload

        self.worker._rumble_effects[3] = FFUpload(
            effect_id=3, strong=0x1234, weak=0x5678,
            replay_length=250, replay_delay=0,
        )
        with mock.patch.object(self.worker, "_play_rumble") as play:
            self.worker._on_play_event(3, 1)
        play.assert_called_once_with(0x1234, 0x5678, 250, 1)

    def test_play_event_stop_count(self):
        with mock.patch.object(self.worker, "_stop_rumble") as stop:
            self.worker._on_play_event(3, 0)
        stop.assert_called_once()

    def test_play_event_silent_effect_stops(self):
        from src.engine.ff_upload import FFUpload

        self.worker._rumble_effects[1] = FFUpload(
            effect_id=1, strong=0, weak=0, replay_length=0, replay_delay=0,
        )
        with mock.patch.object(self.worker, "_stop_rumble") as stop, \
                mock.patch.object(self.worker, "_play_rumble") as play:
            self.worker._on_play_event(1, 1)
        stop.assert_called_once()
        play.assert_not_called()

    def test_play_event_unknown_effect_full_power(self):
        with mock.patch.object(self.worker, "_play_rumble") as play:
            self.worker._on_play_event(9, 1)
        play.assert_called_once_with(0xFFFF, 0xFFFF, 0, 1)

    def test_play_rumble_hid_fallback(self):
        led = mock.Mock()
        led.set_rumble.return_value = True
        self.worker._led_controller = led
        self.worker._phys_ff_ok = False
        self.worker._device = None
        self.worker._play_rumble(0x1234, 0x5678, 0, 1)
        led.set_rumble.assert_called_once_with(0x1234, 0x5678)
        self.assertTrue(self.worker._rumble_active)

    def test_stop_rumble_resets_backends(self):
        led = mock.Mock()
        self.worker._led_controller = led
        self.worker._rumble_active = True
        self.worker._stop_rumble()
        self.assertFalse(self.worker._rumble_active)
        led.set_rumble.assert_called_once_with(0, 0)
        # Idempotent: a second stop does nothing
        self.worker._stop_rumble()
        led.set_rumble.assert_called_once()

    def test_rumble_deadline_bounded(self):
        import time as _time

        self.worker._phys_ff_ok = False
        self.worker._device = None
        self.worker._led_controller = mock.Mock()
        self.worker._led_controller.set_rumble.return_value = True
        before = _time.monotonic()
        self.worker._play_rumble(0xFFFF, 0xFFFF, length_ms=0, count=1)
        self.assertGreaterEqual(
            self.worker._rumble_deadline, before + self.worker.RUMBLE_STALE_S - 0.5
        )


# ---------------------------------------------------------------------------
# FF handshake path (regression: vdev.uinput AttributeError killed the
# worker on the first EVIOCSFF a game ever sent)
# ---------------------------------------------------------------------------
class TestFFHandshakePath(unittest.TestCase):
    def setUp(self):
        from src.engine.worker_thread import WorkerThread

        self.worker = WorkerThread()

    def test_virtual_device_exposes_uinput_property(self):
        from src.engine.virtual_device import VirtualDevice, VirtualDeviceType

        vdev = VirtualDevice(VirtualDeviceType.XBOX, slot_id=0)
        # The worker's handshake loop reads vdev.uinput — the property must
        # exist even while the device is inactive (was AttributeError).
        self.assertIsNone(vdev.uinput)
        self.assertFalse(vdev.is_active())

    def _fake_vdev(self, events):
        vdev = mock.Mock()
        vdev.uinput_fd = 77
        uinput = mock.Mock()
        uinput.read.return_value = iter(events)
        vdev.uinput = uinput
        return vdev

    def test_upload_and_erase_events_handled(self):
        from src.engine.ff_upload import (
            EV_UINPUT,
            UI_FF_ERASE,
            UI_FF_UPLOAD,
            FFUpload,
        )

        upload_ev = mock.Mock(type=EV_UINPUT, code=UI_FF_UPLOAD, value=0x1000)
        erase_ev = mock.Mock(type=EV_UINPUT, code=UI_FF_ERASE, value=5)
        vdev = self._fake_vdev([upload_ev, erase_ev])

        captured = FFUpload(
            effect_id=9, strong=0x1111, weak=0x2222,
            replay_length=100, replay_delay=0,
        )
        stale = FFUpload(
            effect_id=5, strong=1, weak=1, replay_length=0, replay_delay=0,
        )
        self.worker._rumble_effects[5] = stale
        self.worker._playing_virt_id = 5

        with mock.patch(
            "src.engine.worker_thread.handle_ff_upload", return_value=captured
        ) as up, mock.patch(
            "src.engine.worker_thread.handle_ff_erase", return_value=5
        ) as er, mock.patch.object(self.worker, "_stop_rumble") as stop:
            self.worker._handle_uinput_events(vdev)

        up.assert_called_once_with(77, upload_ev.value)
        er.assert_called_once_with(77, erase_ev.value)
        self.assertIs(self.worker._rumble_effects.get(9), captured)
        self.assertNotIn(5, self.worker._rumble_effects)  # erased
        stop.assert_called_once()  # playing effect was the erased one

    def test_missing_uinput_attribute_is_noop(self):
        vdev = mock.Mock()
        vdev.uinput = None
        # Must return without touching anything (device raced out).
        self.worker._handle_uinput_events(vdev)


# ---------------------------------------------------------------------------
# Worker start-up release sweep + DeviceMonitor teardown
# ---------------------------------------------------------------------------
class TestReleaseSweep(unittest.TestCase):
    """A release that happens while the worker is stopped must not be
    swallowed by stale dedup state after restart (stuck virtual button)."""

    def _mapper(self):
        from src.constants import DS4_TO_XBOX_BTN_MAP
        from src.engine.input_mapper import InputMapper, ProfileConfig

        profile = ProfileConfig(
            button_maps={int(k): int(v) for k, v in DS4_TO_XBOX_BTN_MAP.items()},
        )
        return InputMapper(profile)

    def test_pressed_state_is_released_and_cache_cleared(self):
        from evdev import ecodes as e

        from src.engine.worker_thread import WorkerThread

        mapper = self._mapper()
        # Previous run recorded a press (0x130 = BTN_SOUTH -> 304 = BTN_A)
        result = mapper.map_button(0x130, 1)
        self.assertIsNotNone(result)
        self.assertTrue(mapper.button_state.get(0x130))

        worker = WorkerThread()
        events, syncs = [], []
        worker.release_stuck_buttons(
            mapper,
            lambda t, c, v: events.append((t, c, v)),
            lambda: syncs.append(1),
        )
        self.assertEqual(events, [(e.EV_KEY, result[0], 0)])
        self.assertEqual(syncs, [1])
        self.assertEqual(mapper.button_state, {})  # clean slate

    def test_nothing_written_when_nothing_pressed(self):
        from src.engine.worker_thread import WorkerThread

        mapper = self._mapper()
        worker = WorkerThread()
        events, syncs = [], []
        worker.release_stuck_buttons(
            mapper,
            lambda t, c, v: events.append((t, c, v)),
            lambda: syncs.append(1),
        )
        self.assertEqual(events, [])
        self.assertEqual(syncs, [])

    def test_profile_swap_releases_code_actually_written(self):
        """Profile A maps Cross->BTN_A, B maps Cross->BTN_B (same type, vdev
        survives). The sweep must release BTN_A (what was written), not
        BTN_B (what the new profile would map)."""
        from evdev import ecodes

        from src.constants import DS4_TO_XBOX_BTN_MAP
        from src.engine.input_mapper import InputMapper, ProfileConfig
        from src.engine.worker_thread import WorkerThread

        mapper = InputMapper(ProfileConfig(
            button_maps={int(k): int(v) for k, v in DS4_TO_XBOX_BTN_MAP.items()},
        ))
        cross = 0x130
        old_code = mapper.profile.button_maps[cross]
        mapper.map_button(cross, 1)  # press under profile A

        # Profile B: same type, Cross remapped to a different virtual code
        swapped = dict(mapper.profile.button_maps)
        swapped[cross] = 0x131  # BTN_B
        mapper.set_profile(ProfileConfig(button_maps=swapped))
        # set_profile resets state — simulate the surviving stale state by
        # re-recording the press without a release (as the old run left it):
        mapper.button_state[cross] = True
        mapper.written_virtual[cross] = old_code

        worker = WorkerThread()
        events = []
        worker.release_stuck_buttons(
            mapper,
            lambda t, c, v: events.append((t, c, v)),
            lambda: None,
        )
        self.assertEqual(events, [(ecodes.EV_KEY, old_code, 0)])
        self.assertNotIn(0x131, [c for (_, c, _) in events])


class TestDeviceMonitorStop(unittest.TestCase):
    """QTimer.stop() must never be called cross-thread (stop() runs on the
    GUI thread while the timers live in the monitor thread)."""

    def test_stop_disables_both_timers(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from src.engine.device_monitor import DeviceMonitor

        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)

        mon = DeviceMonitor()
        mon._timer = QTimer()
        mon._timer.start(50)
        mon._rescan_timer = QTimer()
        mon._rescan_timer.start(50)
        self.assertTrue(mon._timer.isActive())
        self.assertTrue(mon._rescan_timer.isActive())

        mon.stop()  # no thread started: must not raise, must stop timers
        self.assertFalse(mon._timer.isActive())
        self.assertFalse(mon._rescan_timer.isActive())


# ---------------------------------------------------------------------------
# GUI smoke tests
# ---------------------------------------------------------------------------
class TestGuiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_macro_editor_dialog(self):
        from src.engine.input_mapper import MacroAction
        from src.gui.macro_dialog import MacroEditorDialog

        dlg = MacroEditorDialog(0x130, None, None, None)
        dlg._append_step(MacroAction("key", 0x130, 1))
        dlg._append_step(MacroAction("wait", 0, 0, 0.05))
        dlg._append_step(MacroAction("key", 0x130, 0))
        actions = dlg.get_actions()
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0].action_type, "key")
        dlg._clear()
        self.assertEqual(dlg.get_actions(), [])
        dlg.deleteLater()

    def test_macro_editor_disconnects_on_done(self):
        """A closed editor must stop listening to the long-lived worker."""
        from PySide6.QtCore import QObject, Signal

        from src.gui.macro_dialog import MacroEditorDialog

        class FakeWorker(QObject):
            raw_event = Signal(int, int, int)

        worker = FakeWorker()
        dlg = MacroEditorDialog(0x130, None, worker, None)
        received = []
        # Keep our own probe alongside the dialog's connection
        worker.raw_event.connect(lambda t, c, v: received.append((t, c, v)))
        dlg._toggle_recording(True)
        worker.raw_event.emit(1, 0x130, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(len(dlg.get_actions()), 1, "recording captures presses")

        dlg.done(0)  # what accept()/reject()/Esc all go through
        worker.raw_event.emit(1, 0x131, 1)
        self.assertEqual(len(received), 2, "probe connection must survive")
        self.assertEqual(len(dlg.get_actions()), 1, "dialog must be disconnected")
        self.assertIsNone(dlg._worker)
        dlg.deleteLater()

    def test_osd_overlay(self):
        from PySide6.QtCore import QTimer

        from src.gui.osd_overlay import OSDOverlay

        osd = OSDOverlay()
        osd.notify("hello", level="info")
        # Process events so the queued signal delivers
        QTimer.singleShot(0, self.app.quit)
        self.app.exec()
        # Offscreen platforms may refuse show(); the row must be queued.
        self.assertEqual(len(osd._rows), 1)
        self.assertEqual(osd._rows[0][0].label.text(), "hello")
        osd._dismiss(osd._rows[0][0])
        self.assertEqual(len(osd._rows), 0)
        osd.deleteLater()

    def test_mapping_tab_macro_methods(self):
        from src.engine.input_mapper import MacroAction
        from src.gui.mapping_tab import MappingTabWidget

        tab = MappingTabWidget()
        tab.set_macros({0x131: [MacroAction("key", 0x131, 1)]})
        macros = tab.get_macros()
        self.assertIn(0x131, macros)
        self.assertEqual(macros[0x131][0].code, 0x131)


if __name__ == "__main__":
    unittest.main()
