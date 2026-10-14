import math
from dataclasses import dataclass, field
from enum import Enum

from ..constants import (
    DS4_TO_PS4_BTN_MAP,
    DS4_TO_XBOX_BTN_MAP,
    MAX_AXIS_VALUE,
    MAX_TRIGGER_VALUE,
    PS4_ABS_MAP,
    XBOX_ABS_MAP,
    DS4Abs,
)
from ..engine.virtual_device import VirtualDeviceType
from .macro_engine import MacroAction, MacroEngine


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
    # Preserve the traditional absolute HAT by default; some consumers only
    # recognize four EV_KEY directions, so profiles can opt into button mode.
    dpad_output_mode: str = "hat"
    button_maps: dict[int, int] = field(default_factory=dict)
    macros: dict[int, list[MacroAction]] = field(default_factory=dict)
    left_stick: AxisConfig = field(default_factory=AxisConfig)
    right_stick: AxisConfig = field(default_factory=AxisConfig)
    left_trigger: TriggerConfig = field(default_factory=TriggerConfig)
    right_trigger: TriggerConfig = field(default_factory=TriggerConfig)
    led_color: tuple = (0, 0, 255)
    led_brightness: int = 255
    # Worker select() tick in milliseconds (1-1000 Hz); 10 ms by default.
    poll_rate_ms: int = 10

    def get_button_map(self, physical_code: int) -> int | None:
        return self.button_maps.get(physical_code)

    def set_button_map(self, physical_code: int, virtual_code: int):
        self.button_maps[physical_code] = virtual_code


