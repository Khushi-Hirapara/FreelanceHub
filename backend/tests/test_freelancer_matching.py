"""Deterministic freelancer–project matching."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.freelancer_matching import DeterministicFreelancerMatcher
from app.main import app
from app.models import Project, ProjectStatus, User, UserRole
from app.security import hash_password

client = TestClient(app)
PASSWORD = "Testpass1"


def _register(role: str) -> dict:
    stamp = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "name": f"{role} {stamp}",
            "email": f"{role}-{stamp}@example.com",
            "password": PASSWORD,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"token": body["access_token"], "user": body["user"], "email": body["user"]["email"]}


def _headers(actor: dict) -> dict:
    return {"Authorization": f"Bearer {actor['token']}"}


def _make_freelancer(**fields) -> User:
    stamp = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        user = User(
            name=fields.get("name", f"Freelancer {stamp}"),
            email=fields.get("email", f"match-{stamp}@example.com"),
            hashed_password=hash_password(PASSWORD),
            role=UserRole.freelancer,
            title=fields.get("title"),
            bio=fields.get("bio"),
            skills=fields.get("skills", []),
            hourly_rate=fields.get("hourly_rate"),
            rating_avg=fields.get("rating_avg", 0.0),
            rating_count=fields.get("rating_count", 0),
            projects_done=fields.get("projects_done", 0),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user
    finally:
        db.close()


def _cleanup(emails: list[str], project_ids: list[int] | None = None) -> None:
    db = SessionLocal()
    try:
        if project_ids:
            db.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        users = db.query(User).filter(User.email.in_(emails)).all()
        ids = [u.id for u in users]
        if ids:
            db.query(Project).filter(Project.client_id.in_(ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_deterministic_matcher_prefers_skill_and_budget_fit():
    project = Project(
        id=1,
        client_id=1,
        title="FastAPI booking backend",
        category="Web Dev",
        description="Build a FastAPI and PostgreSQL API for restaurant booking.",
        skills=["Python", "FastAPI", "PostgreSQL"],
        budget_min=800,
        budget_max=1600,
        experience_level="Intermediate",
        status=ProjectStatus.open,
    )
    strong = User(
        id=10,
        name="Strong Dev",
        email="strong@example.com",
        hashed_password="x",
        role=UserRole.freelancer,
        title="Python FastAPI engineer",
        bio="I ship FastAPI and PostgreSQL APIs for booking products.",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        hourly_rate=45,
        rating_avg=4.9,
        rating_count=12,
        projects_done=15,
    )
    weak = User(
        id=11,
        name="Writer",
        email="writer@example.com",
        hashed_password="x",
        role=UserRole.freelancer,
        title="Content writer",
        bio="Blog posts and marketing copy.",
        skills=["Writing", "SEO"],
        hourly_rate=200,
        rating_avg=3.0,
        rating_count=1,
        projects_done=0,
    )
    ranked = DeterministicFreelancerMatcher().rank(project, [weak, strong], limit=5)
    assert ranked[0].freelancer.id == 10
    assert ranked[0].match_score > ranked[1].match_score
    assert "Python" in ranked[0].matched_skills
    assert any("skill" in reason.lower() for reason in ranked[0].reasons)


def test_recommended_freelancers_endpoint():
    owner = _register("client")
    outsider = _register("client")
    emails = [owner["email"], outsider["email"]]
    project_ids: list[int] = []
    freelancers = []
    try:
        strong = _make_freelancer(
            name="API Ace",
            title="Backend engineer",
            bio="FastAPI PostgreSQL specialist for booking platforms.",
            skills=["Python", "FastAPI", "PostgreSQL"],
            hourly_rate=40,
            rating_avg=4.8,
            rating_count=8,
            projects_done=9,
        )
        soft = _make_freelancer(
            name="Generalist",
            title="Web developer",
            bio="I build websites.",
            skills=["HTML", "CSS"],
            hourly_rate=30,
            rating_avg=4.0,
            rating_count=2,
            projects_done=2,
        )
        freelancers = [strong, soft]
        emails.extend([strong.email, soft.email])

        created = client.post(
            "/api/projects",
            headers=_headers(owner),
            json={
                "title": "Restaurant booking API",
                "category": "Web Dev",
                "description": "Need a FastAPI and PostgreSQL backend with online booking endpoints.",
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "budget_min": 900,
                "budget_max": 1800,
                "experience_level": "Intermediate",
            },
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        project_ids.append(project_id)

        denied = client.get(
            f"/api/projects/{project_id}/recommended-freelancers",
            headers=_headers(outsider),
        )
        assert denied.status_code == 403

        response = client.get(
            f"/api/projects/{project_id}/recommended-freelancers?limit=5",
            headers=_headers(owner),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert isinstance(body, list)
        assert len(body) <= 5
        assert body
        top = body[0]
        assert "freelancer" in top
        assert "match_score" in top
        assert "matched_skills" in top
        assert "reasons" in top
        assert top["freelancer"]["id"] == strong.id
        assert top["match_score"] >= body[-1]["match_score"]
    finally:
        _cleanup(emails, project_ids)
