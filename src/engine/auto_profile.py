from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)

AUTO_PROFILE_FILE = Path.home() / ".config" / "ds4linux" / "auto_profiles.json"

DEFAULT_POLL_INTERVAL_MS = 1000


@dataclass
class AutoProfileRule:
    """A single auto-profile rule, modeled after DS4Windows AutoProfileEntity.

    A rule matches when BOTH the foreground process name contains `program`
    AND the window title contains `title` (if either field is empty, that
    condition is ignored).
    """
    name: str = ""
    program: str = ""
    title: str = ""
    profile: str = ""
    enabled: bool = True

    def is_match(self, process_name: str, window_title: str) -> bool:
        if not self.enabled:
            return False
        proc = (process_name or "").lower()
        title = (window_title or "").lower()
        if self.program and self.program.lower() not in proc:
            return False
        if self.title and self.title.lower() not in title:
            return False
        return True


class AutoProfileManager(QObject):
    """DS4Windows-style auto profile switcher for Linux/X11.

    Polls the foreground window (via `xprop`/`/proc`) and applies the profile
    bound to the active game/app. When no rule matches, reverts to the default
    profile (DS4Windows "AutoProfileRevertDefaultProfile" behavior).
    """

    rules_changed = Signal()
    log_message = Signal(str)
    active_profile_changed = Signal(str)  # profile name currently active
    detection_state_changed = Signal(str)  # human-readable foreground info
    profile_apply_requested = Signal(str)  # profile to apply to all controllers

    def __init__(self, profile_manager=None, parent: QObject | None = None):
        super().__init__(parent)
        self._profile_manager = profile_manager
        self._rules: List[AutoProfileRule] = []
        self._default_profile: str = ""
        self._revert_to_default: bool = True
        self._enabled: bool = True
        self._current_profile: Optional[str] = None
        self._last_key: Optional[tuple] = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)
        self._timer.setInterval(DEFAULT_POLL_INTERVAL_MS)

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _file(self) -> Path:
        return AUTO_PROFILE_FILE

    def _load(self):
        try:
            if self._file().exists():
                with open(self._file(), "r") as f:
                    data = json.load(f)
                self._enabled = bool(data.get("enabled", True))
                self._revert_to_default = bool(data.get("revert_to_default", True))
                self._default_profile = data.get("default_profile", "") or ""
                self._rules = [
                    AutoProfileRule(**r) for r in data.get("rules", [])
                ]
                logger.info(f"Loaded {len(self._rules)} auto-profile rule(s)")
        except Exception as e:
            logger.error(f"Failed to load auto-profiles: {e}")

    def save(self):
        try:
            self._file().parent.mkdir(parents=True, exist_ok=True)
            data = {
                "enabled": self._enabled,
                "revert_to_default": self._revert_to_default,
                "default_profile": self._default_profile,
                "rules": [asdict(r) for r in self._rules],
            }
            with open(self._file(), "w") as f:
                json.dump(data, f, indent=2)
            self.rules_changed.emit()
        except Exception as e:
            logger.error(f"Failed to save auto-profiles: {e}")

    # ------------------------------------------------------------------
    # Rule CRUD
    # ------------------------------------------------------------------
    def rules(self) -> List[AutoProfileRule]:
        return list(self._rules)

    def add_rule(self, rule: AutoProfileRule):
        self._rules.append(rule)
        self.save()

    def update_rule(self, index: int, rule: AutoProfileRule):
        if 0 <= index < len(self._rules):
            self._rules[index] = rule
            self.save()

    def remove_rule(self, index: int):
        if 0 <= index < len(self._rules):
            del self._rules[index]
            self.save()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.save()
        if enabled:
            self._timer.start()
            self.check_now()
        else:
            self._timer.stop()
            self._current_profile = None
            self._last_key = None

    def is_enabled(self) -> bool:
        return self._enabled

    def set_default_profile(self, name: str):
        self._default_profile = name
        self.save()

    def get_default_profile(self) -> str:
        return self._default_profile

    def set_revert_to_default(self, revert: bool):
        self._revert_to_default = revert
        self.save()

    def get_revert_to_default(self) -> bool:
        return self._revert_to_default

    # ------------------------------------------------------------------
    # Foreground window detection (X11)
    # ------------------------------------------------------------------
    def get_foreground_info(self) -> Optional[Tuple[str, str]]:
        """Return (process_name, window_title) of the active window or None."""
        if os.environ.get("DISPLAY"):
            info = self._get_foreground_x11()
            if info:
                return info
        # Wayland / unknown: fall back to process scan for known game binaries
        return self._get_foreground_by_process()

    def _get_foreground_x11(self) -> Optional[Tuple[str, str]]:
        try:
            out = subprocess.run(
                ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                capture_output=True, text=True, timeout=1,
            ).stdout.strip()
        except Exception:
            return None

        m = re.search(r"window id # (0x[0-9a-fA-F]+)", out)
        if not m:
            return None
        win = m.group(1)

        title = ""
        try:
            t_out = subprocess.run(
                ["xprop", "-id", win, "_NET_WM_NAME"],
                capture_output=True, text=True, timeout=1,
            ).stdout
            title = self._parse_xprop_string(t_out)
        except Exception:
            pass

        proc = ""
        try:
            p_out = subprocess.run(
                ["xprop", "-id", win, "_NET_WM_PID"],
                capture_output=True, text=True, timeout=1,
            ).stdout
            m2 = re.search(r"=\s*(\d+)", p_out)
            if m2:
                proc = self._proc_name_from_pid(int(m2.group(1)))
        except Exception:
            pass

        if not proc and not title:
            return None
        return proc, title

    @staticmethod
    def _parse_xprop_string(xprop_out: str) -> str:
        m = re.search(r"=\s*\"(.*)\"\s*$", xprop_out, re.DOTALL)
        if m:
            return m.group(1)
        m = re.search(r"=\s*([^\s].*?)\s*$", xprop_out, re.DOTALL)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _proc_name_from_pid(pid: int) -> str:
        try:
            with open(f"/proc/{pid}/comm", "r") as f:
                return f.read().strip()
        except Exception:
            pass
        try:
            exe = Path(f"/proc/{pid}/exe").resolve()
            if exe.exists():
                return exe.name
        except Exception:
            pass
        return ""

    def _get_foreground_by_process(self) -> Optional[Tuple[str, str]]:
        """Fallback for Wayland: scan running processes for known game apps."""
        known = ("wine", "proton", "heroic", "lutris", "steam", "godot",
                 "unity", "game", "eluauncher", "hydra", "playnite")
        try:
            out = subprocess.run(
                ["pgrep", "-f", "-l", ".*"],
                capture_output=True, text=True, timeout=1,
            ).stdout
        except Exception:
            return None
        for line in out.splitlines():
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue
            name = parts[1].lower()
            if any(k in name for k in known):
                return name, name
        return None

    # ------------------------------------------------------------------
    # Matching / profile switching
    # ------------------------------------------------------------------
    def check_now(self):
        if not self._enabled:
            return

        info = self.get_foreground_info()
        if not info:
            self.detection_state_changed.emit("Nenhuma janela ativa detectada")
            return
        process_name, window_title = info
        self.detection_state_changed.emit(f"{process_name} — {window_title}")

        key = (process_name, window_title)
        if key == self._last_key:
            return
        self._last_key = key

        profile_name = self._match_rule(process_name, window_title)
        if profile_name is None and self._revert_to_default:
            profile_name = self._default_profile

        if profile_name and profile_name != self._current_profile:
            self._current_profile = profile_name
            self.log_message.emit(
                f"[Auto Profile] Ativo: \"{profile_name}\" (jogo: {window_title or process_name})"
            )
            self.active_profile_changed.emit(profile_name)
            self.profile_apply_requested.emit(profile_name)

    def _match_rule(self, process_name: str, window_title: str) -> Optional[str]:
        for rule in self._rules:
            if rule.is_match(process_name, window_title):
                return rule.profile
        return None

    def start(self):
        if self._enabled:
            self._timer.start()
            self.check_now()

    def stop(self):
        self._timer.stop()
