# DS4Linux

**DualShock 4 Emulator for Linux** - Use your PlayStation 4 controller as an Xbox or PlayStation 4 virtual controller on Linux.

## Features

- **Multi-controller support** - Up to 2 DS4 controllers simultaneously (USB/Bluetooth)
- **Xbox 360 / XInput emulation** - Play any game with native Xbox controller support
- **PlayStation 4 / DS4 emulation** - Native PS4 support for Steam and compatible games
- **Proton/Wine compatibility** - Virtual device with USB bustype, INPUT_PROP_GAMEPAD, BTN_GAMEPAD for AAA games via Heroic/Lutris/Proton
- **Zero sudo required** - udev rules grant user-space access to controller and uinput
- **Exclusive device grab** - Prevents double input (both physical + virtual)
- **LED lightbar control** - Full RGB control via HID output reports (78 bytes, BT format) + sysfs brightness for virtual display
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
├── udev/                          # udev rules for non-root access
│   └── 99-ds4linux.rules          # Controller + uinput + LED permissions
├── assets/                        # Icons, controller images
├── src/
│   ├── constants.py               # evdev/uinput codes, button maps, axis maps, version
│   │
│   ├── engine/                    # Core input processing engine
│   │   ├── device_monitor.py      # pyudev hot-plug detection (add/remove DS4 via udev netlink)
│   │   ├── device_manager.py      # Scans /dev/input, filters real DS4 (VID/PID), calls grab()
│   │   ├── controller_slot.py     # Per-controller state machine: attach/detach, LED, profile, worker lifecycle
│   │   ├── worker_thread.py       # QThread: select()-based I/O on physical fd + uinput fd
│   │   │                          #   → maps buttons/axes physical→virtual (EV_KEY, EV_ABS)
│   │   │                          #   → forwards rumble virtual→physical (EV_FF → device.write)
│   │   ├── virtual_device.py      # UInput factory: Xbox 360 / PS4 emulation
│   │   │                          #   → bustype=USB, INPUT_PROP_GAMEPAD, BTN_GAMEPAD, EV_FF/FF_RUMBLE
│   │   │                          #   → phys=ds4linux-uinput-<slot> (prevents monitor self-detection)
│   │   ├── input_mapper.py        # DS4→virtual translation: deadzone, sensitivity, anti-deadzone,
│   │   │                          #   output curve, square stick, rotation per stick/trigger
│   │   ├── led_controller.py      # /sys/class/leds/ RGB control (virtual display) + HID output report (78 bytes) for physical LED
│   │   │                          #   LED path via sysfs device symlink matching
│   │   └── multi_device_manager.py # Manages 2 slots, HID parent grouping (gamepad+sensors+touchpad),
│   │                              #   device assignment, reconnect on BT change
│   │
│   ├── config/
│   │   └── profile_manager.py     # JSON profile CRUD in ~/.config/ds4linux/profiles/
│   │                              #   Per-slot independent profiles with button_maps, axis config,
│   │                              #   LED color/brightness, device type, touchpad/gyro settings
│   │
│   └── gui/                       # PySide6 dark UI (DS4Windows-inspired)
│       ├── main_window.py         # Tab container: Controllers, Profiles, Auto Profiles, Settings, Log
│       │                          #   SVG icon loading, system tray, about dialog
│       ├── controllers_table.py   # Table view: slot ID, status, battery, profile combo, LED color cell,
│       │                          #   edit button → opens ControllerTab
│       ├── controller_tab.py      # Per-controller profile editor:
│       │                          #   MappingTabWidget (overlay interativo + wizard)
│       │                          #   LightbarWidget (HSV picker, presets, brightness slider)
│       │                          #   AxisConfigWidget (LS/RS/L2/R2 spinboxes, curves, square stick)
│       │                          #   TouchpadWidget, GyroWidget, OtherWidget
│       │                          #   Profile load/save/cancel, device type switch
│       ├── mapping_tab.py         # Nova interface de mapeamento:
│       │                          #   ControllerOverlayWidget (imagem + botões transparentes)
│       │                          #   ListenDialog (captura evento bruto do evdev)
│       │                          #   MappingWizardDialog (wizard passo-a-passo)
│       ├── color_dialog.py        # Custom HSV color wheel dialog (ported from DS4Windows C#)
│       ├── visual_mapping.py      # DS4 SVG outline with clickable button regions
│       └── styles.py              # QSS dark theme: #1e1e2e bg, #00d4aa accent, rounded corners
│
├── install.sh                     # System installer:
│   │                              #   → apt/pip dependencies, venv, udev rules
│   │                              #   → SVG→PNG icon conversion (QtSvg), desktop entry
│   │                              #   → /usr/local/bin/ds4linux launcher script
│   │                              #   → chown/chmod existing LED sysfs (udevadm trigger doesn't reapply)
├── requirements.txt               # python-evdev, PySide6, pyudev
├── setup.py                       # Package metadata
└── README.md
```

### Data Flow

```
DS4 (USB/BT)                    DS4Linux                          Game (Proton/Wine)
─────────────                   ──────────                        ──────────────────
 event18 (gamepad) ──grab()──→ worker_thread
 event19 (sensors)              │ read_loop()
 event20 (touchpad)             │
                                ├── EV_KEY/EV_ABS ──→ input_mapper ──→ virtual_device.write()
                                │   (DS4 buttons)      (mapping)       (EV_KEY/EV_ABS to uinput)
                                │                                         │
                                │                                         ▼
                                │                                   /dev/input/event21
                                │                                   "Sony Interactive
                                │                                    Entertainment
                                │                                    Wireless Controller"
                                │                                         │
                                │                                    Game reads events
                                │                                    (buttons, sticks)
                                │
                                ├── EV_FF (rumble) ←──── game writes FF ──→ uinput fd
                                │   select() on uinput_fd                  │
                                │   device.write(EV_FF, code, value) ─────→ DS4 hardware
                                │                                         (physical vibration)
                                │
                                                                                        └── LED sysfs ──→ /sys/class/leds/input88:{red,green,blue}/brightness (virtual display)
                                                                                        └── HID output report (78 bytes, BT format, hw_control=0xC4) ──→ physical LED
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

