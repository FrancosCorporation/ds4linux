# DS4Linux

**DualShock 4 Emulator for Linux** - Use your PlayStation 4 controller as an Xbox or PlayStation 4 virtual controller on Linux.

## Features

- **Xbox 360 / XInput emulation** - Play any game with native Xbox controller support
- **PlayStation 4 / DS4 emulation** - Native PS4 support for Steam and compatible games
- **Zero sudo required** - udev rules grant user-space access to controller and uinput
- **Exclusive device grab** - Prevents double input (both physical + virtual)
- **LED lightbar control** - Full RGB control with brightness, presets, and per-profile colors
- **Advanced stick/trigger tuning** - Deadzone, sensitivity, inversion per axis
- **Profile system** - Save/load multiple configurations (JSON)
- **System tray integration** - Minimize to tray, runs in background
- **Dark/Minimalist UI** - DS4Windows-inspired PySide6 interface
- **Background daemon** - QThread-based event loop, never blocks GUI

## Architecture

```
ds4linux/
├── udev/                    # udev rules for non-root access
├── assets/                  # Icons, controller images
├── src/
│   ├── constants.py         # Centralized evdev/uinput codes
│   ├── engine/
│   │   ├── device_manager.py    # DS4 detection & grab()
│   │   ├── led_controller.py    # /sys/class/leds/ RGB control
│   │   ├── virtual_device.py    # uinput device factory (Xbox/PS4)
│   │   ├── input_mapper.py      # DS4 → virtual translation
│   │   └── worker_thread.py     # QThread read_loop
│   ├── config/
│   │   └── profile_manager.py   # JSON profile persistence
│   └── gui/
│       ├── main_window.py       # Main window + system tray
│       ├── color_dialog.py      # HSV color picker
│       └── styles.py            # QSS Dark theme
├── install.sh                 # System installer (udev, .desktop, venv)
├── requirements.txt           # Python dependencies
└── README.md
```

## Quick Start

### 🚀 One-Command Install (Recommended)

```bash
git clone https://github.com/FrancosCorporation/ds4linux.git
cd ds4linux
sudo ./install.sh
```

**That's it!** The installer handles everything:
- System dependencies (python3, libevdev, uinput, PySide6)
- Python virtual environment with all packages
- udev rules for non-root controller access
- Desktop entry + icon for application menu
- `ds4linux` command in `/usr/local/bin`

Then run `ds4linux` from terminal or find **"DS4Linux"** in your application menu.

### Manual Installation (Alternative)

### Manual Installation

```bash
# Install system dependencies
# Ubuntu/Debian:
sudo apt install python3 python3-pip python3-venv libevdev2 libevdev-dev

# Arch:
sudo pacman -S python python-pip python-virtualenv libevdev

# Fedora:
sudo dnf install python3 python3-pip python3-virtualenv libevdev libevdev-devel

# Create venv & install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install udev rules (requires root)
sudo cp udev/99-ds4linux.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# Add your user to input group
sudo usermod -a -G input $USER
# Log out and back in

# Run
python3 -m src.main
```

## Usage

1. **Connect your DS4** via USB or Bluetooth
2. **Launch DS4Linux** - it will auto-detect the controller
3. **Click "Connect"** - creates virtual Xbox/PS4 device
4. **Configure** - Adjust deadzones, sensitivity, LED color in tabs
5. **Save Profile** - Settings persist across restarts
6. **Minimize to tray** - Close window to keep running in background

## Supported Controllers

| Controller | USB VID:PID | Bluetooth VID:PID | Status |
|------------|-------------|-------------------|--------|
| DualShock 4 v1 | 054c:09cc | 054c:0ba0 | ✅ Full |
| DualShock 4 v2 | 054c:09cc | 054c:0ba0 | ✅ Full |
| DualSense (PS5) | 054c:0ce6 | - | ⚠️ Basic |

## Virtual Device Types

| Type | Vendor:Product | Use Case |
|------|----------------|----------|
| Xbox 360 | 045e:028e | XInput games, Steam, most native Linux games |
| PS4 / DS4 | 054c:09cc | Steam (PS4 support), PlayStation Now, Remote Play |

## Configuration

Profiles stored in `~/.config/ds4linux/profiles/*.json`:

```json
{
  "name": "My Profile",
  "device_type": "xbox",
  "button_maps": { "304": 304, "305": 305, ... },
  "left_stick": { "deadzone": 0.15, "sensitivity": 1.0, "inverted": false },
  "right_stick": { "deadzone": 0.15, "sensitivity": 1.0, "inverted": false },
  "left_trigger": { "deadzone": 0.05, "sensitivity": 1.0 },
  "right_trigger": { "deadzone": 0.05, "sensitivity": 1.0 },
  "led_color": [0, 212, 170],
  "led_brightness": 255
}
```

## Building from Source

```bash
# Development install (editable)
pip install -e .

# Run directly
python3 -m src.main
```

## Troubleshooting

**Controller not detected:**
- Ensure udev rules installed: `ls /etc/udev/rules.d/99-ds4linux.rules`
- Reload: `sudo udevadm control --reload-rules && sudo udevadm trigger`
- Check groups: `groups $USER` should include `input`
- Reboot after group changes

**Permission denied on /dev/uinput:**
- Check udev rule for uinput exists
- Verify: `ls -la /dev/uinput` should be `crw-rw-rw-`

**Double input (both physical + virtual):**
- DS4Linux uses `evdev.grab()` for exclusive access
- Ensure no other tools (steam, ds4drv) are grabbing the device

**LED not working:**
- Requires kernel 5.10+ with `hid_playstation` module
- Check: `ls /sys/class/leds/` for `*::kbd_backlight` or similar

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## Acknowledgments

- [evdev](https://github.com/gvalkov/python-evdev) - Linux input event library
- [PySide6](https://wiki.qt.io/Qt_for_Python) - Qt6 Python bindings
- [DS4Windows](https://github.com/Ryochan7/DS4Windows) - UI/UX inspiration
- Linux kernel `hid_playstation` and `uinput` subsystems