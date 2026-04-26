from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "uz_assistant.txt"
_client: Any = None


def _ollama_loopback_alternate(base: str) -> str | None:
    """Windows sometimes resolves localhost vs 127.0.0.1 differently; try both."""
    if "127.0.0.1" in base:
        return base.replace("127.0.0.1", "localhost", 1)
    if re.search(r"localhost", base, flags=re.I):
        return re.sub(r"localhost", "127.0.0.1", base, count=1, flags=re.I)
    return None


def _ollama_host_bases(settings: Settings) -> list[str]:
    primary = settings.ollama_host.rstrip("/")
    bases = [primary]
    alt = _ollama_loopback_alternate(primary)
    if alt and alt not in bases:
        bases.append(alt)
    return bases


def _ollama_connect_help(settings: Settings) -> str:
    host = settings.ollama_host.rstrip("/")
    return (
        f"Ollama serveriga ulanib bo‘lmadi ({host}). "
        "Ollama dasturini ishga tushiring (Windows: Ollama ilovasi yoki `ollama serve`), "
        "keyin brauzerda `http://127.0.0.1:11434/api/tags` ochilib-ochilmasligini tekshiring. "
        "Kerak bo‘lsa `.env` da OLLAMA_HOST ni `http://localhost:11434` qilib ko‘ring. "
        "OLLAMA_MODEL uchun `ollama list` da ko‘rinadigan nomni yozing."
    )


async def ping_ollama(settings: Settings) -> None:
    """Log a clear warning at startup if Ollama is not reachable."""
    timeout = httpx.Timeout(3.0, connect=2.0)
    bases = _ollama_host_bases(settings)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for i, base in enumerate(bases):
                url = base.rstrip("/") + "/api/tags"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except httpx.ConnectError:
                    if i + 1 < len(bases):
                        logger.info("Ollama tekshiruvi: %s — boshqa manzil sinanmoqda", url)
                        continue
                    raise
                else:
                    logger.info(
                        "Ollama ulanishi OK: %s, model=%s",
                        url,
                        settings.ollama_model,
                    )
                    return
    except (httpx.RequestError, httpx.HTTPError) as e:
        logger.warning(
            "Ollama tekshiruvi muvaffaqiyatsiz (%s): %s",
            bases[0] + "/api/tags",
            e,
        )
        logger.warning(_ollama_connect_help(settings))


async def _ollama_post_json(settings: Settings, path: str, payload: dict) -> dict:
    timeout = httpx.Timeout(settings.llm_timeout_seconds)
    bases = _ollama_host_bases(settings)
    last_connect: httpx.ConnectError | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, base in enumerate(bases):
            url = base.rstrip("/") + path
            try:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                return r.json()
            except httpx.ConnectError as e:
                last_connect = e
                if i + 1 < len(bases):
                    logger.info("Ollama ulanmadi (%s), boshqa loopback manzil sinanmoqda…", url)
                    continue
                raise RuntimeError(_ollama_connect_help(settings)) from last_connect
            except httpx.TimeoutException as e:
                raise RuntimeError(
                    f"Ollama javob bermadi (timeout). Server: {settings.ollama_host.rstrip('/')}"
                ) from e
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"Ollama HTTP {e.response.status_code}: {e.response.text[:500]}"
                ) from e
    raise AssertionError("ollama POST: expected return or raise inside loop")


def load_system_prompt() -> str:
    if _PROMPT_PATH.is_file():
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return (
        "Sen o‘zbek tilida yordam beradigan assistentsan. "
        "Javoblaring qisqa va tabiiy bo‘lsin."
    )


