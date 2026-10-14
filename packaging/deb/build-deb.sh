#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="${1:-$REPO_DIR/dist}"

if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [output-directory]\n' "$0" >&2
    exit 2
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
    printf 'dpkg-deb is required to build the Debian package.\n' >&2
    exit 1
fi

VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$REPO_DIR/src/__init__.py")"
if [[ ! "$VERSION" =~ ^[0-9][A-Za-z0-9.+:~.-]*$ ]]; then
    printf 'Could not read a valid Debian package version from src/__init__.py.\n' >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
PACKAGE_ROOT="$(mktemp -d)"
trap 'rm -rf -- "$PACKAGE_ROOT"' EXIT

install -d \
    "$PACKAGE_ROOT/DEBIAN" \
    "$PACKAGE_ROOT/usr/bin" \
    "$PACKAGE_ROOT/usr/lib/ds4linux/src" \
    "$PACKAGE_ROOT/usr/lib/udev/rules.d" \
    "$PACKAGE_ROOT/usr/share/applications" \
    "$PACKAGE_ROOT/usr/share/doc/ds4linux" \
    "$PACKAGE_ROOT/usr/share/ds4linux/assets" \
    "$PACKAGE_ROOT/usr/share/ds4linux/udev" \
    "$PACKAGE_ROOT/usr/share/icons/hicolor/256x256/apps"
chmod 0755 "$PACKAGE_ROOT"

while IFS= read -r -d '' source_file; do
    relative_path="${source_file#"$REPO_DIR/src/"}"
    install -D -m 0644 "$source_file" "$PACKAGE_ROOT/usr/lib/ds4linux/src/$relative_path"
done < <(find "$REPO_DIR/src" -type f -name '*.py' -print0)
install -m 0644 "$REPO_DIR/assets/icon.png" "$PACKAGE_ROOT/usr/share/ds4linux/assets/icon.png"
install -m 0644 "$REPO_DIR/assets/ds4_controller.png" "$PACKAGE_ROOT/usr/share/ds4linux/assets/ds4_controller.png"
install -m 0644 "$REPO_DIR/assets/joystick.png" "$PACKAGE_ROOT/usr/share/ds4linux/assets/joystick.png"
install -m 0644 "$REPO_DIR/udev/99-ds4linux.rules" "$PACKAGE_ROOT/usr/share/ds4linux/udev/99-ds4linux.rules"
install -m 0644 "$REPO_DIR/udev/99-ds4linux.rules" "$PACKAGE_ROOT/usr/lib/udev/rules.d/99-z-ds4linux.rules"
install -m 0644 "$REPO_DIR/README.md" "$PACKAGE_ROOT/usr/share/doc/ds4linux/README.md"
install -m 0644 "$REPO_DIR/CHANGELOG.md" "$PACKAGE_ROOT/usr/share/doc/ds4linux/CHANGELOG.md"
install -m 0644 "$REPO_DIR/LICENSE" "$PACKAGE_ROOT/usr/share/doc/ds4linux/LICENSE"
install -m 0644 "$REPO_DIR/assets/icon.png" \
    "$PACKAGE_ROOT/usr/share/icons/hicolor/256x256/apps/ds4linux.png"

cat > "$PACKAGE_ROOT/usr/bin/ds4linux" <<'LAUNCHER'
#!/bin/sh
set -eu
cd /usr/lib/ds4linux
PYTHONPATH=/usr/lib/ds4linux
export PYTHONPATH
exec /usr/bin/python3 -m src.main "$@"
LAUNCHER
chmod 0755 "$PACKAGE_ROOT/usr/bin/ds4linux"

# Fonte única do desktop entry (também usada por install.sh e pelo PKGBUILD).
install -m 0644 "$REPO_DIR/packaging/ds4linux.desktop" \
    "$PACKAGE_ROOT/usr/share/applications/ds4linux.desktop"

# Installed-Size é exigido pela Política de Pacotes Debian (§5.6.12).
INSTALLED_SIZE="$(du -sk "$PACKAGE_ROOT/usr" | cut -f1)"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<CONTROL
Package: ds4linux
Version: $VERSION
Section: games
Priority: optional
Architecture: all
Installed-Size: $INSTALLED_SIZE
Maintainer: FrancosCorporation <rodolfofranco14@hotmail.com>
Homepage: https://github.com/FrancosCorporation/ds4linux
Depends: python3 (>= 3.10), python3-evdev (>= 1.6.1), python3-pyudev (>= 0.24), python3-pyside6.qtwidgets (>= 6.5), python3-pyside6.qtnetwork (>= 6.5), udev
Description: DualShock 4 input and virtual-controller utility
 DS4Linux reads compatible Sony controller input and exposes a virtual
 Xbox 360 or PlayStation 4 controller to Linux applications and games.
 The package installs device access rules; the application runs as the
 logged-in desktop user and does not need to run as root.
CONTROL

install -m 0755 "$SCRIPT_DIR/postinst" "$PACKAGE_ROOT/DEBIAN/postinst"
install -m 0755 "$SCRIPT_DIR/postrm" "$PACKAGE_ROOT/DEBIAN/postrm"

PACKAGE_FILE="$OUTPUT_DIR/ds4linux_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" "$PACKAGE_FILE" >/dev/null
printf 'Built %s\n' "$PACKAGE_FILE"
