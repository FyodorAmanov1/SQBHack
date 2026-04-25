from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

logger = logging.getLogger(__name__)

OpenKind = Literal["shell_execute", "startfile"]


@dataclass(frozen=True)
class OpenSpec:
    kind: OpenKind
    target: str


@dataclass(frozen=True)
class AppEntry:
    id: str
    phrases: tuple[str, ...]
    open: OpenSpec


def _parse_open(raw: dict[str, Any]) -> OpenSpec:
    kind = raw.get("kind")
    target = raw.get("target")
    if kind not in ("shell_execute", "startfile"):
        raise ValueError(f"Invalid open.kind: {kind!r}")
    if not target or not isinstance(target, str):
        raise ValueError("open.target must be a non-empty string")
    return OpenSpec(kind=kind, target=target.strip())


def load_apps_yaml(path: Path) -> list[AppEntry]:
    if not path.is_file():
        raise FileNotFoundError(f"Config not found: {path}")

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "apps" not in data:
        raise ValueError("Config must be a mapping with an 'apps' key")

    apps_raw = data["apps"]
    if not isinstance(apps_raw, list):
        raise ValueError("'apps' must be a list")

    out: list[AppEntry] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(apps_raw):
        if not isinstance(item, dict):
            raise ValueError(f"apps[{i}] must be a mapping")
        aid = item.get("id")
        if not aid or not isinstance(aid, str):
            raise ValueError(f"apps[{i}].id must be a non-empty string")
        if aid in seen_ids:
            raise ValueError(f"Duplicate app id: {aid!r}")
        seen_ids.add(aid)

        phrases = item.get("phrases")
        if not isinstance(phrases, list) or not phrases:
            raise ValueError(f"apps[{i}].phrases must be a non-empty list")
        norm_phrases: list[str] = []
        for j, p in enumerate(phrases):
            if not isinstance(p, str) or not p.strip():
                raise ValueError(f"apps[{i}].phrases[{j}] must be a non-empty string")
            norm_phrases.append(p.strip())

        open_raw = item.get("open")
        if not isinstance(open_raw, dict):
            raise ValueError(f"apps[{i}].open must be a mapping")
        open_spec = _parse_open(open_raw)

        out.append(
            AppEntry(
                id=aid,
                phrases=tuple(norm_phrases),
                open=open_spec,
            )
        )

    logger.info("Loaded %d app(s) from %s", len(out), path)
    return out


def default_config_path() -> Path:
    """jamol/config/apps.yaml next to the project root (jamol/ folder)."""
    here = Path(__file__).resolve()
    jamol_root = here.parents[2]
    return jamol_root / "config" / "apps.yaml"


def default_example_config_path() -> Path:
    here = Path(__file__).resolve()
    jamol_root = here.parents[2]
    return jamol_root / "config" / "apps.example.yaml"


def resolve_config_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env_path = os.environ.get("JAMOL_CONFIG", "").strip()
    if env_path:
        return Path(env_path)
    primary = default_config_path()
    if primary.is_file():
        return primary
    example = default_example_config_path()
    if example.is_file():
        logger.warning(
            "Using %s - copy to config/apps.yaml to customize.",
            example.name,
        )
        return example
    raise FileNotFoundError(
        f"No config found. Expected {primary} or {example}. "
        "Copy config/apps.example.yaml to config/apps.yaml."
    )
