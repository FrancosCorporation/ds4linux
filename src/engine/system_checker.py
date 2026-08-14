from __future__ import annotations

import os
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

UDEVS_RULES_SOURCE = Path(__file__).parent.parent.parent / "udev" / "99-ds4linux.rules"
UDEVS_RULES_DEST = Path("/etc/udev/rules.d/99-ds4linux.rules")
MODULE_NAME = "hid-playstation"
CONFIG_DIR = Path.home() / ".config" / "ds4linux"
SUDO_PASS_FILE = CONFIG_DIR / ".sudo_pass"


def _get_stored_password() -> Optional[str]:
    """Read stored sudo password from config, if available."""
    try:
        if SUDO_PASS_FILE.exists():
            return SUDO_PASS_FILE.read_text().strip()
    except Exception:
        pass
    return None


def _has_stored_password() -> bool:
    """Check if a sudo password is already saved."""
    return _get_stored_password() is not None


def _store_password(password: str) -> bool:
    """Store sudo password securely in user config (mode 600)."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SUDO_PASS_FILE.write_text(password)
        os.chmod(SUDO_PASS_FILE, 0o600)
        return True
    except Exception as e:
        logger.error(f"Failed to store password: {e}")
        return False


def _run_sudo(command: str, password: Optional[str] = None) -> Tuple[int, str, str]:
    """Run a command with sudo, providing password via stdin."""
    pw = password or _get_stored_password()
    try:
        proc = subprocess.run(
            ["sudo", "-S", "sh", "-c", command],
            input=f"{pw}\n",
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        logger.error(f"sudo run error: {e}")
        return 1, "", str(e)


def is_module_loaded(module: str = MODULE_NAME) -> bool:
    """Check if the hid-playstation kernel module is loaded."""
    try:
        result = subprocess.run(["lsmod"], capture_output=True, text=True)
        # lsmod uses underscores (hid_playstation), but MODULE_NAME uses hyphens (hid-playstation)
        return module.replace("-", "_") in result.stdout or module in result.stdout
    except Exception as e:
        logger.debug(f"Error checking module: {e}")
        return False


def load_module(module: str = MODULE_NAME, password: Optional[str] = None) -> bool:
    """Load the hid-playstation kernel module."""
    if is_module_loaded(module):
        logger.info(f"Module {module} already loaded")
        return True

    returncode, stdout, stderr = _run_sudo(f"modprobe {module}", password)
    if returncode == 0:
        logger.info(f"Module {module} loaded successfully")
        return True
    else:
        logger.error(f"Failed to load {module}: {stderr}")
        return False


def is_udev_rules_installed() -> bool:
    """Check if DS4Linux udev rules are installed."""
    if not UDEVS_RULES_DEST.exists():
        return False
    try:
        content = UDEVS_RULES_DEST.read_text()
        return "054c" in content.lower() and "uinput" in content.lower()
    except Exception:
        return False


def install_udev_rules(password: Optional[str] = None) -> Tuple[bool, str]:
    """Install DS4Linux udev rules and reload udev."""
    if not UDEVS_RULES_SOURCE.exists():
        logger.error(f"Rules source not found: {UDEVS_RULES_SOURCE}")
        return False, "Regras udev não encontradas no projeto"

    if is_udev_rules_installed():
        logger.info("udev rules already installed")
        _fix_led_permissions(password)
        return True, "Regras udev já instaladas"

    cmd = (
        f"cp '{UDEVS_RULES_SOURCE}' '{UDEVS_RULES_DEST}' && "
        "udevadm control --reload-rules && "
        "udevadm trigger"
    )
    returncode, stdout, stderr = _run_sudo(cmd, password)
    if returncode == 0:
        logger.info("udev rules installed and reloaded successfully")
    else:
        logger.error(f"Failed to install udev rules: {stderr}")
        return False, stderr

    _fix_led_permissions(password)
    return True, "Regras udev instaladas"


def _fix_led_permissions(password: Optional[str] = None):
    """Fix LED sysfs permissions for existing DS4 controllers."""
    import glob
    led_patterns = [
        "/sys/class/leds/input*:red/brightness",
        "/sys/class/leds/input*:green/brightness",
        "/sys/class/leds/input*:blue/brightness",
        "/sys/class/leds/input*:global/brightness",
    ]
    user = os.getenv("USER", "servidor")
    for pattern in led_patterns:
        for path in glob.glob(pattern):
            if os.path.exists(path):
                _run_sudo(f"chown {user}:{user} '{path}'", password)
                _run_sudo(f"chmod 0666 '{path}'", password)


def scan_ds4_devices() -> list:
    """Scan for connected DS4 controllers via evdev."""
    try:
        import evdev
        devices = []
        for d in evdev.list_devices():
            try:
                dev = evdev.InputDevice(d)
                if dev.info.vendor == 0x054C and dev.info.product in (0x09CC, 0x0BA0, 0x05C4):
                    if "motion" not in dev.name.lower() and "touchpad" not in dev.name.lower():
                        devices.append({
                            "path": d,
                            "name": dev.name,
                            "uniq": dev.uniq,
                            "phys": dev.phys,
                        })
            except Exception:
                pass
        return devices
    except Exception as e:
        logger.error(f"Error scanning devices: {e}")
        return []


def ensure_system_ready(password: Optional[str] = None) -> Tuple[bool, list]:
    """
    Ensure all system requirements are met.
    Returns (success, list_of_messages).
    """
    messages = []

    # Auto-load hid-playstation module if needed
    if not is_module_loaded():
        logger.info("Auto-loading hid-playstation module...")
        if load_module(password=password):
            messages.append("✅ Driver hid-playstation carregado")
        else:
            messages.append("❌ Falha ao carregar hid-playstation")

    # Auto-install udev rules if needed
    if not is_udev_rules_installed():
        logger.info("Auto-installing udev rules...")
        ok, msg = install_udev_rules(password=password)
        if ok:
            messages.append("✅ Regras udev instaladas")
        else:
            messages.append(f"❌ Falha ao instalar regras udev: {msg}")

    # Fix LED permissions
    _fix_led_permissions(password)

    # Scan for controllers
    devices = scan_ds4_devices()
    if devices:
        for dev in devices:
            messages.append(f"✅ Controle detectado: {dev['name']} ({dev['path']})")
    else:
        messages.append("⚠️ Nenhum controle DS4 detectado — conecte o controle")

    all_ok = all("❌" not in m for m in messages)
    return all_ok, messages


def needs_setup() -> bool:
    """Check if system setup is required."""
    return not is_module_loaded() or not is_udev_rules_installed()


def auto_setup() -> Tuple[bool, list]:
    """
    Try to set up the system automatically using stored password.
    Returns (success, messages).
    If no password is stored, returns (False, ["Sem senha salva"]) so caller knows to prompt.
    """
    password = _get_stored_password()
    if not password:
        return False, ["Nenhuma senha salva — configuração manual necessária"]

    return ensure_system_ready(password=password)


def setup_with_password(password: str) -> Tuple[bool, list]:
    """
    Save password and run full setup.
    Call this when user provides password in the dialog.
    """
    if not _store_password(password):
        return False, ["Falha ao salvar senha"]
    return ensure_system_ready(password=password)


def clear_stored_password():
    """Remove stored sudo password."""
    try:
        if SUDO_PASS_FILE.exists():
            SUDO_PASS_FILE.unlink()
    except Exception:
        pass
