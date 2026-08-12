import json
from pathlib import Path
from typing import Dict, List, Optional
import logging

from PySide6.QtCore import QObject, Signal

from ..constants import PROFILE_DIR, CONFIG_FILE
from ..engine.virtual_device import VirtualDeviceType
from ..engine.input_mapper import ProfileConfig, AxisConfig, TriggerConfig

logger = logging.getLogger(__name__)


class ProfileManager(QObject):
    """Manages profile loading, saving, and listing."""

    profiles_changed = Signal()

    def __init__(self):
        super().__init__()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._current_profile_name: Optional[str] = None
        self._load_last_used()
        self.seed_default_profiles()

    def _load_last_used(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self._current_profile_name = data.get("last_profile")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")

    def _save_last_used(self):
        try:
            data = {"last_profile": self._current_profile_name}
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_profile_path(self, name: str) -> Path:
        return PROFILE_DIR / f"{name}.json"

    def list_profiles(self) -> List[str]:
        profiles = []
        for f in PROFILE_DIR.glob("*.json"):
            profiles.append(f.stem)
        if "default" not in [p.lower() for p in profiles]:
            profiles.insert(0, "Default")
        return sorted(profiles, key=str.lower)

    def load_profile(self, name: str) -> ProfileConfig:
        path = self.get_profile_path(name)
        if not path.exists():
            # Fallback to Xbox 360 if requested profile doesn't exist
            if name.lower() in ("xbox 360", "default"):
                return self._create_xbox360_profile("Xbox 360")
            return self.load_profile("Xbox 360")

        try:
            with open(path, "r") as f:
                data = json.load(f)
            profile = self._dict_to_profile(data)
            self._current_profile_name = name
            self._save_last_used()
            logger.info(f"Loaded profile: {name}")
            return profile
        except Exception as e:
            logger.error(f"Failed to load profile {name}: {e}")
            return self._create_default_profile()

    def save_profile(self, name: str, profile: ProfileConfig) -> bool:
        path = self.get_profile_path(name)
        try:
            data = self._profile_to_dict(profile)
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self._current_profile_name = name
            self._save_last_used()
            logger.info(f"Saved profile: {name}")
            self.profiles_changed.emit()
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {name}: {e}")
            return False

    def create_profile(self, name: str) -> ProfileConfig:
        """Create a new profile with default settings and return it."""
        profile = self._create_default_profile(name)
        self.save_profile(name, profile)
        return profile

    def delete_profile(self, name: str) -> bool:
        if name.lower() == "default":
            return False
        path = self.get_profile_path(name)
        try:
            if path.exists():
                path.unlink()
                if self._current_profile_name == name:
                    self._current_profile_name = None
                    self._save_last_used()
                logger.info(f"Deleted profile: {name}")
                self.profiles_changed.emit()
                return True
        except Exception as e:
            logger.error(f"Failed to delete profile {name}: {e}")
        return False

    def get_current_profile_name(self) -> Optional[str]:
        return self._current_profile_name

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
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
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
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
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
        }

    def _dict_to_profile(self, data: dict) -> ProfileConfig:
        button_maps = {int(k): v for k, v in data.get("button_maps", {}).items()}
        ls = data.get("left_stick", {})
        rs = data.get("right_stick", {})
        lt = data.get("left_trigger", {})
        rt = data.get("right_trigger", {})
        return ProfileConfig(
            name=data.get("name", "Default"),
            device_type=VirtualDeviceType(data.get("device_type", "xbox")),
            button_maps=button_maps,
            left_stick=AxisConfig(**ls),
            right_stick=AxisConfig(**rs),
            left_trigger=TriggerConfig(**lt),
            right_trigger=TriggerConfig(**rt),
            led_color=tuple(data.get("led_color", (0, 0, 255))),
            led_brightness=data.get("led_brightness", 255),
        )