def init_client(settings: Settings) -> None:
    global _client
    if settings.llm_provider != "openai":
        _client = None
        return
    if _client is not None:
        return
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY bo‘sh — LLM ishlamaydi. Kalitni `.env` ga yozing yoki "
            "`LLM_PROVIDER=ollama` qiling."
        )
        _client = None
        return
    try:
        from openai import AsyncOpenAI
    except ModuleNotFoundError:
        logger.warning(
            "Paket `openai` topilmadi. `pip install openai` yoki "
            "`LLM_PROVIDER=ollama` qiling. OpenAI rejimi birinchi so‘rovda xato beradi."
        )
        _client = None
        return
    _client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.openai_base_url,
        timeout=settings.llm_timeout_seconds,
    )


def trim_llm_history(
    history: list[dict[str, str]],
    max_messages: int,
) -> None:
    """Drop oldest entries so len(history) <= max_messages (in-place)."""
    if max_messages <= 0:
        history.clear()
        return
    while len(history) > max_messages:
        history.pop(0)


def build_messages_with_history(
    system: str,
    history: list[dict[str, str]],
    user_text: str,
) -> list[dict[str, str]]:
    """OpenAI-style messages: system, prior user/assistant turns, then current user."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in history:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        msgs.append({"role": cast(str, role), "content": content})
    msgs.append({"role": "user", "content": user_text.strip()})
    return msgs


async def generate_reply_with_history(
    user_text: str,
    history: list[dict[str, str]],
    settings: Settings,
) -> str:
    """Voice pipeline: multi-turn chat using prior user/assistant pairs only."""
    system = load_system_prompt()
    messages = build_messages_with_history(system, history, user_text)
    return await generate_from_messages(messages, settings)


async def generate_reply(
    user_text: str,
    settings: Settings,
) -> str:
    system = load_system_prompt()
    if settings.llm_provider == "openai":
        return await _openai_chat(system, user_text, settings)
    return await _ollama_chat(system, user_text, settings)


async def _openai_chat(system: str, user_text: str, settings: Settings) -> str:
    if _client is None:
        init_client(settings)
    if _client is None:
        raise RuntimeError(
            "OpenAI rejimi ishlamayapti: `.env` da OPENAI_API_KEY, `pip install openai`, "
            "yoki `LLM_PROVIDER=ollama`."
        )
    create_kw: dict = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.6,
    }
    if settings.openai_max_tokens > 0:
        create_kw["max_tokens"] = settings.openai_max_tokens
    resp = await _client.chat.completions.create(**create_kw)
    choice = resp.choices[0]
    content = choice.message.content or ""
    return content.strip()


async def _ollama_chat(system: str, user_text: str, settings: Settings) -> str:
    payload: dict = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }
    if settings.ollama_num_predict > 0:
        payload["options"] = {"num_predict": settings.ollama_num_predict}
    data = await _ollama_post_json(settings, "/api/chat", payload)
    msg = data.get("message") or {}
    content = msg.get("content", "")
    if not content and isinstance(data.get("response"), str):
        content = data["response"]
    return str(content).strip()


async def generate_from_messages(
    messages: list[dict[str, str]],
    settings: Settings,
) -> str:
    """REST helper: messages must be OpenAI-style role/content."""
    if settings.llm_provider == "openai":
        if _client is None:
            init_client(settings)
        if _client is None:
            raise RuntimeError(
                "OpenAI rejimi ishlamayapti: `.env` da OPENAI_API_KEY, `pip install openai`, "
                "yoki `LLM_PROVIDER=ollama`."
            )
        create_kw = {
            "model": settings.openai_model,
            "messages": messages,
            "temperature": 0.6,
        }
        if settings.openai_max_tokens > 0:
            create_kw["max_tokens"] = settings.openai_max_tokens
        resp = await _client.chat.completions.create(**create_kw)
        return (resp.choices[0].message.content or "").strip()
    return await _ollama_raw_messages(messages, settings)


async def _ollama_raw_messages(messages: list[dict[str, str]], settings: Settings) -> str:
    if not messages:
        return ""
    payload: dict = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": messages,
    }
    if settings.ollama_num_predict > 0:
        payload["options"] = {"num_predict": settings.ollama_num_predict}
    data = await _ollama_post_json(settings, "/api/chat", payload)
    msg = data.get("message") or {}
    content = msg.get("content", "")
    if not content and isinstance(data.get("response"), str):
        content = data["response"]
    return str(content).strip()


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

OPERATOR_ADVICE_SYSTEM = """Sen bank call-markazidagi operator uchun maslahatchisan. Javobing FAQAT \
valid JSON bo‘lishi kerak, boshqa matn yo‘q. \
Format (o‘zbek lotinida title va content):
{"panels":[
  {"title":"...","content":"..."},
  {"title":"...","content":"..."},
  {"title":"...","content":"..."}
]}
Uchta panel:
1) Darhol qilish — operatorning keyingi amali.
2) Mijoz bilan muloqot — aytish mumkin bo‘lgan tabiiy iboralar.
3) Xavf va ruxsat — cheklovlar, identifikatsiya, shubhali operatsiyalar.

