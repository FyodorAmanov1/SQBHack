from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from jamol.config import AppEntry, OpenSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str


def _app_by_id(apps: list[AppEntry], app_id: str) -> AppEntry | None:
    for a in apps:
        if a.id == app_id:
            return a
    return None


def execute_open(app_id: str, apps: list[AppEntry]) -> ActionResult:
    """Launch an allowlisted app by id. No other targets are accepted."""
    if sys.platform != "win32":
        return ActionResult(False, "Jamol actions are only supported on Windows.")

    entry = _app_by_id(apps, app_id)
    if entry is None:
        logger.warning("Unknown app id (not in config): %s", app_id)
        return ActionResult(False, f"Unknown action: {app_id}")

    spec: OpenSpec = entry.open
    try:
        if spec.kind == "shell_execute":
            return _open_shell_execute(spec.target, label=entry.id)
        if spec.kind == "startfile":
            return _open_startfile(spec.target, label=entry.id)
    except OSError as e:
        logger.exception("Failed to open %s", entry.id)
        return ActionResult(False, f"Could not start {entry.id}: {e}")

    return ActionResult(False, f"Unsupported open kind: {spec.kind}")


def _open_shell_execute(target: str, *, label: str) -> ActionResult:
    resolved = shutil.which(target)
    if not resolved and os.path.isfile(target):
        resolved = target
    if not resolved:
        logger.error("Executable not found on PATH: %s", target)
        return ActionResult(False, f"Program not found: {target}")

    logger.info("Starting [%s] -> %s", label, resolved)
    subprocess.Popen(
        [resolved],
        shell=False,
        cwd=None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return ActionResult(True, f"Opened {label}.")


def _open_startfile(target: str, *, label: str) -> ActionResult:
    logger.info("startfile [%s] -> %s", label, target)
    os.startfile(target)  # noqa: S606 - intentional allowlisted path from config
    return ActionResult(True, f"Opened {label}.")
