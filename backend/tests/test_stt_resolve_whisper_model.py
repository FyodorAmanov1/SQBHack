"""Tests for :func:`app.services.stt._resolve_whisper_model` — the three dispatch paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.services import stt as stt_mod


def test_official_size_passes_through() -> None:
    """Known whisper sizes must be returned verbatim (no conversion)."""
    for size in ("tiny", "base", "small", "medium", "large-v3", "distil-large-v3"):
        assert stt_mod._resolve_whisper_model(Settings(stt_model_size=size)) == size


def test_unknown_short_name_falls_back_to_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-standard short name without '/' and no path shape is handed to faster-whisper as-is."""
    # Simulate absence of any matching directory on disk.
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert stt_mod._resolve_whisper_model(Settings(stt_model_size="foobar")) == "foobar"


def test_local_ct2_dir_returned_as_absolute_path(tmp_path: Path) -> None:
    """A directory containing ``model.bin`` is treated as a pre-built CT2 model."""
    model_dir = tmp_path / "uzbek_ct2"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"\x00")

    resolved = stt_mod._resolve_whisper_model(
        Settings(stt_model_size=str(model_dir))
    )
    assert Path(resolved) == model_dir.resolve()


def test_local_existing_dir_without_model_bin_raises(tmp_path: Path) -> None:
    """Misconfigured local paths must be reported clearly, not silently fall through."""
    broken = tmp_path / "broken"
    broken.mkdir()
    with pytest.raises(RuntimeError, match="not a CT2 model dir"):
        stt_mod._resolve_whisper_model(Settings(stt_model_size=str(broken)))


def test_hf_repo_id_returns_cached_ct2_without_reconversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the cache already has ``<cache>/<owner__name>/model.bin``, skip conversion."""
    cache = tmp_path / "ct2_cache"
    repo = "islomov/rubaistt_v2_medium"
    target = cache / "islomov__rubaistt_v2_medium"
    target.mkdir(parents=True)
    (target / "model.bin").write_bytes(b"\x00")

    def _boom(*args, **kwargs):
        raise AssertionError("Must not re-convert when cached CT2 exists")

    monkeypatch.setattr(stt_mod, "_convert_hf_whisper_to_ct2", _boom)

    settings = Settings(stt_model_size=repo, stt_model_cache_dir=str(cache))
    resolved = stt_mod._resolve_whisper_model(settings)
    assert Path(resolved) == target.resolve()


def test_hf_repo_id_triggers_conversion_when_cache_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First-time HF repo resolution must call the converter with the cache path."""
    cache = tmp_path / "ct2_cache"
    repo = "islomov/rubaistt_v2_medium"
    expected_target = cache / "islomov__rubaistt_v2_medium"

    calls: list[tuple[str, Path, str]] = []

    def _fake_convert(repo_id: str, target: Path, *, quantization: str) -> Path:
        calls.append((repo_id, target, quantization))
        target.mkdir(parents=True, exist_ok=True)
        (target / "model.bin").write_bytes(b"\x00")
        return target

    monkeypatch.setattr(stt_mod, "_convert_hf_whisper_to_ct2", _fake_convert)

    settings = Settings(
        stt_model_size=repo,
        stt_model_cache_dir=str(cache),
        stt_ct2_quantization="int8_float16",
    )
    resolved = stt_mod._resolve_whisper_model(settings)

    assert calls == [(repo, expected_target, "int8_float16")]
    assert Path(resolved) == expected_target.resolve()


def test_safe_repo_dirname_is_slash_safe() -> None:
    assert stt_mod._safe_repo_dirname("islomov/rubaistt_v2_medium") == (
        "islomov__rubaistt_v2_medium"
    )
    assert stt_mod._safe_repo_dirname("a\\b") == "a__b"
