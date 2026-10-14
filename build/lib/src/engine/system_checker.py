from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from ..resource_paths import resource_path

logger = logging.getLogger(__name__)

UDEVS_RULES_SOURCE = resource_path("udev", "99-ds4linux.rules")
UDEVS_RULES_DEST = Path("/etc/udev/rules.d/99-ds4linux.rules")
UDEVS_RULES_PACKAGE_DEST = Path("/usr/lib/udev/rules.d/99-z-ds4linux.rules")
UDEVS_RULES_PACKAGE_OVERRIDE = Path("/etc/udev/rules.d/99-z-ds4linux.rules")
MODULE_NAME = "hid-playstation"
SUDO_PASS_FILE = Path.home() / ".config" / "ds4linux" / ".sudo_pass"


def _current_audit_session_id() -> str | None:
    """Return this process' Linux audit session ID, if it has one."""
    try:
        session_id = Path(f"/proc/{os.getpid()}/sessionid").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return session_id if session_id and session_id != "4294967295" else None


def _active_graphical_audit_session_ids() -> set[str]:
    """Return audit IDs for active seat-backed X11/Wayland sessions."""
    loginctl = shutil.which("loginctl")
    if loginctl is None:
        return set()
    try:
        sessions = subprocess.run(
            [loginctl, "list-sessions", "--no-legend", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if sessions.returncode != 0:
        return set()

    active_ids: set[str] = set()
    for line in sessions.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        try:
            details = subprocess.run(
                [
                    loginctl,
                    "show-session",
                    fields[0],
                    "-p",
                    "Active",
                    "-p",
                    "Audit",
                    "-p",
                    "Seat",
                    "-p",
                    "Type",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if details.returncode != 0:
            continue
        properties = dict(
            line.partition("=")[::2]
            for line in details.stdout.splitlines()
            if "=" in line
        )
        audit_id = properties.get("Audit", "")
        if (
            properties.get("Active") == "yes"
            and properties.get("Type") in {"x11", "wayland"}
            and properties.get("Seat")
            and audit_id
            and audit_id != "4294967295"
        ):
            active_ids.add(audit_id)
    return active_ids


def _user_linger_enabled() -> bool:
    """Report whether logind keeps this user's manager alive outside logins."""
    loginctl = shutil.which("loginctl")
    if loginctl is None:
        return False
    try:
        result = subprocess.run(
            [loginctl, "show-user", str(os.getuid()), "-p", "Linger"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "Linger=yes" in result.stdout.splitlines()


def _polkit_agent_error_message() -> str:
    process_session = _current_audit_session_id()
    active_sessions = _active_graphical_audit_session_ids()
    if process_session and active_sessions and process_session not in active_sessions:
        active_text = ", ".join(sorted(active_sessions))
        linger_text = (
            " O linger está habilitado para este usuário, mantendo esse gerenciador ativo fora "
            "da sessão gráfica; desativá-lo pode interromper serviços em segundo plano."
            if _user_linger_enabled()
            else ""
        )
        return (
            "O Polkit não encontrou um agente gráfico para a sessão deste processo. "
            f"O DS4Linux pertence à sessão de auditoria {process_session}, mas a sessão "
            f"gráfica ativa usa {active_text}.{linger_text} É necessário iniciar o GNOME e "
            "o DS4Linux na mesma sessão logind. Revise a configuração de linger, salve seu "
            "trabalho e recrie a sessão gráfica; encerrar apenas a janela do app não resolve. "
            "Essa falha ocorreu antes da operação privilegiada; nenhuma alteração foi aplicada."
        )
    return (
        "O Polkit não encontrou um agente gráfico registrado para este processo e não há "
        "terminal controlador (/dev/tty). Verifique se o agente de autorização do desktop está "
        "ativo na sessão atual e tente novamente. Nenhuma alteração privilegiada foi aplicada."
    )


def _run_privileged(*command: str) -> tuple[int, str, str]:
    """Run one fixed argument-vector operation through the desktop polkit agent."""
    if not command or any(not isinstance(arg, str) or "\x00" in arg for arg in command):
        return 1, "", "Comando privilegiado inválido"
    runner = shutil.which("pkexec")
    if runner is None:
        return 127, "", "pkexec não está disponível; aplique a configuração manualmente"
    try:
        proc = subprocess.run(
            [runner, *command],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        stderr = proc.stderr
        normalized_error = stderr.casefold()
        if (
            "textual authentication agent" in normalized_error
            and "current controlling terminal" in normalized_error
        ):
            stderr = _polkit_agent_error_message()
        return proc.returncode, proc.stdout, stderr
    except subprocess.TimeoutExpired:
        return 124, "", "A autorização/operação privilegiada excedeu 60 segundos"
    except Exception as e:
        logger.error("Privileged operation failed: %s", e)
        return 1, "", str(e)


def is_module_loaded(module: str = MODULE_NAME) -> bool:
    """Check if the hid-playstation kernel module is loaded."""
    try:
        result = subprocess.run(["/usr/sbin/lsmod"], capture_output=True,
                                text=True, timeout=5, check=False)
        normalized = module.replace("-", "_")
        return any(line.split() and line.split()[0] == normalized
                   for line in result.stdout.splitlines())
    except Exception as e:
        logger.debug(f"Error checking module: {e}")
        return False


def load_module(module: str = MODULE_NAME) -> bool:
    """Load the hid-playstation kernel module."""
    if not isinstance(module, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", module):
        logger.error("Invalid kernel module name: %r", module)
        return False

    if is_module_loaded(module):
        logger.info(f"Module {module} already loaded")
        return True

    returncode, _stdout, stderr = _run_privileged("/usr/sbin/modprobe", module)
    if returncode == 0:
        logger.info(f"Module {module} loaded successfully")
        return True
    else:
        logger.error(f"Failed to load {module}: {stderr}")
        return False


def is_udev_rules_installed() -> bool:
    """Check the effective administrator/package udev rule without changing it."""
    if not UDEVS_RULES_SOURCE.is_file():
        return False

    # Package rules intentionally run after the legacy 99-ds4linux.rules name
    # so upgrades from the source installer can correct its permissions without
    # replacing the user's file. Only a same-named /etc override masks the new
    # vendor rule; check it before the package copy.
    for candidate in (UDEVS_RULES_PACKAGE_OVERRIDE, UDEVS_RULES_PACKAGE_DEST, UDEVS_RULES_DEST):
        if not candidate.exists() and not candidate.is_symlink():
            continue
        try:
            return candidate.read_bytes() == UDEVS_RULES_SOURCE.read_bytes()
        except OSError:
            return False
    return False


def install_udev_rules() -> tuple[bool, str]:
    """Install source/manual udev rules through Polkit and reload udev."""
    if not UDEVS_RULES_SOURCE.exists():
        logger.error(f"Rules source not found: {UDEVS_RULES_SOURCE}")
        return False, "Regras udev não encontradas no projeto"

    if is_udev_rules_installed():
        logger.info("udev rules already installed")
        return True, "Regras udev já instaladas"

    existing_admin_rule = next(
        (
            path
            for path in (UDEVS_RULES_PACKAGE_OVERRIDE, UDEVS_RULES_DEST)
            if path.exists() or path.is_symlink()
        ),
        None,
    )
    if existing_admin_rule is not None:
        logger.warning("Refusing to replace an existing administrator udev rule: %s", existing_admin_rule)
        return (
            False,
            f"Já existe uma regra local em {existing_admin_rule}. "
            "Ela tem prioridade sobre a regra do pacote e foi preservada; revise-a manualmente.",
        )

    commands = (
        (
            "/usr/bin/install",
            "-D",
            "-m",
            "0644",
            "--",
            str(UDEVS_RULES_SOURCE),
            str(UDEVS_RULES_DEST),
        ),
        ("/usr/bin/udevadm", "control", "--reload-rules"),
        ("/usr/bin/udevadm", "trigger"),
    )
    for command in commands:
        returncode, _stdout, stderr = _run_privileged(*command)
        if returncode != 0:
            logger.error("Failed to run privileged command %s: %s", command[0], stderr)
            return False, stderr or f"{command[0]} falhou (código {returncode})"

    logger.info("udev rules installed and reloaded successfully")
    return True, "Regras udev instaladas"


def scan_ds4_devices() -> list:
    """Scan for connected DS4 controllers via evdev."""
    try:
        import evdev
        devices = []
        for d in evdev.list_devices():
            dev = None
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
            finally:
                if dev is not None:
                    dev.close()
        return devices
    except Exception as e:
        logger.error(f"Error scanning devices: {e}")
        return []


def ensure_system_ready() -> tuple[bool, list]:
    """
    Read system readiness without requesting privileges or changing the host.
    Returns (rules_ready, list_of_messages).
    """
    messages = []

    # Diagnostics must not trigger administrative prompts or mutate the host.
    if is_module_loaded():
        messages.append("✅ Driver hid-playstation carregado")
    else:
        messages.append("ℹ️ Driver hid-playstation será carregado pelo kernel ao conectar um controle compatível")

    rules_configured = is_udev_rules_installed()
    if rules_configured:
        messages.append("✅ Regras udev instaladas")
    else:
        messages.append(
            "⚠️ Regras udev ausentes ou substituídas; instale o pacote da distribuição ou consulte a ajuda"
        )

    # Scan for controllers
    devices = scan_ds4_devices()
    if devices:
        for dev in devices:
            messages.append(f"✅ Controle detectado: {dev['name']} ({dev['path']})")
    else:
        messages.append("⚠️ Nenhum controle DS4 detectado — conecte o controle")

    all_ok = rules_configured and all("❌" not in m for m in messages)
    return all_ok, messages


def needs_setup() -> bool:
    """Report missing setup components for callers; never execute setup."""
    return not is_module_loaded() or not is_udev_rules_installed()


def discard_legacy_sudo_secret() -> bool:
    """Delete the obsolete plaintext secret without ever reading its contents."""
    try:
        if SUDO_PASS_FILE.exists():
            SUDO_PASS_FILE.unlink()
            logger.warning("Removed legacy plaintext sudo credential file")
            return True
    except Exception:
        logger.exception("Could not remove legacy sudo credential file")
    return False
