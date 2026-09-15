"""Freelancer–project matching.

Deterministic scoring today; swap in an embedding/vector matcher later via FreelancerMatcher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, User, UserRole
from app.schemas import PublicUserOut, RatingSummary, RecommendedFreelancerOut

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#-]{1,}", re.I)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "with",
    "you",
    "your",
    "we",
    "need",
    "looking",
    "project",
    "work",
}


@dataclass(frozen=True)
class ScoredMatch:
    freelancer: User
    match_score: int
    matched_skills: list[str]
    reasons: list[str]


class FreelancerMatcher(Protocol):
    """Pluggable ranking strategy (deterministic now; embeddings later)."""

    def rank(self, project: Project, freelancers: Sequence[User], *, limit: int = 5) -> list[ScoredMatch]:
        ...


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _skill_key(skill: str) -> str:
    return re.sub(r"[^a-z0-9+#.]", "", skill.lower())


def _tokens(*parts: str | None) -> set[str]:
    bag: set[str] = set()
    for part in parts:
        for match in TOKEN_RE.findall(part or ""):
            token = match.lower()
            if token in STOPWORDS or len(token) < 2:
                continue
            bag.add(token)
    return bag


def _public(user: User) -> PublicUserOut:
    avg = round(float(user.rating_avg or 0), 2)
    count = int(user.rating_count or 0)
    return PublicUserOut(
        id=user.id,
        name=user.name,
        role=user.role,
        title=user.title,
        location=user.location,
        bio=user.bio,
        hourly_rate=user.hourly_rate,
        skills=list(user.skills or []),
        ratings=RatingSummary(average=avg, count=count),
        rating_avg=avg,
        rating_count=count,
        projects_done=int(user.projects_done or 0),
    )


class DeterministicFreelancerMatcher:
    """Weighted heuristic matcher. Scores sum toward 0–100."""

    # Weights intentionally documented so an embedding matcher can mirror them.
    W_SKILLS = 40.0
    W_TEXT = 25.0
    W_BUDGET = 15.0
    W_RATING = 12.0
    W_EXPERIENCE = 8.0

    def rank(self, project: Project, freelancers: Sequence[User], *, limit: int = 5) -> list[ScoredMatch]:
        scored = [self._score(project, user) for user in freelancers]
        scored.sort(key=lambda item: (-item.match_score, -(item.freelancer.rating_avg or 0), item.freelancer.id))
        return scored[: max(0, limit)]

    def _score(self, project: Project, user: User) -> ScoredMatch:
        reasons: list[str] = []
        skill_pts, matched = self._skill_overlap(project, user, reasons)
        text_pts = self._text_relevance(project, user, reasons)
        budget_pts = self._budget_fit(project, user, reasons)
        rating_pts = self._rating_score(user, reasons)
        experience_pts = self._experience_score(user, reasons)

        total = skill_pts + text_pts + budget_pts + rating_pts + experience_pts
        match_score = int(round(max(0.0, min(100.0, total))))
        if not reasons and match_score > 0:
            reasons.append("Partial profile fit")
        return ScoredMatch(
            freelancer=user,
            match_score=match_score,
            matched_skills=matched,
            reasons=reasons[:5],
        )

    def _skill_overlap(self, project: Project, user: User, reasons: list[str]) -> tuple[float, list[str]]:
        needed = [s for s in (project.skills or []) if str(s).strip()]
        have = [s for s in (user.skills or []) if str(s).strip()]
        if not needed:
            # Fall back to category token against freelancer skills.
            if not have:
                return 0.0, []
            cat = _norm(project.category)
            soft = [s for s in have if cat and (cat in _norm(s) or _norm(s) in cat)]
            pts = self.W_SKILLS * (0.45 if soft else 0.2)
            if soft:
                reasons.append("Skills related to project category")
            return pts, soft[:5]

        needed_keys = {_skill_key(s): s for s in needed if _skill_key(s)}
        have_keys = {_skill_key(s): s for s in have if _skill_key(s)}
        matched: list[str] = []
        for key, original in needed_keys.items():
            if key in have_keys:
                matched.append(have_keys[key])
                continue
            # Soft containment (e.g. "react" in "react.js")
            for hkey, horig in have_keys.items():
                if key in hkey or hkey in key:
                    matched.append(horig)
                    break

        # Preserve order, unique
        seen: set[str] = set()
        ordered: list[str] = []
        for skill in matched:
            low = skill.lower()
            if low in seen:
                continue
            seen.add(low)
            ordered.append(skill)

        ratio = len(ordered) / max(len(needed_keys), 1)
        pts = self.W_SKILLS * ratio
        if ratio >= 0.75:
            reasons.append("Strong skill match")
        elif ratio >= 0.4:
            reasons.append("Good skill overlap")
        elif ordered:
            reasons.append("Some matching skills")
        return pts, ordered

    def _text_relevance(self, project: Project, user: User, reasons: list[str]) -> float:
        project_tokens = _tokens(
            project.title,
            project.description,
            project.category,
            project.experience_level,
            " ".join(project.skills or []),
        )
        profile_tokens = _tokens(user.title, user.bio, " ".join(user.skills or []))
        if not project_tokens or not profile_tokens:
            return 0.0
        overlap = project_tokens & profile_tokens
        # Prefer denser overlap relative to the smaller set
        ratio = len(overlap) / max(min(len(project_tokens), 24), 1)
        ratio = min(1.0, ratio * 1.4)
        pts = self.W_TEXT * ratio
        if ratio >= 0.45:
            reasons.append("Title and bio align with the brief")
        elif ratio >= 0.2:
            reasons.append("Relevant experience keywords")
        return pts

    def _budget_fit(self, project: Project, user: User, reasons: list[str]) -> float:
        rate = user.hourly_rate
        budget_min = float(project.budget_min or 0)
        budget_max = float(project.budget_max or 0)
        if rate is None or rate <= 0 or budget_max <= 0:
            return self.W_BUDGET * 0.45

        # Rough engagement window: 10–40 billable hours against the project budget.
        low_estimate = float(rate) * 10
        mid_estimate = float(rate) * 20
        high_estimate = float(rate) * 40

        if low_estimate <= budget_max and high_estimate >= budget_min:
            reasons.append("Within project budget")
            return self.W_BUDGET
        if mid_estimate <= budget_max * 1.25:
            reasons.append("Rate is close to the project budget")
            return self.W_BUDGET * 0.7
        if low_estimate > budget_max * 1.5:
            return self.W_BUDGET * 0.15
        return self.W_BUDGET * 0.4

    def _rating_score(self, user: User, reasons: list[str]) -> float:
        avg = float(user.rating_avg or 0)
        count = int(user.rating_count or 0)
        if count <= 0:
            return self.W_RATING * 0.35
        pts = self.W_RATING * (avg / 5.0)
        if avg >= 4.5 and count >= 2:
            reasons.append("High freelancer rating")
        elif avg >= 4.0:
            reasons.append("Solid freelancer rating")
        return pts

    def _experience_score(self, user: User, reasons: list[str]) -> float:
        done = int(user.projects_done or 0)
        ratio = min(1.0, done / 10.0)
        pts = self.W_EXPERIENCE * (0.25 + 0.75 * ratio)
        if done >= 8:
            reasons.append("Proven completed projects")
        elif done >= 3:
            reasons.append("Completed freelance projects")
        return pts


DEFAULT_MATCHER: FreelancerMatcher = DeterministicFreelancerMatcher()


def load_candidate_freelancers(db: Session, *, exclude_user_id: int | None = None) -> list[User]:
    filters = [
        User.role == UserRole.freelancer,
        User.is_active.is_(True),
    ]
    if exclude_user_id is not None:
        filters.append(User.id != exclude_user_id)
    return list(
        db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.rating_avg.desc(), User.projects_done.desc(), User.id.asc())
            .limit(200)
        ).all()
    )


def recommend_freelancers(
    db: Session,
    project: Project,
    *,
    limit: int = 5,
    matcher: FreelancerMatcher | None = None,
) -> list[RecommendedFreelancerOut]:
    engine = matcher or DEFAULT_MATCHER
    candidates = load_candidate_freelancers(db, exclude_user_id=project.client_id)
    ranked = engine.rank(project, candidates, limit=limit)
    return [
        RecommendedFreelancerOut(
            freelancer=_public(item.freelancer),
            match_score=item.match_score,
            matched_skills=item.matched_skills,
            reasons=item.reasons,
        )
        for item in ranked
        if item.match_score > 0
    ]