## Roadmap

### v1.0.0 - Core Engine (Done)
- [x] DS4 detection via udev (USB + Bluetooth)
- [x] Exclusive device grab (evdev)
- [x] Xbox 360 virtual device emulation (uinput)
- [x] PS4 virtual device emulation (uinput)
- [x] Button mapping (DS4 → Xbox / DS4 → PS4)
- [x] Axis mapping with deadzone, sensitivity, anti-deadzone
- [x] Trigger mapping (L2/R2)
- [x] D-pad mapping
- [x] Per-slot controller architecture
- [x] QThread background event loop (zero GUI lag)

### v1.1.0 - LED & UI (Done)
- [x] LED lightbar control via `/sys/class/leds/` (virtual display)
- [x] HID output reports (78 bytes, BT format) for physical LED lightbar
- [x] RGB color picker (HSV)
- [x] LED presets (solid, pulse, rainbow, battery gradient)
- [x] Per-profile LED colors
- [x] Two-controller LED differentiation (per-slot input path)
- [x] udev rules for non-root LED access
- [x] install.sh LED permission fix (chown/chmod for existing devices)
- [x] Dark/minimalist UI (DS4Windows-inspired)
- [x] Controllers table (status, battery, profile, LED, edit)
- [x] Per-controller profile tabs (Controls, Axis, Lightbar, Gyro, Other)
- [x] Visual button mapping with DS4 outline
- [x] Touchpad configuration (mouse/controls mode, gestures)
- [x] Gyro support (mouse emulation, sensitivity, calibration)
- [x] System tray integration
- [x] SVG icon + desktop entry

### v1.2.0 - Proton/Wine Compatibility (Done)
- [x] USB bustype (0x03) on virtual device
- [x] INPUT_PROP_GAMEPAD kernel property flag
- [x] BTN_GAMEPAD explicit capability
- [x] EV_FF/FF_RUMBLE declaration + force feedback forwarding
- [x] select()-based async I/O for rumble (physical ↔ virtual)
- [x] Unique phys per slot (ds4linux-uinput-\<slot\>)
- [x] PS4 name: "Sony Interactive Entertainment Wireless Controller"
- [x] HID output reports (78 bytes, BT format, hw_control=0xC4) for physical LED lightbar
- [x] HID output report forwarding for games that bypass evdev
- [x] README + documentation

### v1.3.0 - In Progress
- [x] **ControllerTab UI refactor** - QScrollArea, QSizePolicy, margin/spacing cleanup, slider redesign, controller diagram L2/R2
- [x] **MappingTab interativo** - Overlay sobre imagem do controle, Listen Mode, Wizard de mapeamento rápido
- [x] **LEDController multi-fallback** - Detecção hid-sony/hid-playstation, HID report + sysfs colors/brightness
- [x] **WorkerThread raw_event** - Sinal para captura de eventos brutos pela UI
- [x] **udev rules corrigidas** - MODE="0666" + TAG+="uaccess" para LEDs e hidraw
- [ ] **God of War verification** - End-to-end test with Heroic/Proton
- [ ] **SDL GUID validation** - Confirm virtual device GUID matches expected Xbox/PS4 signatures
- [ ] **Rumble magnitude mapping** - Proportional forwarding (game sends 0-1 → map to physical 0-255)

### v1.4.0 - Planned
- [ ] **Auto-profiles** - Switch profiles automatically per game (detect via window title / game binary)
- [ ] **Profile import/export** - Share profiles as `.ds4profile` files
- [ ] **DualSense (PS5) full support** - Adaptive triggers, haptic feedback, microphone LED
- [ ] **Steam Input compatibility** - Coexist with Steam Input without conflicts
- [ ] **Macro support** - Record and playback button sequences
- [ ] **On-screen display (OSD)** - Battery/connection notifications overlay

### v2.0.0 - Community & Ecosystem
- [ ] **Multi-controller beyond 2** - Support 4+ controllers
- [ ] **Xbox controller passthrough** - Use DS4Linux as a configuration layer for Xbox controllers too
- [ ] **Motion aim integration** - Gyro-based aiming for FPS games (Steam Input style)
- [ ] **Community profile repository** - Browse and download shared profiles
- [ ] **Flatpak / AppImage packaging** - Universal Linux distribution
- [ ] **AUR / RPM / DEB packages** - Native package manager support
- [ ] **Wayland native support** - Full functionality under Wayland without XWayland
- [ ] **CLI daemon mode** - Headless operation for servers / embedded setups
- [ ] **Gamepad tester** - Built-in input visualization and diagnostics tool
- [ ] **HID report forwarding** - Direct HID communication for games that bypass evdev

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