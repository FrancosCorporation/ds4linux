"""Locate application resources in source, system and virtualenv installs."""

from __future__ import annotations

import sysconfig
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    """Return an existing resource from the source tree or wheel data dir."""
    relative = Path(*parts)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("resource path must stay inside the application resource root")

    candidates = (
        _SOURCE_ROOT / relative,
        Path(sysconfig.get_path("data")) / "share" / "ds4linux" / relative,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
