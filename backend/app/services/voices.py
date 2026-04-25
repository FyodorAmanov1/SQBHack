from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

# Audio extensions supported by soundfile (same as typical TTS ref clips).
_VOICE_EXTENSIONS = frozenset({".wav", ".flac", ".ogg", ".opus"})

_backend_dir = Path(__file__).resolve().parents[2]
_repo_root = _backend_dir.parent


@dataclass(frozen=True)
class VoiceEntry:
    """A cloneable reference clip under the voice scan directory."""

    id: str
    label: str
    filename: str


_catalog: list[VoiceEntry] = []
_by_id: dict[str, VoiceEntry] = {}


def repo_root() -> Path:
    return _repo_root


def _scan_root(settings: "Settings") -> Path:
    raw = (settings.tts_voices_scan_dir or "myVoice").strip() or "myVoice"
    return (_repo_root / raw).resolve()


def _is_under(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def label_for_voice_path(path_under_scan: Path) -> str:
    """Human-readable label from path relative to the scan root."""
    if len(path_under_scan.parts) <= 1:
        return path_under_scan.stem
    parent = path_under_scan.parent.as_posix().replace("/", " / ")
    return f"{parent} — {path_under_scan.stem}"


def refresh_voice_catalog(settings: "Settings", *, log: bool = True) -> int:
    """Scan `tts_voices_scan_dir` under repo root; populate in-memory catalog."""
    global _catalog, _by_id
    root = _scan_root(settings)
    if not root.is_dir():
        if log:
            logger.info(
                "Voice catalog: directory not found (%s); no cloned speakers.",
                root,
            )
        _catalog = []
        _by_id = {}
        return 0

    entries: list[VoiceEntry] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _VOICE_EXTENSIONS:
            continue
        resolved = path.resolve()
        if not _is_under(root, resolved):
            continue
        try:
            rel_repo = resolved.relative_to(_repo_root.resolve())
        except ValueError:
            continue
        rel_posix = rel_repo.as_posix()
        under_scan = path.relative_to(root)
        label = label_for_voice_path(under_scan)
        entries.append(
            VoiceEntry(
                id=rel_posix,
                label=label,
                filename=path.name,
            )
        )

    entries.sort(key=lambda e: (e.label.casefold(), e.id.casefold()))
    _catalog = entries
    _by_id = {e.id: e for e in entries}
    msg = "Voice catalog: %d reference clip(s) in %s" % (len(entries), root)
    if log:
        logger.info(msg)
    else:
        logger.debug(msg)
    return len(entries)


def voice_catalog() -> list[VoiceEntry]:
    return list(_catalog)


def optional_ref_text_for_audio(rel_id: str) -> str | None:
    """If a `.txt` exists next to the audio (same stem), return its text; else None."""
    audio = _repo_root / rel_id
    if not audio.is_file():
        return None
    sidecar = audio.with_suffix(".txt")
    if not sidecar.is_file():
        return None
    try:
        text = sidecar.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Could not read ref text sidecar: %s", sidecar)
        return None
    return text if text else None


def get_voice(rel_id: str | None) -> VoiceEntry | None:
    if not rel_id or not rel_id.strip():
        return None
    key = rel_id.strip().replace("\\", "/")
    hit = _by_id.get(key)
    if hit is None:
        return None
    audio = _repo_root / hit.id
    if not audio.is_file():
        return None
    return hit


def default_speaker_id(settings: "Settings") -> str | None:
    """Prefer env ref path if it matches catalog; else first catalog entry."""
    if not _catalog:
        return None
    env_path = (settings.tts_ref_audio_path or "").strip().replace("\\", "/")
    if env_path and env_path in _by_id:
        return env_path
    return _catalog[0].id
