"""Marketplace AI chat replies via Gemini (Messages page assistant)."""

from __future__ import annotations

import re
from typing import Any

from app.gemini_client import chat_text

SYSTEM_CHAT = """You are FreelanceHub Assistant — a helpful guide inside a freelance marketplace.
Help clients and freelancers with posting projects, writing proposals, messaging politely,
milestones, contracts, reviews, and platform how-tos.

Rules:
- Be concise, practical, and friendly (2–6 short paragraphs or bullet points max).
- Do not invent payment processor integrations, bank transfers, or real account balances.
- Do not claim you can publish projects, hire freelancers, send money, or change contracts yourself.
- Do not ask for passwords, API keys, or payment card numbers.
- If asked for something outside FreelanceHub help, politely redirect to marketplace topics.
"""


def _clean(value: Any, *, max_len: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len].strip()


def build_prompt(message: str, history: list[dict[str, str]] | None = None) -> str:
    lines: list[str] = []
    for item in (history or [])[-12:]:
        role = (item.get("role") or "").strip().lower()
        content = _clean(item.get("content"), max_len=1500)
        if not content:
            continue
        label = "Assistant" if role == "assistant" else "User"
        lines.append(f"{label}: {content}")
    lines.append(f"User: {_clean(message, max_len=2000)}")
    lines.append("Assistant:")
    return "\n".join(lines)


def generate_chat_reply(message: str, history: list[dict[str, str]] | None = None) -> str:
    prompt = build_prompt(message, history)
    reply = chat_text(user_prompt=prompt, system_prompt=SYSTEM_CHAT, temperature=0.55)
    cleaned = _clean(reply, max_len=4000)
    if not cleaned:
        return "I can help with FreelanceHub projects, proposals, and messaging. What do you need?"
    return cleaned
