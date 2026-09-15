"""Project edit rules and client proposal review."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import Project, ProjectStatus

PASSWORD = "Testpass1"
COVER = "I can deliver this brief on time and keep the scope clear for the client."
client = TestClient(app)


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
    return {"token": body["access_token"], "user": body["user"]}


def _headers(actor: dict) -> dict:
    return {"Authorization": f"Bearer {actor['token']}"}


def _project(owner: dict) -> dict:
    response = client.post(
        "/api/projects",
        headers=_headers(owner),
        json={
            "title": "Booking API rebuild",
            "category": "Web Dev",
            "description": "Replace the booking service with a documented FastAPI backend.",
            "skills": ["FastAPI", "PostgreSQL"],
            "budget_min": 800,
            "budget_max": 1200,
            "experience_level": "Intermediate",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _propose(freelancer: dict, project_id: int, bid: float) -> dict:
    response = client.post(
        "/api/proposals",
        headers=_headers(freelancer),
        json={
            "project_id": project_id,
            "bid_amount": bid,
            "estimated_duration": "3 weeks",
            "cover_letter": COVER,
            "milestones": [{"description": "API scaffold", "amount": bid}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_edit_project_and_review_proposals():
    owner = _register("client")
    outsider = _register("client")
    freelancer = _register("freelancer")
    client.put(
        "/api/users/me",
        headers=_headers(freelancer),
        json={"title": "Backend Engineer", "skills": ["FastAPI"]},
    )
    other_freelancer = _register("freelancer")
    project = _project(owner)
    first = _propose(freelancer, project["id"], 900)
    second = _propose(other_freelancer, project["id"], 1000)

    listed = client.get(f"/api/projects/{project['id']}/proposals", headers=_headers(owner))
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert {item["id"] for item in body} == {first["id"], second["id"]}
    card = next(item for item in body if item["id"] == first["id"])
    assert card["freelancer"]["name"] == freelancer["user"]["name"]
    assert card["freelancer"]["skills"] == ["FastAPI"]
    assert card["bid_amount"] == 900
    assert card["milestones"][0]["description"] == "API scaffold"
    assert card["created_at"]

    hidden = client.get(f"/api/projects/{project['id']}/proposals", headers=_headers(outsider))
    assert hidden.status_code == 403

    forbidden_edit = client.put(
        f"/api/projects/{project['id']}",
        headers=_headers(outsider),
        json={"title": "Taken over"},
    )
    assert forbidden_edit.status_code == 403

    bad_budget = client.put(
        f"/api/projects/{project['id']}",
        headers=_headers(owner),
        json={"budget_min": 2000, "budget_max": 1000},
    )
    assert bad_budget.status_code == 422

    updated = client.put(
        f"/api/projects/{project['id']}",
        headers=_headers(owner),
        json={"title": "Booking API rebuild v2", "skills": [" FastAPI ", "PostgreSQL"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Booking API rebuild v2"
    assert updated.json()["skills"] == ["FastAPI", "PostgreSQL"]

    rejected = client.patch(
        f"/api/proposals/{first['id']}",
        headers=_headers(owner),
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    accepted = client.patch(
        f"/api/proposals/{second['id']}",
        headers=_headers(owner),
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["contract_id"]

    db = SessionLocal()
    try:
        stored = db.scalar(select(Project).where(Project.id == project["id"]))
        stored.status = ProjectStatus.completed
        db.add(stored)
        db.commit()
    finally:
        db.close()

    locked = client.put(
        f"/api/projects/{project['id']}",
        headers=_headers(owner),
        json={"title": "Should stay locked"},
    )
    assert locked.status_code == 400


if __name__ == "__main__":
    test_edit_project_and_review_proposals()
    print("ok")
