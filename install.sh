#!/bin/bash
# DS4Linux Installer
# Run with: sudo ./install.sh

set -e

APP_NAME="DS4Linux"
INSTALL_DIR="/opt/ds4linux"
BIN_DIR="/usr/local/bin"
DESKTOP_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
UDEV_RULES_DIR="/etc/udev/rules.d"
SYSTEMD_DIR="/etc/systemd/system"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

detect_distro() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
    else
        DISTRO="unknown"
    fi
    log_info "Detected distribution: $DISTRO $VERSION"
}

install_dependencies() {
    log_info "Installing system dependencies..."
    case $DISTRO in
        ubuntu|debian|linuxmint|pop|elementary|zorin)
            apt-get update
            apt-get install -y python3 python3-pip python3-venv \
                libevdev2 libevdev-dev \
                libxcb-cursor0 \
                python3-pyqt6 python3-pyqt6.qtsvg || true
            ;;
        arch|manjaro|endeavouros|garuda)
            pacman -Sy --needed --noconfirm python python-pip python-virtualenv \
                libevdev \
                libxcb \
                pyside6 qt6-svg || true
            ;;
        fedora|rhel|centos|rocky|almalinux)
            dnf install -y python3 python3-pip python3-virtualenv \
                libevdev libevdev-devel \
                libxcb \
                python3-pyside6 qt6-qtsvg || true
            ;;
        opensuse*|suse)
            zypper install -y python3 python3-pip python3-virtualenv \
                libevdev2 libevdev-devel \
                libxcb \
                python3-pyside6 qt6-qtsvg || true
            ;;
        *)
            log_warning "Unknown distribution. Please install manually:"
            log_warning "  - python3, python3-pip, python3-venv"
            log_warning "  - libevdev, uinput"
            log_warning "  - PySide6 (Qt6)"
            ;;
    esac
}

create_virtualenv() {
    log_info "Creating virtual environment at $INSTALL_DIR..."
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
}

install_files() {
    log_info "Installing application files..."
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='venv' --exclude='.venv' --exclude='*.egg-info' \
        "$SCRIPT_DIR/src/" "$INSTALL_DIR/src/"
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/README.md" "$INSTALL_DIR/" 2>/dev/null || true
}

install_udev_rules() {
    log_info "Installing udev rules..."
    cp "$SCRIPT_DIR/udev/99-ds4linux.rules" "$UDEV_RULES_DIR/"
    udevadm control --reload-rules
    udevadm trigger
    log_success "udev rules installed and triggered"
}

create_launcher() {
    log_info "Creating launcher script..."
    cat > "$BIN_DIR/ds4linux" << 'EOF'
#!/bin/bash
cd /opt/ds4linux
source venv/bin/activate
exec python3 -m src.main "$@"
EOF
    chmod +x "$BIN_DIR/ds4linux"
}

create_desktop_entry() {
    log_info "Creating desktop entry..."
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/ds4linux.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DS4Linux
GenericName=DualShock 4 Emulator
Comment=Emulate Xbox/PS4 controller with DualShock 4 on Linux
Exec=ds4linux
Icon=ds4linux
Terminal=false
Categories=Game;Settings;HardwareSettings;
StartupNotify=true
Keywords=controller;dualshock;playstation;xbox;emulator;
EOF
}

create_icon() {
    log_info "Creating application icon..."
    mkdir -p "$ICON_DIR"
    python3 << 'PYEOF'
from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush
from PySide6.QtCore import Qt

pixmap = QPixmap(256, 256)
pixmap.fill(Qt.transparent)
painter = QPainter(pixmap)
painter.setRenderHint(QPainter.Antialiasing)

# Background circle
painter.setBrush(QBrush(QColor(30, 30, 46)))
painter.setPen(Qt.NoPen)
painter.drawEllipse(8, 8, 240, 240)

# Main body
painter.setBrush(QBrush(QColor(0, 212, 170)))
painter.drawRoundedRect(40, 60, 176, 136, 30, 30)

# Touchpad
painter.setBrush(QBrush(QColor(20, 20, 35)))
painter.drawRoundedRect(60, 75, 136, 40, 8, 8)

# Sticks
painter.setBrush(QBrush(QColor(40, 40, 55)))
painter.drawEllipse(70, 140, 48, 48)
painter.drawEllipse(138, 140, 48, 48)

# D-pad
painter.drawEllipse(70, 80, 24, 24)

# Face buttons
painter.setBrush(QBrush(QColor(40, 40, 55)))
painter.drawEllipse(180, 100, 24, 24)
painter.drawEllipse(208, 128, 24, 24)
painter.drawEllipse(180, 156, 24, 24)
painter.drawEllipse(152, 128, 24, 24)

# Shoulder buttons
painter.setBrush(QBrush(QColor(0, 180, 145)))
painter.drawRoundedRect(30, 50, 80, 18, 8, 8)
painter.drawRoundedRect(146, 50, 80, 18, 8, 8)

painter.end()
pixmap.save("/usr/share/icons/hicolor/256x256/apps/ds4linux.png")
PYEOF
}

setup_user_permissions() {
    log_info "Setting up user permissions..."
    for user in $(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd); do
        usermod -a -G input "$user" 2>/dev/null || true
    done
    log_success "Users added to input group (re-login required)"
}

main() {
    echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║       DS4Linux Installer v1.0        ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
    echo

    check_root
    detect_distro

    log_info "Starting installation..."

    install_dependencies
    create_virtualenv
    install_files
    install_udev_rules
    create_launcher
    create_desktop_entry
    create_icon
    setup_user_permissions

    echo
    log_success "═══════════════════════════════════════"
    log_success "  DS4Linux installed successfully!"
    log_success "═══════════════════════════════════════"
    echo
    log_info "Run 'ds4linux' from terminal or find it in your application menu"
    log_warning "Please log out and back in (or reboot) for udev/group changes to take effect"
    echo
}

main "$@"