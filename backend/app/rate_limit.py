"""Lightweight in-process rate limiting for sensitive routes.

For multi-worker / multi-host production, terminate rate limits at the reverse
proxy (nginx, Cloudflare, API gateway) or swap this for a Redis-backed limiter.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.config import get_settings

_lock = Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(request: Request, *, bucket: str, limit: int, window_seconds: int = 60) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled or limit <= 0:
        return
    key = f"{bucket}:{client_ip(request)}"
    now = time.monotonic()
    with _lock:
        q = _buckets[key]
        cutoff = now - window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again shortly.",
            )
        q.append(now)
