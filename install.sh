#!/bin/bash
# DS4Linux Installer
# Run with: sudo ./install.sh

set -e

APP_NAME="DS4Linux"
INSTALL_DIR="${DS4LINUX_INSTALL_DIR:-/opt/ds4linux}"
BIN_DIR="${DS4LINUX_BIN_DIR:-/usr/local/bin}"
DESKTOP_DIR="${DS4LINUX_DESKTOP_DIR:-/usr/share/applications}"
ICON_DIR="${DS4LINUX_ICON_DIR:-/usr/share/icons/hicolor/256x256/apps}"
UDEV_RULES_DIR="${DS4LINUX_UDEV_RULES_DIR:-/etc/udev/rules.d}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$SCRIPT_DIR/src/__init__.py")"

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

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_error "Required command not found: $1"
        return 1
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
            apt-get install -y python3 python3-pip python3-venv python3-dev build-essential rsync \
                libevdev2 libevdev-dev libxcb-cursor0 libegl1
            ;;
        arch|manjaro|endeavouros|garuda)
            pacman -Sy --needed --noconfirm python python-pip python-virtualenv base-devel rsync \
                libevdev libxcb
            ;;
        fedora|rhel|centos|rocky|almalinux)
            dnf install -y python3 python3-pip python3-devel gcc rsync \
                libevdev libevdev-devel libxcb libxkbcommon-x11
            ;;
        opensuse*|suse)
            zypper install -y python3 python3-pip python3-devel gcc rsync \
                libevdev2 libevdev-devel libxcb
            ;;
        *)
            log_error "Unsupported distribution '$DISTRO'; install prerequisites manually and extend this installer."
            return 1
            ;;
    esac
    require_command rsync
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
    mkdir -p "$INSTALL_DIR/assets" "$INSTALL_DIR/udev"
    rsync -a "$SCRIPT_DIR/assets/" "$INSTALL_DIR/assets/"
    rsync -a "$SCRIPT_DIR/udev/" "$INSTALL_DIR/udev/"
    install -m 0644 "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
    install -m 0644 "$SCRIPT_DIR/README.md" "$INSTALL_DIR/README.md"
    install -m 0644 "$SCRIPT_DIR/CHANGELOG.md" "$INSTALL_DIR/CHANGELOG.md"
    install -m 0644 "$SCRIPT_DIR/LICENSE" "$INSTALL_DIR/LICENSE"
    install -m 0644 "$SCRIPT_DIR/CONTRIBUTING.md" "$INSTALL_DIR/CONTRIBUTING.md"
}

install_udev_rules() {
    log_info "Installing udev rules..."
    install -D -m 0644 "$INSTALL_DIR/udev/99-ds4linux.rules" \
        "$UDEV_RULES_DIR/99-ds4linux.rules"
    udevadm control --reload-rules
    udevadm trigger --action=add
    log_success "udev rules installed and triggered"
}

create_launcher() {
    log_info "Creating launcher script..."
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/ds4linux" << EOF
#!/bin/sh
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/venv/bin/python" -m src.main "\$@"
EOF
    chmod +x "$BIN_DIR/ds4linux"
}

create_desktop_entry() {
    log_info "Creating desktop entry..."
    mkdir -p "$DESKTOP_DIR"
    install -m 0644 "$SCRIPT_DIR/packaging/ds4linux.desktop" "$DESKTOP_DIR/ds4linux.desktop"
}

create_icon() {
    log_info "Installing application icon..."
    install -D -m 0644 "$SCRIPT_DIR/assets/icon.png" "$ICON_DIR/ds4linux.png"
}

load_hid_playstation_module() {
    log_info "Configuring hid-playstation kernel module to load on boot..."
    
    # Add module to load at boot
    echo "hid-playstation" > /etc/modules-load.d/ds4linux.conf
    
    # Load it now for current session
    if modprobe hid-playstation 2>/dev/null; then
        log_success "hid-playstation module loaded and configured for boot"
    else
        log_warning "hid-playstation will be requested by the app; this kernel may not provide the module"
    fi
}

main() {
    echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     DS4Linux Installer v${APP_VERSION}       ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
    echo

    check_root
    detect_distro

    log_info "Starting installation..."

    install_dependencies
    create_virtualenv
    install_files
    install_udev_rules
    load_hid_playstation_module
    create_launcher
    create_desktop_entry
    create_icon

    echo
    log_success "═══════════════════════════════════════"
    log_success "  DS4Linux installed successfully!"
    log_success "═══════════════════════════════════════"
    echo
    log_info "Run 'ds4linux' from terminal or find it in your application menu"
    log_warning "Reconnect the controller for udev permissions to take effect"
    echo
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
