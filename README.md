# DS4Linux

**DualShock 4 Emulator for Linux** - Use your PlayStation 4 controller as an Xbox or PlayStation 4 virtual controller on Linux.

## Features

- **Multi-controller support** - Up to 2 DS4 controllers simultaneously (USB/Bluetooth)
- **Xbox 360 / XInput emulation** - Play any game with native Xbox controller support
- **PlayStation 4 / DS4 emulation** - Native PS4 support for Steam and compatible games
- **Proton/Wine compatibility** - Virtual device with USB bustype, INPUT_PROP_GAMEPAD, BTN_GAMEPAD for AAA games via Heroic/Lutris/Proton
- **Zero sudo required** - udev rules grant user-space access to controller and uinput
- **Exclusive device grab** - Prevents double input (both physical + virtual)
- **LED lightbar control** - Full RGB control with brightness, presets, battery gradient, per-profile colors
- **Advanced stick/trigger tuning** - Deadzone, max zone, anti-deadzone, sensitivity, output curve, square stick, rotation
- **Per-controller profiles** - Independent profiles per controller slot (JSON)
- **Visual button mapping** - DS4 outline with clickable mapping list
- **Touchpad configuration** - Mouse mode, controls mode, gestures, jitter compensation
- **Gyro support** - Mouse emulation, sensitivity, calibration
- **Rumble forwarding** - EV_FF/FF_RUMBLE from games forwarded to physical controller via select()-based async I/O
- **System tray integration** - Minimize to tray, runs in background
- **Dark/Minimalist UI** - DS4Windows-inspired PySide6 interface (Controllers table, Profile tabs)
- **Background daemon** - QThread-based event loop, never blocks GUI

## Architecture

```
ds4linux/
├── udev/                    # udev rules for non-root access
├── assets/                  # Icons, controller images
├── src/
│   ├── constants.py         # Centralized evdev/uinput codes
│   ├── engine/
│   │   ├── device_manager.py     # DS4 detection & grab()
│   │   ├── led_controller.py     # /sys/class/leds/ RGB control
│   │   ├── virtual_device.py     # uinput device factory (Xbox/PS4)
│   │   ├── input_mapper.py       # DS4 → virtual translation
│   │   ├── worker_thread.py      # QThread read_loop per controller
│   │   ├── controller_slot.py    # Per-controller state (device, virtual, mapper, LED)
│   │   └── multi_device_manager.py # Manages up to 2 controller slots
│   ├── config/
│   │   └── profile_manager.py    # JSON profile persistence
│   └── gui/
│       ├── main_window.py        # Main window with Controllers/Profiles/Auto Profiles/Settings/Log tabs
│       ├── color_dialog.py       # HSV color picker
│       └── styles.py             # QSS Dark theme
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
- System dependencies (python3, libevdev, libxcb-cursor0, PySide6)
- Python virtual environment with all packages
- udev rules for non-root controller access
- Desktop entry + icon for application menu
- `ds4linux` command in `/usr/local/bin`

Then run `ds4linux` from terminal or find **"DS4Linux"** in your application menu.

### Manual Installation (Alternative)

```bash
# Install system dependencies
# Ubuntu/Debian:
sudo apt install python3 python3-pip python3-venv libevdev2 libevdev-dev libxcb-cursor0

# Arch:
sudo pacman -S python python-pip python-virtualenv libevdev libxcb

# Fedora:
sudo dnf install python3 python3-pip python3-virtualenv libevdev libevdev-devel libxcb

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

1. **Connect your DS4** via USB or Bluetooth (up to 2 controllers)
2. **Launch DS4Linux** - it will auto-detect controllers
3. **Controllers tab** - View all connected controllers in a table (ID, Status, Battery, Profile, LED color)
4. **Click "Editar"** on a controller row - Opens per-controller Profile tab
5. **Configure** in Profile tab:
   - **Controls** - Visual DS4 mapping, Touchpad mode, button list
   - **Axis Config** - LS/RS/L2/R2 deadzone, maxzone, anti-deadzone, sensitivity, curves
   - **Lightbar** - Color picker, brightness, presets, battery gradient
   - **Gyro** - Enable, mouse mode, sensitivity, calibration
   - **Other** - Rumble, LED behavior, auto-reconnect
6. **Save Profile** - Settings persist per controller slot
7. **Minimize to tray** - Close window to keep running in background

## GUI Overview (DS4Windows-style)

### Main Tabs
| Tab | Description |
|-----|-------------|
| **Controllers** | Table view of all controller slots with status, battery, profile dropdown, LED color, edit button |
| **Profiles** | Placeholder - select controller from Controllers tab |
| **Auto Profiles** | Coming soon - auto-switch profiles by game |
| **Settings** | Startup options, udev installer, about |
| **Log** | Real-time event log |

### Per-Controller Profile Tab (opened via "Editar")
- **Header**: Profile name, Save/Cancel, Keep window size
- **Controls**: Visual DS4 outline + mapping list + Touchpad settings
- **Axis Config**: LS/RS/L2/R2 advanced tuning (deadzone, maxzone, anti-deadzone, sensitivity, output curve, square stick, rotation)
- **Lightbar**: HSV color picker, presets, brightness, battery gradient colors
- **Gyro**: Enable, mouse mode, sensitivity, calibration
- **Other**: Rumble intensity, LED behavior modes, connection settings
- **Footer**: Status, Hotkeys/About link, Stop button

## Supported Controllers

| Controller | USB VID:PID | Bluetooth VID:PID | Status |
|------------|-------------|-------------------|--------|
| DualShock 4 v1 | 054c:09cc | 054c:0ba0 | ✅ Full |
| DualShock 4 v2 | 054c:09cc | 054c:0ba0 | ✅ Full |
| DualSense (PS5) | 054c:0ce6 | - | ⚠️ Basic |

## Virtual Device Types

| Type | Vendor:Product | Bustype | Features |
|------|----------------|---------|----------|
| Xbox 360 | 045e:028e | USB (0x03) | BTN_GAMEPAD, INPUT_PROP_GAMEPAD, EV_FF rumble |
| PS4 / DS4 | 054c:09cc | USB (0x03) | BTN_GAMEPAD, INPUT_PROP_GAMEPAD, EV_FF rumble |

*Each controller slot can independently emulate Xbox or PS4*

### Proton/Wine Compatibility

Virtual devices are created with characteristics expected by Windows game APIs running under Proton/Wine:
- **USB bustype** (0x03) - Required by SDL/XInput device enumeration
- **INPUT_PROP_GAMEPAD** - Kernel property flag for gamepad recognition
- **BTN_GAMEPAD** - Standard gamepad button code for input mapping
- **phys=ds4linux-uinput-\<slot\>** - Unique physical address per slot, prevents self-detection by the monitor
- **EV_FF/FF_RUMBLE** - Force feedback events from games are forwarded to the physical controller

Start DS4Linux **before** launching your game via Heroic, Lutris, or Proton.

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

**Game doesn't recognize controller (Proton/Wine):**
- Start DS4Linux **before** launching the game
- Disable Steam Input if using Steam
- Try switching virtual device type (Xbox/PS4) in profile
- Check `evtest /dev/input/eventXX` - virtual device should show `bustype=0x3` and `BTN_GAMEPAD`

**Rumble not working:**
- Ensure game is not running through Steam Input (which intercepts FF)
- Test with `evtest` - write FF event to virtual node, check physical output

**Qt platform plugin error (xcb):**
- Install: `sudo apt install libxcb-cursor0` (Ubuntu/Debian)
- Or use Wayland: `QT_QPA_PLATFORM=wayland ds4linux`

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