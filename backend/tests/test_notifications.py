"""Database notifications for marketplace events."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "Testpass1"
COVER = "I can deliver this work clearly and keep the client updated throughout."
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


def _types(actor: dict) -> list[str]:
    response = client.get("/api/notifications", headers=_headers(actor))
    assert response.status_code == 200, response.text
    return [item["type"] for item in response.json()]


def test_notifications_for_proposals_messages_and_payment():
    owner = _register("client")
    worker = _register("freelancer")
    other = _register("freelancer")

    project = client.post(
        "/api/projects",
        headers=_headers(owner),
        json={
            "title": "Notification brief",
            "category": "Web Dev",
            "description": "A brief used only to exercise the notification feed.",
            "skills": ["Python"],
            "budget_min": 100,
            "budget_max": 400,
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    first = client.post(
        "/api/proposals",
        headers=_headers(worker),
        json={
            "project_id": project_id,
            "bid_amount": 200,
            "cover_letter": COVER,
            "estimated_duration": "1 week",
        },
    )
    assert first.status_code == 201, first.text
    assert _types(owner) == ["new_proposal"]
    assert _types(worker) == []

    guest = client.get("/api/notifications")
    assert guest.status_code == 401

    hidden = client.patch(f"/api/notifications/1/read", headers=_headers(worker))
    note_id = client.get("/api/notifications", headers=_headers(owner)).json()[0]["id"]
    stolen = client.patch(f"/api/notifications/{note_id}/read", headers=_headers(worker))
    assert stolen.status_code == 404

    second = client.post(
        "/api/proposals",
        headers=_headers(other),
        json={
            "project_id": project_id,
            "bid_amount": 250,
            "cover_letter": COVER,
            "estimated_duration": "2 weeks",
        },
    )
    assert second.status_code == 201, second.text

    rejected = client.patch(
        f"/api/proposals/{first.json()['id']}",
        headers=_headers(owner),
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert "proposal_rejected" in _types(worker)

    accepted = client.patch(
        f"/api/proposals/{second.json()['id']}",
        headers=_headers(owner),
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    accepted_types = _types(other)
    assert "proposal_accepted" in accepted_types
    assert "contract_created" in accepted_types

    contract_id = accepted.json()["contract_id"]
    created = client.post(f"/api/payments/create/{contract_id}", headers=_headers(owner))
    assert created.status_code == 201, created.text
    confirmed = client.post(f"/api/payments/{created.json()['id']}/confirm", headers=_headers(owner))
    assert confirmed.status_code == 200, confirmed.text
    assert "payment_successful" in _types(other)
    assert "payment_successful" not in _types(owner)

    sent = client.post(
        "/api/messages",
        headers=_headers(owner),
        json={"receiver_id": other["user"]["id"], "message_text": "Contract is funded."},
    )
    assert sent.status_code == 201, sent.text
    assert "new_message" in _types(other)
    assert "new_message" not in _types(owner)

    unread = client.get("/api/notifications/unread-count", headers=_headers(other))
    assert unread.status_code == 200
    assert unread.json()["count"] >= 3

    marked = client.patch("/api/notifications/read-all", headers=_headers(other))
    assert marked.status_code == 200
    assert marked.json()["updated"] >= 1
    assert client.get("/api/notifications/unread-count", headers=_headers(other)).json()["count"] == 0


if __name__ == "__main__":
    test_notifications_for_proposals_messages_and_payment()
    print("ok")