class InputMapper:
    def __init__(self, profile: ProfileConfig | None = None, macro_engine: MacroEngine | None = None):
        self.profile = profile or ProfileConfig()
        self.macro_engine = macro_engine
        self._axis_state: dict[int, int] = {}
        self._btn_state: dict[int, bool] = {}
        # ds4_code -> virtual code ACTUALLY written to the virtual device.
        # The button_maps can change (profile swap) while a button is down;
        # the release sweep must target the code that was written, not the
        # one the current profile would map it to.
        self._written_virtual: dict[int, int] = {}
        # Target axes last sent to the virtual device, used to neutralize
        # analog outputs when the worker stops or a profile is replaced.
        self._written_axes: dict[int, int] = {}
        self._stick_raw = {
            DS4Abs.X: 128, DS4Abs.Y: 128,
            DS4Abs.RX: 128, DS4Abs.RY: 128,
        }
        self._axis_infos = {}
        # Virtual keys can have several physical sources (for example two
        # buttons deliberately mapped to A). Only emit release when the last
        # source lets go, or an unrelated held input would be cancelled.
        self._virtual_button_sources: dict[int, set[int]] = {}

    def set_profile(self, profile: ProfileConfig):
        self.profile = profile
        self.reset_state()

    @property
    def button_state(self) -> dict:
        """Shared pressed-state cache (evdev code -> bool).

        The worker thread is the only writer while it runs (change
        detection + dedup); the GUI never touches it directly.  Exposed as a
        read-mostly view so callers don't poke at private attributes.
        """
        return self._btn_state

    @property
    def axis_state(self) -> dict:
        """Shared axis cache (evdev code -> last emitted value)."""
        return self._axis_state

    @property
    def written_virtual(self) -> dict:
        """ds4_code -> virtual code actually written to the virtual device
        (release-sweep source of truth across profile swaps)."""
        return self._written_virtual

    @property
    def written_axes(self) -> dict[int, int]:
        """Physical axis code -> virtual axis code last emitted."""
        return self._written_axes

    def is_macro_button(self, ds4_code: int) -> bool:
        """True when the profile binds a macro to this physical button."""
        return bool(self.profile and ds4_code in self.profile.macros)

    def maybe_execute_macro(self, ds4_code: int, value: int) -> bool:
        """Fire the macro bound to ``ds4_code`` (on press only).

        Returns True whenever the button is macro-bound — for both press and
        release — so callers can treat such buttons as fully consumed: a
        macro *replaces* the button instead of coexisting with its mapping.
        """
        if not self.is_macro_button(ds4_code):
            return False
        if value == 1 and self.macro_engine is not None:
            self.macro_engine.execute_macro(self.profile.macros[ds4_code])
        return True

    def map_button(self, ds4_code: int, value: int) -> tuple | None:
        # Linux EV_KEY values are 0=release, 1=press, 2=repeat. A repeat is
        # still down; treating it as release breaks held keys in some drivers.
        if value not in (0, 1, 2):
            return None
        pressed = value != 0
        if self.is_macro_button(ds4_code):
            # Transition-triggered: works for both edge sources (evdev) and
            # level sources (hidraw, which repeats the full state every
            # packet). Macro-bound buttons are consumed in both directions.
            if self._btn_state.get(ds4_code) == pressed:
                return None
            self._btn_state[ds4_code] = pressed
            if pressed and self.macro_engine is not None:
                self.macro_engine.execute_macro(self.profile.macros[ds4_code])
            return None

        if self._btn_state.get(ds4_code) == pressed:
            return None

        if pressed:
            virtual_code = self.profile.button_maps.get(ds4_code)
            if virtual_code is None:
                return None
            self._btn_state[ds4_code] = True
            self._written_virtual[ds4_code] = virtual_code
            sources = self._virtual_button_sources.setdefault(virtual_code, set())
            was_down = bool(sources)
            sources.add(ds4_code)
            return None if was_down else (virtual_code, 1)

        # Release the destination actually pressed, even if a caller edited
        # the mapping dictionary while this source was held.
        virtual_code = self._written_virtual.get(ds4_code)
        if virtual_code is None:
            self._btn_state[ds4_code] = False
            return None
        self._btn_state[ds4_code] = pressed
        self._written_virtual.pop(ds4_code, None)
        sources = self._virtual_button_sources.get(virtual_code)
        if sources is not None:
            sources.discard(ds4_code)
            if sources:
                return None
            self._virtual_button_sources.pop(virtual_code, None)
        return (virtual_code, 0)

    def map_axis(self, ds4_code: int, value: int, axis_info=None) -> tuple | None:
        """Compatibility helper returning the first virtual event for an axis."""
        results = self.map_axes(ds4_code, value, axis_info)
        return results[0] if results else None

    def map_axes(self, ds4_code: int, value: int, axis_info=None) -> list[tuple[int, int]]:
        """Map one physical axis update, including both rotated stick axes."""
        if ds4_code not in self.profile.button_maps and ds4_code not in [DS4Abs.X, DS4Abs.Y, DS4Abs.RX, DS4Abs.RY, DS4Abs.Z, DS4Abs.RZ, DS4Abs.HAT0X, DS4Abs.HAT0Y]:
            return []

        abs_map = XBOX_ABS_MAP if self.profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP
        if ds4_code in (DS4Abs.X, DS4Abs.Y):
            axis_codes = (DS4Abs.X, DS4Abs.Y)
            cfg = self.profile.left_stick
        elif ds4_code in (DS4Abs.RX, DS4Abs.RY):
            axis_codes = (DS4Abs.RX, DS4Abs.RY)
            cfg = self.profile.right_stick
        else:
            axis_codes = ()

        if axis_codes:
            self._stick_raw[ds4_code] = value
            if axis_info is not None:
                self._axis_infos[ds4_code] = axis_info
                center = (axis_info.min + axis_info.max + 1) / 2.0
                other = axis_codes[1] if ds4_code == axis_codes[0] else axis_codes[0]
                if other not in self._axis_infos:
                    self._stick_raw[other] = center
            raw_x, raw_y = (self._stick_raw[code] for code in axis_codes)
            x_info, y_info = (self._axis_infos.get(code) for code in axis_codes)
            x = self._normalize_axis(raw_x, MAX_AXIS_VALUE, cfg, is_stick=True,
                                     axis_info=x_info)
            y = self._normalize_axis(raw_y, MAX_AXIS_VALUE, cfg, is_stick=True,
                                     axis_info=y_info)
            rotation = int(self._setting(cfg.rotation, 0, -360, 360))
            angle = math.radians(rotation % 360)
            if angle:
                x, y = (
                    x * math.cos(angle) - y * math.sin(angle),
                    x * math.sin(angle) + y * math.cos(angle),
                )
            outputs = []
            for code, normalized in zip(axis_codes, (x, y)):
                virtual_code = abs_map.get(code)
                if virtual_code is None:
                    continue
                normalized = max(-MAX_AXIS_VALUE, min(MAX_AXIS_VALUE, int(normalized)))
                self._written_axes[code] = virtual_code
                if self._axis_state.get(code) != normalized:
                    self._axis_state[code] = normalized
                    outputs.append((virtual_code, normalized))
            return outputs

        virtual_code = abs_map.get(ds4_code)
        if virtual_code is None:
            return []
        if ds4_code == DS4Abs.Z:
            cfg = self.profile.left_trigger
        elif ds4_code == DS4Abs.RZ:
            cfg = self.profile.right_trigger
        elif ds4_code in (DS4Abs.HAT0X, DS4Abs.HAT0Y):
            normalized = value
        else:
            return []
        if ds4_code in (DS4Abs.Z, DS4Abs.RZ):
            normalized = self._normalize_trigger(value, cfg, axis_info)

        self._written_axes[ds4_code] = virtual_code
        if self._axis_state.get(ds4_code) == normalized:
            return []
        self._axis_state[ds4_code] = normalized
        return [(virtual_code, normalized)]

    def map_hat(self, ds4_code: int, value: int) -> tuple | None:
        abs_map = XBOX_ABS_MAP if self.profile.device_type == VirtualDeviceType.XBOX else PS4_ABS_MAP
        virtual_code = abs_map.get(ds4_code)
        if virtual_code is None:
            return None
        self._written_axes[ds4_code] = virtual_code
        if self._axis_state.get(ds4_code) == value:
            return None
        self._axis_state[ds4_code] = value
        return (virtual_code, value)

    def _normalize_axis(self, raw: int, max_val: int, cfg: AxisConfig,
                        is_stick: bool = False, axis_info=None) -> int:
        if is_stick:
            lo = getattr(axis_info, "min", 0)
            hi = getattr(axis_info, "max", 255)
            center = (lo + hi + 1) / 2.0 if hi > lo else 128.0
            span = (hi - center) if raw >= center else (center - lo)
            ratio = ((raw - center) / span) if span > 0 else (raw - 128) / 127.0
            ratio = max(-1.0, min(1.0, ratio))
            flat = max(0.0, float(getattr(axis_info, "flat", 0) or 0))
            flat_ratio = flat / max(1.0, (hi - lo) / 2.0)
            normalized = ratio * max_val
        else:
            normalized = raw

        adj = abs(normalized)
        deadzone = max(self._setting(cfg.deadzone, 0.15, 0.0, 0.99), flat_ratio) \
            if is_stick else self._setting(cfg.deadzone, 0.05, 0.0, 0.99)
        max_zone = self._setting(cfg.max_zone, 1.0, 0.05, 10.0)
        anti_deadzone = self._setting(cfg.anti_deadzone, 0.0, 0.0, 0.99)
        sensitivity = self._setting(cfg.sensitivity, 1.0, 0.01, 20.0)
        deadzone_val = deadzone * max_val
        if adj < deadzone_val:
            normalized = 0.0
        else:
            sign = 1 if normalized > 0 else -1
            # Normaliza para 0.0 - 1.0 (após deadzone)
            adj = (adj - deadzone_val) / (max_val * (1.0 - deadzone))
            # Aplica anti-deadzone
            adj = 1.0 - (1.0 - adj) * (1.0 - anti_deadzone)
            # Aplica limite de max_zone
            adj = min(1.0, adj / max_zone)

            # Aplica Curvas matematicamente precisas
            if cfg.output_curve == "Exponential":
                adj = adj ** 2
            elif cfg.output_curve == "Quadratic":
                adj = adj ** 3

            # Aplica sensibilidade
            adj = min(1.0, adj * sensitivity)
            normalized = sign * adj * max_val

        if cfg.square_stick and is_stick:
            if abs(normalized) > 0.001:
                sign_x = 1 if normalized > 0 else -1
                norm = abs(normalized) / max_val
                square_amount = self._setting(cfg.square_stick_value, 5.0, 0.0, 100.0)
                squared = norm ** (1 + square_amount / 100.0)
                normalized = sign_x * squared * max_val

        if cfg.inverted and is_stick:
            normalized = -normalized
        return int(normalized)

    def _normalize_trigger(self, raw: int, cfg: TriggerConfig, axis_info=None) -> int:
        lo = getattr(axis_info, "min", 0)
        hi = getattr(axis_info, "max", MAX_TRIGGER_VALUE)
        if hi <= lo:
            lo, hi = 0, MAX_TRIGGER_VALUE
        normalized = max(0.0, min(1.0, (raw - lo) / (hi - lo)))
        flat = max(0.0, float(getattr(axis_info, "flat", 0) or 0))
        deadzone = max(self._setting(cfg.deadzone, 0.05, 0.0, 0.99), flat / (hi - lo))
        anti_deadzone = self._setting(cfg.anti_deadzone, 0.0, 0.0, 0.99)
        max_zone = self._setting(cfg.max_zone, 1.0, 0.05, 10.0)
        sensitivity = self._setting(cfg.sensitivity, 1.0, 0.01, 20.0)
        if normalized < deadzone:
            normalized = 0.0
        else:
            normalized = (normalized - deadzone) / (1.0 - deadzone)
            normalized = 1.0 - (1.0 - normalized) * (1.0 - anti_deadzone)
            normalized = min(1.0, normalized / max_zone)
            normalized = min(1.0, normalized * sensitivity)
        return int(normalized * MAX_TRIGGER_VALUE)

    @staticmethod
    def _setting(value, default: float, minimum: float, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return max(minimum, min(maximum, number))

    def reset_state(self):
        self._axis_state.clear()
        self._btn_state.clear()
        self._written_virtual.clear()
        self._written_axes.clear()
        self._virtual_button_sources.clear()
        self._stick_raw = {
            DS4Abs.X: 128, DS4Abs.Y: 128,
            DS4Abs.RX: 128, DS4Abs.RY: 128,
        }
        self._axis_infos.clear()

    def get_default_mapping(self, device_type: VirtualDeviceType) -> dict[int, int]:
        if device_type == VirtualDeviceType.XBOX:
            return DS4_TO_XBOX_BTN_MAP.copy()
        return DS4_TO_PS4_BTN_MAP.copy()
