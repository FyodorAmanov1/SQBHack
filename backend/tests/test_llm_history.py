"""LLM history trimming and message assembly for voice."""

from app.config import Settings
from app.services.llm import (
    build_messages_with_history,
    trim_llm_history,
)


def test_trim_llm_history_drops_oldest():
    h: list[dict[str, str]] = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
    ]
    trim_llm_history(h, max_messages=2)
    assert h == [
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
    ]


def test_trim_llm_history_clear_when_zero():
    h = [{"role": "user", "content": "x"}]
    trim_llm_history(h, max_messages=0)
    assert h == []


def test_build_messages_with_history():
    system = "Sys"
    hist: list[dict[str, str]] = [
        {"role": "user", "content": "old q"},
        {"role": "assistant", "content": "old a"},
        {"role": "bogus", "content": "skip"},
        {"role": "user", "content": ""},
    ]
    msgs = build_messages_with_history(system, hist, "  new q  ")
    assert msgs == [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "old q"},
        {"role": "assistant", "content": "old a"},
        {"role": "user", "content": "new q"},
    ]


def test_settings_llm_history_default():
    s = Settings()
    assert s.llm_history_max_messages == 24
    assert s.api_shared_secret == ""
