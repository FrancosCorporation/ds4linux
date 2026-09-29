import json
import logging
import os
import re
import stat
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..constants import CONFIG_FILE, PROFILE_DIR
from ..engine.input_mapper import AxisConfig, MacroAction, ProfileConfig, TriggerConfig
from ..engine.virtual_device import VirtualDeviceType

logger = logging.getLogger(__name__)

# Safety limits for imported (untrusted) profile files.
MAX_IMPORT_BYTES = 1 * 1024 * 1024  # 1 MiB
MAX_MACRO_ACTIONS = 100
MAX_MACRO_DELAY_S = 10.0
MAX_POLL_RATE_MS = 1000
MIN_POLL_RATE_MS = 1
MAX_PROFILE_NAME_LEN = 64

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_FORBIDDEN_CHARS = set('/\\:*?"<>|')


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: unique temp file in the same dir, then ``os.replace``.

    Opening the target with ``"w"`` truncates it *before* json.dump runs,
    so a crash mid-write (power loss, kill -9) used to leave a corrupted
    profile/config behind. The replace is atomic on POSIX, so readers only
    ever see the old or the new file, never a partial one. The temp name is
    unique per call (mkstemp) so two concurrent writers on the same target
    cannot truncate each other's temp file.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp creates 0600; profiles/exports are host-readable artifacts
        # (0644, like a plain open("w") would produce under a normal umask).
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        # Never leave a half-written temp file behind on failure.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def sanitize_profile_name(name) -> str | None:
    """Return a filesystem-safe profile name, or None when unacceptable.

    Blocks path traversal (``../``, absolute paths, separators, control chars)
    so an imported ``.ds4profile`` can never write outside ``PROFILE_DIR``.
    """
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or name in (".", ".."):
        return None
    if name.startswith(".") or len(name) > MAX_PROFILE_NAME_LEN:
        return None
    if _CTRL_RE.search(name):
        return None
    if any(c in name for c in _FORBIDDEN_CHARS):
        return None
    return name


