"""Server-side Gemini generative client (API key never leaves the backend)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import HTTPException, status

from app.config import Settings, get_settings

logger = logging.getLogger("freelancehub.ai")

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - dependency missing in broken installs
    genai = None
    genai_types = None

SYSTEM_BRIEF = """You turn a client's rough idea into a clear freelance project brief.
Return ONLY a JSON object with these keys:
- title (string, concise, under 80 characters)
- category (one of: Web Dev, Design, Writing, Mobile, Marketing, Data/AI)
- description (string, 2-4 short paragraphs covering scope, deliverables, and requirements)
- skills (array of 3-8 short skill strings)
- experience_level (one of: Entry level, Intermediate, Expert)
- budget_min (number, USD)
- budget_max (number, USD, >= budget_min)
- estimated_duration (short string like "2-4 weeks")

Do not invent payment processors, real personal data, or that the job is already posted.
Keep budgets realistic for a typical freelance marketplace.
"""

_SECRET_PATTERNS = (
    re.compile(r"AIza[\w-]{10,}", re.I),
    re.compile(r"AQ\.[\w-]{10,}", re.I),
    re.compile(r"Bearer\s+\S+", re.I),
    re.compile(r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[\w.-]+", re.I),
)


def gemini_configured(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool((cfg.gemini_api_key or "").strip())


def _redact(text: str) -> str:
    cleaned = text or ""
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned


def _safe_detail(message: str) -> str:
    return _redact(message)


def _require_client(settings: Settings | None = None):
    cfg = settings or get_settings()
    api_key = (cfg.gemini_api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI assistant is not configured. Add GEMINI_API_KEY on the server.",
        )
    if genai is None or genai_types is None:
        logger.error("google-genai package is not installed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI assistant is not available on this server.",
        )
    timeout_ms = max(1, int(float(cfg.gemini_timeout_seconds) * 1000))
    model = (cfg.gemini_model or "gemini-3.6-flash").strip()
    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=timeout_ms),
    )
    return client, model


def _map_gemini_error(exc: Exception) -> HTTPException:
    message = _safe_detail(str(exc))
    lower = message.lower()
    logger.warning("Gemini request failed: %s", message[:300])
    if "timeout" in lower or "timed out" in lower:
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI assistant timed out. Try again in a moment.",
        )
    if any(token in lower for token in ("429", "quota", "rate limit", "resource_exhausted")):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI assistant is temporarily rate-limited. Try again shortly.",
        )
    if any(token in lower for token in ("401", "403", "api key", "permission", "unauthenticated")):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI assistant failed. Check the server Gemini configuration.",
        )
    if any(token in lower for token in ("404", "not_found", "no longer available", "is not found")):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model is unavailable. Set GEMINI_MODEL=gemini-3.6-flash on the server.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="AI assistant is temporarily unavailable.",
    )


def _response_text(response: Any) -> str:
    content = getattr(response, "text", None)
    if not content:
        candidates = getattr(response, "candidates", None) or []
        parts: list[str] = []
        for candidate in candidates:
            content_obj = getattr(candidate, "content", None)
            for part in getattr(content_obj, "parts", None) or []:
                text = getattr(part, "text", None)
                if text:
                    parts.append(text)
        content = "".join(parts)
    text = str(content or "").strip()
    if not text:
        raise ValueError("empty model response")
    return text


def chat_text(
    *,
    user_prompt: str,
    system_prompt: str,
    settings: Settings | None = None,
    temperature: float = 0.6,
) -> str:
    """Call Gemini and return plain text. Never logs or returns the API key."""
    client, model = _require_client(settings)
    try:
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _map_gemini_error(exc) from None

    try:
        return _response_text(response)
    except ValueError:
        logger.warning("Gemini returned an empty text payload")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI assistant returned an invalid response.",
        ) from None


def chat_json(
    *,
    user_prompt: str,
    system_prompt: str = SYSTEM_BRIEF,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Call Gemini and parse a JSON object response. Never logs or returns the API key."""
    client, model = _require_client(settings)

    try:
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — map provider errors to safe HTTP responses
        raise _map_gemini_error(exc) from None

    try:
        data = json.loads(_response_text(response))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Gemini returned an invalid JSON payload")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI assistant returned an invalid response.",
        ) from None

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI assistant returned an invalid response.",
        )
    return data
