import json
from pathlib import Path
from typing import Dict, List, Optional
import logging

from ..constants import PROFILE_DIR, CONFIG_FILE, VirtualDeviceType
from ..engine.input_mapper import ProfileConfig, AxisConfig, TriggerConfig

logger = logging.getLogger(__name__)


class ProfileManager:
    def __init__(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._current_profile_name: Optional[str] = None
        self._load_last_used()

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
            if name.lower() == "default":
                return self._create_default_profile()
            return self.load_profile("Default")

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
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {name}: {e}")
            return False

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
                return True
        except Exception as e:
            logger.error(f"Failed to delete profile {name}: {e}")
        return False

    def get_current_profile_name(self) -> Optional[str]:
        return self._current_profile_name

    def _create_default_profile(self) -> ProfileConfig:
        from ..constants import DS4_TO_XBOX_BTN_MAP
        profile = ProfileConfig(
            name="Default",
            device_type=VirtualDeviceType.XBOX,
            button_maps=DS4_TO_XBOX_BTN_MAP.copy(),
        )
        self.save_profile("Default", profile)
        return profile

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