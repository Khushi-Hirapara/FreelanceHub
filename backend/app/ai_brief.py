"""Validate and sanitize AI project-brief suggestions before they reach the client."""

from __future__ import annotations

import re
from typing import Any

from app.gemini_client import chat_json
from app.schemas import ProjectBriefOut

ALLOWED_CATEGORIES = ("Web Dev", "Design", "Writing", "Mobile", "Marketing", "Data/AI")
ALLOWED_EXPERIENCE = ("Entry level", "Intermediate", "Expert")

CATEGORY_ALIASES = {
    "web": "Web Dev",
    "web development": "Web Dev",
    "webdev": "Web Dev",
    "website": "Web Dev",
    "development": "Web Dev",
    "programming": "Web Dev",
    "design": "Design",
    "ui": "Design",
    "ux": "Design",
    "graphic": "Design",
    "writing": "Writing",
    "content": "Writing",
    "copywriting": "Writing",
    "mobile": "Mobile",
    "ios": "Mobile",
    "android": "Mobile",
    "app": "Mobile",
    "marketing": "Marketing",
    "seo": "Marketing",
    "data": "Data/AI",
    "ai": "Data/AI",
    "machine learning": "Data/AI",
    "data/ai": "Data/AI",
    "data science": "Data/AI",
}

EXPERIENCE_ALIASES = {
    "entry": "Entry level",
    "entry level": "Entry level",
    "junior": "Entry level",
    "beginner": "Entry level",
    "intermediate": "Intermediate",
    "mid": "Intermediate",
    "mid-level": "Intermediate",
    "expert": "Expert",
    "senior": "Expert",
    "advanced": "Expert",
}


def _clean_text(value: Any, *, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("\x00", "")
    return text[:max_len]


def _map_category(value: Any) -> str:
    raw = _clean_text(value, max_len=80)
    for allowed in ALLOWED_CATEGORIES:
        if raw.lower() == allowed.lower():
            return allowed
    alias = CATEGORY_ALIASES.get(raw.lower())
    if alias:
        return alias
    lowered = raw.lower()
    for key, mapped in CATEGORY_ALIASES.items():
        if key in lowered:
            return mapped
    return "Web Dev"


def _map_experience(value: Any) -> str:
    raw = _clean_text(value, max_len=40)
    for allowed in ALLOWED_EXPERIENCE:
        if raw.lower() == allowed.lower():
            return allowed
    return EXPERIENCE_ALIASES.get(raw.lower(), "Intermediate")


def _clean_skills(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;/|]+", value)
    elif isinstance(value, list):
        parts = value
    else:
        parts = [value]
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        skill = _clean_text(part, max_len=40)
        if len(skill) < 2:
            continue
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(skill)
        if len(cleaned) >= 10:
            break
    return cleaned


def _as_budget(value: Any, default: float) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = default
    if amount != amount:  # NaN
        amount = default
    return round(max(50.0, min(amount, 250_000.0)), 2)


def sanitize_brief(raw: dict[str, Any], rough_description: str) -> ProjectBriefOut:
    title = _clean_text(raw.get("title"), max_len=200)
    if len(title) < 5:
        snippet = _clean_text(rough_description, max_len=70)
        title = snippet[:67] + "..." if len(snippet) > 70 else (snippet or "New freelance project")
        if len(title) < 5:
            title = "New freelance project"

    description = str(raw.get("description") or "").replace("\x00", "").strip()
    description = re.sub(r"[ \t]+\n", "\n", description)
    description = re.sub(r"\n{3,}", "\n\n", description)
    description = description[:8000].strip()
    if len(description) < 20:
        description = (
            f"{_clean_text(rough_description, max_len=500)}\n\n"
            "Please expand this brief with deliverables, timeline, and any technical constraints "
            "before posting."
        )[:8000]

    skills = _clean_skills(raw.get("skills"))
    if not skills:
        skills = ["Communication", "Problem solving", "Time management"]

    budget_min = _as_budget(raw.get("budget_min"), 500.0)
    budget_max = _as_budget(raw.get("budget_max"), max(budget_min * 1.4, budget_min + 100))
    if budget_max < budget_min:
        budget_max = budget_min

    estimated = _clean_text(raw.get("estimated_duration"), max_len=80) or "2-4 weeks"

    return ProjectBriefOut(
        title=title,
        category=_map_category(raw.get("category")),
        description=description,
        skills=skills,
        experience_level=_map_experience(raw.get("experience_level")),
        budget_min=budget_min,
        budget_max=budget_max,
        estimated_duration=estimated,
    )


def generate_project_brief(description: str) -> ProjectBriefOut:
    rough = description.strip()
    prompt = (
        "Turn this rough client request into a structured freelance project brief.\n\n"
        f"Rough description:\n{rough}"
    )
    raw = chat_json(user_prompt=prompt)
    return sanitize_brief(raw, rough)
