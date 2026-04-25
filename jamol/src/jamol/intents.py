from __future__ import annotations

import re
import unicodedata

from jamol.config import AppEntry

_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for matching."""
    t = text.strip().lower()
    t = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", t)
        if not unicodedata.combining(ch)
    )
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = _WS_RE.sub(" ", t).strip()
    return t


def match_intent(user_text: str, apps: list[AppEntry]) -> str | None:
    """
    Return app id for the best matching phrase, or None.
    Prefers longer phrase matches to reduce ambiguity.
    """
    nu = normalize(user_text)
    if not nu:
        return None

    candidates: list[tuple[int, str]] = []
    for app in apps:
        for phrase in app.phrases:
            pn = normalize(phrase)
            if not pn:
                continue
            if pn == nu or pn in nu:
                candidates.append((len(pn), app.id))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][1]