Muhim: transkriptda kredit, karta, qo‘shimcha xizmat yoki mahsulot turi tilga olinyapti, lekin \
mijoz kontekstidagi JSONda shu tafsilotlar bo‘lmasa ham, umumiy bank amaliyoti, ehtiyotkorlik \
va yuridik cheklovlar bo‘yicha qisqa maslahat ber. Tafsilotlar noma’lum bo‘lsa, buni aytib, \
qanday aniq so‘roq (masalan, shartnoma, ID, limit, muddati) yoki qaysi tizimda tekshirish \
kerakligini tavsiya et.

Javoblar qisqa, aniq, xavfsizlik va mijozga hurmat bilan. Agar transkript bo‘sh bo‘lsa, \
umumiy ehtiyotkorlik maslahatlari ber."""


def _parse_operator_advice_json(raw: str) -> list[dict[str, str]]:
    text = (raw or "").strip()
    m = _JSON_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    data = json.loads(text)
    panels = data.get("panels")
    if not isinstance(panels, list):
        raise ValueError("JSONda 'panels' ro‘yxati kutilgan")
    out: list[dict[str, str]] = []
    for item in panels[:3]:
        if not isinstance(item, dict):
            continue
        t = str(item.get("title") or "").strip()
        c = str(item.get("content") or "").strip()
        if t or c:
            out.append({"title": t or "—", "content": c or "—"})
    while len(out) < 3:
        out.append(
            {
                "title": "Ma’lumot yetarli emas",
                "content": "Transkriptni yangilang yoki mijoz ma’lumotini tekshiring.",
            }
        )
    return out[:3]


async def generate_operator_advice_panels(
    client_context: str,
    transcript: str,
    settings: Settings,
) -> list[dict[str, str]]:
    """Return three {title, content} dicts from the LLM as JSON."""
    user = (
        "Mijoz konteksti (JSON yoki qisqacha) — barcha mahsulotlar ro‘yxati bo‘lmasligi mumkin; "
        "transkriptdagi tahlillar uchun transkript ham muhim:\n"
        f"{client_context}\n\n"
        "So‘nggi suhbat transkripti (operator va mijoz):\n"
        f"{(transcript or '').strip()[:12000]}\n\n"
        "Eslatma: suhbatda tilga olingan, lekin yuqoridagi JSONda ko‘rinmaydigan kredit, karta yoki "
        "xizmat bo‘yicha ham umumiy maslahat bering; kerakli tekshiruvlarni aytib o‘ting."
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": OPERATOR_ADVICE_SYSTEM},
        {"role": "user", "content": user},
    ]
    raw = await generate_from_messages(messages, settings)
    try:
        return _parse_operator_advice_json(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("operator advice JSON parse failed: %s — raw=%s", e, raw[:500])
        raise RuntimeError(
            "LLM javobi JSON formatida emas. Modelni qayta urinib ko‘ring."
        ) from e
