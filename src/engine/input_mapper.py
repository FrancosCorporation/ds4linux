from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from enum import Enum

from evdev import ecodes as e

from ..constants import (
    DS4Btn, DS4Abs, XboxBtn, PS4Btn, XboxAbs,
    DS4_TO_XBOX_BTN_MAP, DS4_TO_PS4_BTN_MAP,
    DS4_ABS_MAP, XBOX_ABS_MAP, PS4_ABS_MAP,
    MAX_AXIS_VALUE, MAX_TRIGGER_VALUE,
)
from ..engine.virtual_device import VirtualDeviceType


class Stick(Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass
class AxisConfig:
    deadzone: float = 0.15
    max_zone: float = 1.0
    anti_deadzone: float = 0.0
    sensitivity: float = 1.0
    output_curve: str = "Linear"
    square_stick: bool = False
    square_stick_value: float = 5.0
    curve_input: int = 0
    rotation: int = 0
    inverted: bool = False


@dataclass
class TriggerConfig:
    deadzone: float = 0.05
    max_zone: float = 1.0
    anti_deadzone: float = 0.0
    sensitivity: float = 1.0


@dataclass
class ButtonMap:
    physical_code: int
    virtual_code: int


@dataclass
class ProfileConfig:
    name: str = "Default"
    device_type: VirtualDeviceType = VirtualDeviceType.XBOX
    button_maps: Dict[int, int] = field(default_factory=dict)
    left_stick: AxisConfig = field(default_factory=AxisConfig)
    right_stick: AxisConfig = field(default_factory=AxisConfig)
    left_trigger: TriggerConfig = field(default_factory=TriggerConfig)
    right_trigger: TriggerConfig = field(default_factory=TriggerConfig)
    led_color: tuple = (0, 0, 255)
    led_brightness: int = 255

    def get_button_map(self, physical_code: int) -> Optional[int]:
        return self.button_maps.get(physical_code)

    def set_button_map(self, physical_code: int, virtual_code: int):
        self.button_maps[physical_code] = virtual_code


class InputMapper:
    def __init__(self, profile: Optional[ProfileConfig] = None):
        self.profile = profile or ProfileConfig()
        self._axis_state: Dict[int, int] = {}
        self._btn_state: Dict[int, bool] = {}

    def set_profile(self, profile: ProfileConfig):
        self.profile = profile
        self.reset_state()

    def map_button(self, ds4_code: int, value: int) -> Optional[tuple]:
        if ds4_code not in self.profile.button_maps:
            return None
        virtual_code = self.profile.button_maps[ds4_code]
        pressed = value == 1
        if self._btn_state.get(ds4_code) == pressed:
            return None
        self._btn_state[ds4_code] = pressed
        return (virtual_code, 1 if pressed else 0)

    def map_axis(self, ds4_code: int, value: int) -> Optional[tuple]:
        if ds4_code not in self.profile.button_maps and ds4_code not in [DS4Abs.X, DS4Abs.Y, DS4Abs.RX, DS4Abs.RY, DS4Abs.Z, DS4Abs.RZ, DS4Abs.HAT0X, DS4Abs.HAT0Y]:
            return None

        abs_map = XBOX_ABS_MAP if self.profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP
        virtual_code = abs_map.get(ds4_code)
        if virtual_code is None:
            return None

        if ds4_code in (DS4Abs.X, DS4Abs.Y):
            cfg = self.profile.left_stick
            normalized = self._normalize_axis(value, MAX_AXIS_VALUE, cfg, is_stick=True)
        elif ds4_code in (DS4Abs.RX, DS4Abs.RY):
            cfg = self.profile.right_stick
            normalized = self._normalize_axis(value, MAX_AXIS_VALUE, cfg, is_stick=True)
        elif ds4_code == DS4Abs.Z:
            cfg = self.profile.left_trigger
            normalized = self._normalize_trigger(value, cfg)
        elif ds4_code == DS4Abs.RZ:
            cfg = self.profile.right_trigger
            normalized = self._normalize_trigger(value, cfg)
        else:
            normalized = value

        if self._axis_state.get(ds4_code) == normalized:
            return None
        self._axis_state[ds4_code] = normalized
        return (virtual_code, normalized)

    def map_hat(self, ds4_code: int, value: int) -> Optional[tuple]:
        abs_map = XBOX_ABS_MAP if self.profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP
        virtual_code = abs_map.get(ds4_code)
        if virtual_code is None:
            return None
        if self._axis_state.get(ds4_code) == value:
            return None
        self._axis_state[ds4_code] = value
        return (virtual_code, value)

    def _normalize_axis(self, raw: int, max_val: int, cfg: AxisConfig, is_stick: bool = False) -> int:
        if is_stick:
            # DS4 sends 0-255 with center at 128; virtual device expects -max_val..+max_val
            normalized = (raw - 128) * (max_val / 127.0)
        else:
            normalized = raw

        adj = abs(normalized)
        deadzone_val = cfg.deadzone * max_val
        if adj < deadzone_val:
            normalized = 0.0
        else:
            sign = 1 if normalized > 0 else -1
            adj = (adj - deadzone_val) / (max_val * (1.0 - cfg.deadzone))
            adj = 1.0 - (1.0 - adj) * (1.0 - cfg.anti_deadzone)
            adj = min(1.0, adj * cfg.max_zone)
            adj = adj * cfg.sensitivity
            normalized = sign * adj * max_val

        if cfg.square_stick and is_stick:
            import math
            if abs(normalized) > 0.001:
                sign_x = 1 if normalized > 0 else -1
                norm = abs(normalized) / max_val
                squared = norm ** (1 + cfg.square_stick_value / 100.0)
                normalized = sign_x * squared * max_val

        if cfg.inverted and is_stick:
            normalized = -normalized
        return int(normalized)

    def _normalize_trigger(self, raw: int, cfg: TriggerConfig) -> int:
        normalized = raw / MAX_TRIGGER_VALUE
        if normalized < cfg.deadzone:
            normalized = 0.0
        else:
            normalized = min(1.0, (normalized - cfg.deadzone) / (1.0 - cfg.deadzone) * cfg.sensitivity)
        return int(normalized * MAX_TRIGGER_VALUE)

    def reset_state(self):
        self._axis_state.clear()
        self._btn_state.clear()

    def get_default_mapping(self, device_type: VirtualDeviceType) -> Dict[int, int]:
        if device_type == VirtualDeviceType.XBOX:
            return DS4_TO_XBOX_BTN_MAP.copy()
        return DS4_TO_PS4_BTN_MAP.copy()