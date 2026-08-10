from enum import IntEnum, Enum
from pathlib import Path


class EVType(IntEnum):
    SYN = 0x00
    KEY = 0x01
    REL = 0x02
    ABS = 0x03
    MSC = 0x04
    SW = 0x05
    LED = 0x11
    SND = 0x12
    REP = 0x14
    FF = 0x15
    PWR = 0x16
    FF_STATUS = 0x17


class DS4Abs(IntEnum):
    X = 0x00
    Y = 0x01
    Z = 0x02
    RX = 0x03
    RY = 0x04
    RZ = 0x05
    THROTTLE = 0x06
    RUDDER = 0x07
    WHEEL = 0x08
    GAS = 0x09
    BRAKE = 0x0A
    HAT0X = 0x10
    HAT0Y = 0x11
    HAT1X = 0x12
    HAT1Y = 0x13
    HAT2X = 0x14
    HAT2Y = 0x15
    HAT3X = 0x16
    HAT3Y = 0x17
    PRESSURE = 0x18
    DISTANCE = 0x19
    TILT_X = 0x1A
    TILT_Y = 0x1B
    TOOL_WIDTH = 0x1C
    VOLUME = 0x20
    MISC = 0x28


class DS4Btn(IntEnum):
    SOUTH = 0x130
    EAST = 0x131
    NORTH = 0x133
    WEST = 0x134
    TL = 0x136
    TR = 0x137
    TL2 = 0x138
    TR2 = 0x139
    SELECT = 0x13A
    START = 0x13B
    THUMBL = 0x13D
    THUMBR = 0x13E
    DPAD_UP = 0x220
    DPAD_DOWN = 0x221
    DPAD_LEFT = 0x222
    DPAD_RIGHT = 0x223
    PS = 0x13C
    TOUCHPAD = 0x13F


class XboxBtn(IntEnum):
    A = 0x130
    B = 0x131
    X = 0x133
    Y = 0x134
    LB = 0x136
    RB = 0x137
    LT = 0x138
    RT = 0x139
    BACK = 0x13A
    START = 0x13B
    THUMBL = 0x13D
    THUMBR = 0x13E
    DPAD_UP = 0x220
    DPAD_DOWN = 0x221
    DPAD_LEFT = 0x222
    DPAD_RIGHT = 0x223
    GUIDE = 0x13C


class PS4Btn(IntEnum):
    CROSS = 0x130
    CIRCLE = 0x131
    TRIANGLE = 0x133
    SQUARE = 0x134
    L1 = 0x136
    R1 = 0x137
    L2 = 0x138
    R2 = 0x139
    SHARE = 0x13A
    OPTIONS = 0x13B
    L3 = 0x13D
    R3 = 0x13E
    DPAD_UP = 0x220
    DPAD_DOWN = 0x221
    DPAD_LEFT = 0x222
    DPAD_RIGHT = 0x223
    PS = 0x13C
    TOUCHPAD = 0x13F


class XboxAbs(IntEnum):
    X = 0x00
    Y = 0x01
    Z = 0x02
    RX = 0x03
    RY = 0x04
    RZ = 0x05
    HAT0X = 0x10
    HAT0Y = 0x11


DS4_TO_XBOX_BTN_MAP = {
    DS4Btn.SOUTH: XboxBtn.A,
    DS4Btn.EAST: XboxBtn.B,
    DS4Btn.NORTH: XboxBtn.Y,
    DS4Btn.WEST: XboxBtn.X,
    DS4Btn.TL: XboxBtn.LB,
    DS4Btn.TR: XboxBtn.RB,
    DS4Btn.TL2: XboxBtn.LT,
    DS4Btn.TR2: XboxBtn.RT,
    DS4Btn.SELECT: XboxBtn.BACK,
    DS4Btn.START: XboxBtn.START,
    DS4Btn.THUMBL: XboxBtn.THUMBL,
    DS4Btn.THUMBR: XboxBtn.THUMBR,
    DS4Btn.DPAD_UP: XboxBtn.DPAD_UP,
    DS4Btn.DPAD_DOWN: XboxBtn.DPAD_DOWN,
    DS4Btn.DPAD_LEFT: XboxBtn.DPAD_LEFT,
    DS4Btn.DPAD_RIGHT: XboxBtn.DPAD_RIGHT,
    DS4Btn.PS: XboxBtn.GUIDE,
}