class ProfileManager(QObject):
    """Manages profile loading, saving, and listing."""

    profiles_changed = Signal()

    def __init__(self):
        super().__init__()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._current_profile_name: str | None = None
        self._load_last_used()
        self.seed_default_profiles()

    def _load_last_used(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                    self._current_profile_name = data.get("last_profile")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")

    def _save_last_used(self):
        try:
            data = {"last_profile": self._current_profile_name}
            _atomic_write_json(CONFIG_FILE, data)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_profile_path(self, name: str) -> Path:
        # Defense in depth: never build a path from an unsafe name, even for
        # internally-supplied callers.
        safe = sanitize_profile_name(name)
        if safe is None:
            raise ValueError(f"unsafe profile name: {name!r}")
        return PROFILE_DIR / f"{safe}.json"

    def list_profiles(self) -> list[str]:
        profiles = []
        for f in PROFILE_DIR.glob("*.json"):
            profiles.append(f.stem)
        if "default" not in [p.lower() for p in profiles]:
            profiles.insert(0, "Default")
        return sorted(profiles, key=str.lower)

    def load_profile(self, name: str) -> ProfileConfig:
        safe = sanitize_profile_name(name)
        if safe is None:
            logger.warning("load_profile: unsafe name %r — using fallback", name)
            return self.load_profile("Xbox 360") if name != "Xbox 360" \
                else self._create_xbox360_profile("Xbox 360")
        path = self.get_profile_path(safe)
        if not path.exists():
            # Fallback to Xbox 360 if requested profile doesn't exist
            if safe.lower() in ("xbox 360", "default"):
                return self._create_xbox360_profile("Xbox 360")
            return self.load_profile("Xbox 360")

        try:
            with open(path) as f:
                data = json.load(f)
            profile = self._dict_to_profile(data)
            self._current_profile_name = safe
            self._save_last_used()
            logger.info(f"Loaded profile: {safe}")
            return profile
        except Exception as e:
            logger.error(f"Failed to load profile {safe}: {e}")
            return self._create_default_profile()

    def save_profile(self, name: str, profile: ProfileConfig) -> bool:
        safe = sanitize_profile_name(name)
        if safe is None:
            logger.error(f"save_profile: unsafe name {name!r}")
            return False
        path = self.get_profile_path(safe)
        try:
            data = self._profile_to_dict(profile)
            _atomic_write_json(path, data)
            self._current_profile_name = safe
            self._save_last_used()
            logger.info(f"Saved profile: {safe}")
            self.profiles_changed.emit()
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {safe}: {e}")
            return False

    def create_profile(self, name: str) -> ProfileConfig:
        """Create a new profile with default settings and return it."""
        safe = sanitize_profile_name(name) or "Profile"
        profile = self._create_default_profile(safe)
        self.save_profile(safe, profile)
        return profile

    def delete_profile(self, name: str) -> bool:
        if str(name).lower() == "default":
            return False
        safe = sanitize_profile_name(name)
        if safe is None:
            logger.error(f"delete_profile: unsafe name {name!r}")
            return False
        path = self.get_profile_path(safe)
        try:
            if path.exists():
                path.unlink()
                if self._current_profile_name == safe:
                    self._current_profile_name = None
                    self._save_last_used()
                logger.info(f"Deleted profile: {safe}")
                self.profiles_changed.emit()
                return True
        except Exception as e:
            logger.error(f"Failed to delete profile {safe}: {e}")
        return False

    def get_current_profile_name(self) -> str | None:
        return self._current_profile_name

    # ------------------------------------------------------------------
    # Import / export (.ds4profile JSON sharing)
    # ------------------------------------------------------------------
    def export_profile(self, name: str, dest_path) -> bool:
        """Export a profile as a portable ``.ds4profile`` file.

        The file is a superset of the stored JSON, plus a magic marker and
        schema version so future imports can migrate safely.
        """
        safe = sanitize_profile_name(name)
        if safe is None:
            logger.warning(f"export_profile: unsafe name {name!r}")
            return False
        path = self.get_profile_path(safe)
        if not path.exists():
            logger.warning(f"export_profile: '{safe}' not found")
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            data["_ds4linux_profile"] = True
            data["_schema"] = 1
            dest_path = Path(dest_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(dest_path, data)
            logger.info(f"Exported profile '{safe}' -> {dest_path}")
            return True
        except Exception as e:
            logger.error(f"export_profile failed: {e}")
            return False

    def import_profile(self, src_path, new_name: str | None = None) -> str | None:
        """Import a ``.ds4profile`` file and register it under ``new_name``.

        Returns the profile name on success, None on failure. The file is
        untrusted input: it is size-capped, must carry the export marker, its
        name is sanitized against path traversal and every field is validated
        by ``_dict_to_profile`` before anything is written to disk. The active
        profile selection is left untouched.
        """
        try:
            src_path = Path(src_path)
            # Open with O_NONBLOCK first and fstat the fd: a FIFO/device
            # swapped in after stat() would otherwise block forever or
            # bypass the size cap (st_size == 0 for FIFOs and char devs).
            fd = os.open(src_path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        except OSError as e:
            logger.error(f"import_profile: cannot open {src_path}: {e}")
            return None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                logger.error("import_profile: not a regular file: %s", src_path)
                return None
            if st.st_size > MAX_IMPORT_BYTES:
                logger.error("import_profile: file too large (> %d bytes)", MAX_IMPORT_BYTES)
                return None
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                fd = -1  # ownership transferred to f
                raw = f.read(MAX_IMPORT_BYTES + 1)
            if len(raw) > MAX_IMPORT_BYTES:
                logger.error("import_profile: file too large (> %d bytes)", MAX_IMPORT_BYTES)
                return None
            data = json.loads(raw)
        except Exception as e:
            logger.error(f"import_profile: cannot read {src_path}: {e}")
            return None
        finally:
            if fd >= 0:
                os.close(fd)

        if not isinstance(data, dict) or data.get("_ds4linux_profile") is not True:
            logger.error("import_profile: not a ds4linux profile file (missing marker)")
            return None

        # Name handling: untrusted file name is strictly sanitized; a name
        # explicitly chosen by the caller is sanitized too (same rules).
        raw_name = new_name if new_name is not None else data.get("name")
        name = sanitize_profile_name(raw_name)
        if name is None:
            logger.error("import_profile: unacceptable profile name %r", raw_name)
            return None
        # Never silently overwrite an existing profile, whichever source the
        # name came from (the file, or an explicit caller argument: the old
        # code skipped _unique_name for new_name and clobbered whatever
        # profile already used that name).
        unique = self._unique_name(name)
        if unique is None:
            logger.error(
                "import_profile: no free name for %r (refusing to overwrite)",
                raw_name,
            )
            return None
        name = unique
        data["name"] = name

        try:
            profile = self._dict_to_profile(data)  # validates + clamps fields
        except Exception as e:
            logger.error(f"import_profile: invalid profile data: {e}")
            return None

        if not self._write_profile(name, profile):
            return None
        logger.info(f"Imported profile '{name}' from {src_path}")
        return name

    def _unique_name(self, name: str) -> str | None:
        """Append `` (2)``, `` (3)``... until the profile name is free.

        The suffix is applied on a truncated base so the candidate always
        fits ``MAX_PROFILE_NAME_LEN`` (a 61-64 char name would otherwise
        produce candidates that every `` (i)`` suffix pushes over the
        limit, silently falling back to the original name and
        overwriting the existing profile). Returns None when no free
        variant fits — callers must treat that as a refusal, not a
        fallback to ``name``.
        """
        if not self.get_profile_path(name).exists():
            return name
        for i in range(2, 1000):
            suffix = f" ({i})"
            candidate = name[: MAX_PROFILE_NAME_LEN - len(suffix)] + suffix
            if sanitize_profile_name(candidate) and not self.get_profile_path(candidate).exists():
                return candidate
        return None

    def _write_profile(self, name: str, profile: ProfileConfig) -> bool:
        """Persist a profile WITHOUT changing the active profile selection."""
        try:
            path = self.get_profile_path(name)
            data = self._profile_to_dict(profile)
            _atomic_write_json(path, data)
            self.profiles_changed.emit()
            return True
        except Exception as e:
            logger.error(f"Failed to write profile {name}: {e}")
            return False

    def _create_xbox360_profile(self, name: str = "Xbox 360") -> ProfileConfig:
        """Create a DS4-to-Xbox 360 profile (emulates Xbox 360 controller)."""
        from ..constants import DS4_TO_XBOX_BTN_MAP
        profile = ProfileConfig(
            name=name,
            device_type=VirtualDeviceType.XBOX,
            button_maps=DS4_TO_XBOX_BTN_MAP.copy(),
            led_color=(0, 212, 170),
        )
        path = self.get_profile_path(name)
        if not path.exists():
            try:
                data = self._profile_to_dict(profile)
                _atomic_write_json(path, data)
                logger.info(f"Created profile: {name}")
                self.profiles_changed.emit()
            except Exception as e:
                logger.error(f"Failed to create profile {name}: {e}")
        return profile

    def _create_ps4_profile(self, name: str = "PlayStation 4") -> ProfileConfig:
        """Create a DS4-to-PS4 profile (emulates DualShock 4 controller)."""
        from ..constants import DS4_TO_PS4_BTN_MAP
        profile = ProfileConfig(
            name=name,
            device_type=VirtualDeviceType.PS4,
            button_maps=DS4_TO_PS4_BTN_MAP.copy(),
            led_color=(0, 212, 170),
        )
        path = self.get_profile_path(name)
        if not path.exists():
            try:
                data = self._profile_to_dict(profile)
                _atomic_write_json(path, data)
                logger.info(f"Created profile: {name}")
                self.profiles_changed.emit()
            except Exception as e:
                logger.error(f"Failed to create profile {name}: {e}")
        return profile

    def seed_default_profiles(self):
        """Create two preset profiles on first launch:

        1. 'Xbox 360' - Emulates an Xbox 360 controller (DS4 buttons → Xbox layout)
        2. 'PlayStation 4' - Emulates a DualShock 4 controller (native PS4 button names)
        """
        profiles_to_create = [
            ("Xbox 360", self._create_xbox360_profile),
            ("PlayStation 4", self._create_ps4_profile),
        ]

        for name, creator in profiles_to_create:
            path = self.get_profile_path(name)
            if not path.exists():
                creator(name)

        # Set Xbox 360 as default if none exists
        if not self._current_profile_name:
            self._current_profile_name = "Xbox 360"
            self._save_last_used()

    def _profile_to_dict(self, profile: ProfileConfig) -> dict:
        return {
            "name": profile.name,
            "device_type": profile.device_type.value,
            "button_maps": profile.button_maps,
            "left_stick": {
                "deadzone": profile.left_stick.deadzone,
                "max_zone": profile.left_stick.max_zone,
                "anti_deadzone": profile.left_stick.anti_deadzone,
                "sensitivity": profile.left_stick.sensitivity,
                "output_curve": profile.left_stick.output_curve,
                "square_stick": profile.left_stick.square_stick,
                "square_stick_value": profile.left_stick.square_stick_value,
                "curve_input": profile.left_stick.curve_input,
                "rotation": profile.left_stick.rotation,
                "inverted": profile.left_stick.inverted,
            },
            "right_stick": {
                "deadzone": profile.right_stick.deadzone,
                "max_zone": profile.right_stick.max_zone,
                "anti_deadzone": profile.right_stick.anti_deadzone,
                "sensitivity": profile.right_stick.sensitivity,
                "output_curve": profile.right_stick.output_curve,
                "square_stick": profile.right_stick.square_stick,
                "square_stick_value": profile.right_stick.square_stick_value,
                "curve_input": profile.right_stick.curve_input,
                "rotation": profile.right_stick.rotation,
                "inverted": profile.right_stick.inverted,
            },
            "left_trigger": {
                "deadzone": profile.left_trigger.deadzone,
                "max_zone": profile.left_trigger.max_zone,
                "anti_deadzone": profile.left_trigger.anti_deadzone,
                "sensitivity": profile.left_trigger.sensitivity,
            },
            "right_trigger": {
                "deadzone": profile.right_trigger.deadzone,
                "max_zone": profile.right_trigger.max_zone,
                "anti_deadzone": profile.right_trigger.anti_deadzone,
                "sensitivity": profile.right_trigger.sensitivity,
            },
            "led_color": profile.led_color,
            "led_brightness": profile.led_brightness,
            "poll_rate_ms": profile.poll_rate_ms,
            "macros": {
                str(ds4_code): [
                    {
                        "action_type": a.action_type,
                        "code": a.code,
                        "value": a.value,
                        "delay": a.delay,
                    }
                    for a in actions
                ]
                for ds4_code, actions in profile.macros.items()
            },
        }

    def _dict_to_profile(self, data: dict) -> ProfileConfig:
        """Build a ProfileConfig from untrusted JSON, validating everything.

        Malformed values are dropped or clamped instead of raising, so a
        crafted file can never crash the worker (bad button codes), divide by
        zero in the input mapper (max_zone) or stall the select() loop
        (poll_rate_ms).
        """
        if not isinstance(data, dict):
            raise ValueError("profile data must be an object")

        # --- button maps: int code -> int code, sane ranges only ---
        button_maps: dict[int, int] = {}
        raw_maps = data.get("button_maps", {})
        if isinstance(raw_maps, dict):
            for k, v in raw_maps.items():
                try:
                    pk, pv = int(k), int(v)
                except (TypeError, ValueError):
                    continue
                if 0 <= pk <= 0x2FFFFFFF and 0 <= pv <= 0x2FFFFFFF:
                    button_maps[pk] = pv

        ls = self._axis_config(data.get("left_stick"), AxisConfig)
        rs = self._axis_config(data.get("right_stick"), AxisConfig)
        lt = self._trigger_config(data.get("left_trigger"))
        rt = self._trigger_config(data.get("right_trigger"))

        macros = self._parse_macros(data.get("macros"))

        led_color = self._led_color(data.get("led_color"))
        try:
            led_brightness = int(data.get("led_brightness", 255))
        except (TypeError, ValueError):
            led_brightness = 255
        led_brightness = max(0, min(255, led_brightness))
        try:
            poll_rate_ms = int(data.get("poll_rate_ms", 10))
        except (TypeError, ValueError):
            poll_rate_ms = 10
        poll_rate_ms = max(MIN_POLL_RATE_MS, min(MAX_POLL_RATE_MS, poll_rate_ms))

        try:
            device_type = VirtualDeviceType(data.get("device_type", "xbox"))
        except ValueError:
            device_type = VirtualDeviceType.XBOX

        name = data.get("name", "Default")
        if not isinstance(name, str):
            name = "Default"

        return ProfileConfig(
            name=name,
            device_type=device_type,
            button_maps=button_maps,
            macros=macros,
            left_stick=ls,
            right_stick=rs,
            left_trigger=lt,
            right_trigger=rt,
            led_color=led_color,
            led_brightness=led_brightness,
            poll_rate_ms=poll_rate_ms,
        )

    @staticmethod
    def _num(value, default: float, lo: float, hi: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return default
        if v != v:  # NaN
            return default
        return max(lo, min(hi, v))

    def _axis_config(self, raw, cls) -> AxisConfig:
        if not isinstance(raw, dict):
            return cls()
        allowed = {f for f in cls.__dataclass_fields__}
        cfg = cls()
        for key, value in raw.items():
            if key not in allowed:
                continue
            if key in ("square_stick", "inverted"):
                setattr(cfg, key, bool(value))
            elif key in ("output_curve",):
                if isinstance(value, str):
                    setattr(cfg, key, value)
            elif key in ("curve_input", "rotation"):
                setattr(cfg, key, int(self._num(value, 0, -360, 360)))
            elif key == "deadzone":
                cfg.deadzone = self._num(value, 0.15, 0.0, 0.99)
            elif key == "max_zone":
                # Must stay > 0: input_mapper divides by max_zone.
                cfg.max_zone = self._num(value, 1.0, 0.05, 10.0)
            elif key == "anti_deadzone":
                cfg.anti_deadzone = self._num(value, 0.0, 0.0, 0.99)
            elif key == "sensitivity":
                cfg.sensitivity = self._num(value, 1.0, 0.01, 20.0)
            elif key == "square_stick_value":
                cfg.square_stick_value = self._num(value, 5.0, 0.0, 100.0)
        return cfg

    def _trigger_config(self, raw) -> TriggerConfig:
        cfg = TriggerConfig()
        if not isinstance(raw, dict):
            return cfg
        cfg.deadzone = self._num(raw.get("deadzone"), 0.05, 0.0, 0.99)
        cfg.max_zone = self._num(raw.get("max_zone"), 1.0, 0.05, 10.0)
        cfg.anti_deadzone = self._num(raw.get("anti_deadzone"), 0.0, 0.0, 0.99)
        cfg.sensitivity = self._num(raw.get("sensitivity"), 1.0, 0.01, 20.0)
        return cfg

    @staticmethod
    def _led_color(raw):
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            try:
                r, g, b = (int(c) for c in raw)
            except (TypeError, ValueError):
                return (0, 0, 255)
            return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
        return (0, 0, 255)

    def _parse_macros(self, raw) -> dict[int, list[MacroAction]]:
        macros: dict[int, list[MacroAction]] = {}
        if not isinstance(raw, dict):
            return macros
        for code_str, actions in raw.items():
            try:
                ds4_code = int(code_str)
            except (TypeError, ValueError):
                continue
            if not (0 <= ds4_code <= 0x2FFFFFFF):
                continue
            macro_actions = []
            for a in actions if isinstance(actions, list) else []:
                if len(macro_actions) >= MAX_MACRO_ACTIONS:
                    break
                if not isinstance(a, dict) or "action_type" not in a:
                    continue
                action_type = a.get("action_type")
                if action_type not in ("key", "wait"):
                    continue
                try:
                    action = MacroAction(
                        action_type=str(action_type),
                        code=int(a.get("code", 0)),
                        value=int(a.get("value", 0)),
                        delay=self._num(a.get("delay", 0.0), 0.0, 0.0, MAX_MACRO_DELAY_S),
                    )
                except (TypeError, ValueError, AttributeError):
                    continue
                if not (0 <= action.code <= 0x2FFFFFFF):
                    continue
                action.value = max(0, min(1, action.value))
                macro_actions.append(action)
            if macro_actions:
                macros[ds4_code] = macro_actions
        return macros