DS4_TO_PS4_BTN_MAP = {
    DS4Btn.SOUTH: PS4Btn.CROSS,
    DS4Btn.EAST: PS4Btn.CIRCLE,
    DS4Btn.NORTH: PS4Btn.TRIANGLE,
    DS4Btn.WEST: PS4Btn.SQUARE,
    DS4Btn.TL: PS4Btn.L1,
    DS4Btn.TR: PS4Btn.R1,
    DS4Btn.TL2: PS4Btn.L2,
    DS4Btn.TR2: PS4Btn.R2,
    DS4Btn.SELECT: PS4Btn.SHARE,
    DS4Btn.START: PS4Btn.OPTIONS,
    DS4Btn.THUMBL: PS4Btn.L3,
    DS4Btn.THUMBR: PS4Btn.R3,
    DS4Btn.DPAD_UP: PS4Btn.DPAD_UP,
    DS4Btn.DPAD_DOWN: PS4Btn.DPAD_DOWN,
    DS4Btn.DPAD_LEFT: PS4Btn.DPAD_LEFT,
    DS4Btn.DPAD_RIGHT: PS4Btn.DPAD_RIGHT,
    DS4Btn.PS: PS4Btn.PS,
    DS4Btn.TOUCHPAD: PS4Btn.TOUCHPAD,
}

DS4_ABS_MAP = {
    DS4Abs.X: DS4Abs.X,
    DS4Abs.Y: DS4Abs.Y,
    DS4Abs.RX: DS4Abs.RX,
    DS4Abs.RY: DS4Abs.RY,
    DS4Abs.Z: DS4Abs.Z,
    DS4Abs.RZ: DS4Abs.RZ,
    DS4Abs.HAT0X: DS4Abs.HAT0X,
    DS4Abs.HAT0Y: DS4Abs.HAT0Y,
}

XBOX_ABS_MAP = {
    DS4Abs.X: XboxAbs.X,
    DS4Abs.Y: XboxAbs.Y,
    DS4Abs.RX: XboxAbs.RX,
    DS4Abs.RY: XboxAbs.RY,
    DS4Abs.Z: XboxAbs.Z,
    DS4Abs.RZ: XboxAbs.RZ,
    DS4Abs.HAT0X: XboxAbs.HAT0X,
    DS4Abs.HAT0Y: XboxAbs.HAT0Y,
}

PS4_ABS_MAP = {
    DS4Abs.X: DS4Abs.X,
    DS4Abs.Y: DS4Abs.Y,
    DS4Abs.RX: DS4Abs.RX,
    DS4Abs.RY: DS4Abs.RY,
    DS4Abs.Z: DS4Abs.Z,
    DS4Abs.RZ: DS4Abs.RZ,
    DS4Abs.HAT0X: DS4Abs.HAT0X,
    DS4Abs.HAT0Y: DS4Abs.HAT0Y,
}

DS4_VID = 0x054C
DS4_PID = 0x09CC
DS4_PID_DONGLE = 0x0BA0

UINPUT_PATH = Path("/dev/uinput")
HIDRAW_BASE = Path("/dev/hidraw")
SYS_LEDS_BASE = Path("/sys/class/leds")

DEFAULT_DEADZONE = 0.15
DEFAULT_SENSITIVITY = 1.0
MAX_AXIS_VALUE = 32767
MAX_TRIGGER_VALUE = 255

PROFILE_DIR = Path.home() / ".config" / "ds4linux" / "profiles"
CONFIG_FILE = Path.home() / ".config" / "ds4linux" / "config.json"

UDEV_RULE_CONTENT = '''# DS4Linux udev rules
# Allow non-root access to DualShock 4 controllers
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="09cc", MODE="0666"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ba0", MODE="0666"
# Allow uinput access for virtual device creation
KERNEL=="uinput", MODE="0666", GROUP="input"
'''

VIRTUAL_DEVICE_TYPES = ("xbox", "ps4")


class VirtualDeviceType(Enum):
    XBOX = "xbox"
    PS4 = "ps4"


APP_NAME = "DS4Linux"
APP_VERSION = "1.0.0"
ORG_NAME = "DS4Linux"
ORG_DOMAIN = "ds4linux.app"