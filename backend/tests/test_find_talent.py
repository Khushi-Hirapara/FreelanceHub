"""Public freelancer directory. No password, email, or token fields."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "Testpass1"
client = TestClient(app)


def _register(role: str, name: str) -> dict:
    stamp = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "name": name,
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


def test_find_talent_is_public_and_filtered():
    stamp = uuid.uuid4().hex[:6]
    freelancer = _register("freelancer", f"Ada {stamp}")
    client_user = _register("client", f"Client {stamp}")
    updated = client.put(
        "/api/users/me",
        headers=_headers(freelancer),
        json={
            "title": "Product Designer",
            "location": f"Lisbon {stamp}",
            "bio": "Figma and product design for SaaS teams.",
            "hourly_rate": 40,
            "skills": ["Figma", "UI"],
        },
    )
    assert updated.status_code == 200, updated.text

    listed = client.get("/api/users")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["page"] == 1
    assert "items" in body
    payload = listed.text
    assert "hashed_password" not in payload
    assert "access_token" not in payload
    assert freelancer["user"]["email"] not in payload

    match = client.get("/api/users", params={"q": stamp, "location": "Lisbon", "skill": "design", "max_rate": 50})
    assert match.status_code == 200, match.text
    ids = [item["id"] for item in match.json()["items"]]
    assert freelancer["user"]["id"] in ids
    assert client_user["user"]["id"] not in ids
    card = next(item for item in match.json()["items"] if item["id"] == freelancer["user"]["id"])
    assert set(card) == {
        "id",
        "name",
        "title",
        "location",
        "bio",
        "hourly_rate",
        "skills",
        "ratings",
        "projects_done",
    }
    assert card["ratings"]["count"] == 0
    assert card["hourly_rate"] == 40

    too_cheap = client.get("/api/users", params={"q": stamp, "max_rate": 10})
    assert freelancer["user"]["id"] not in [item["id"] for item in too_cheap.json()["items"]]

    rated = client.get("/api/users", params={"q": stamp, "min_rating": 4})
    assert freelancer["user"]["id"] not in [item["id"] for item in rated.json()["items"]]

    clients = client.get("/api/users", params={"role": "client", "q": stamp})
    assert client_user["user"]["id"] in [item["id"] for item in clients.json()["items"]]

    admin = client.get("/api/users", params={"role": "admin"})
    assert admin.status_code == 400

    paged = client.get("/api/users", params={"page": 1, "limit": 1, "q": stamp})
    assert paged.status_code == 200
    assert paged.json()["limit"] == 1
    assert len(paged.json()["items"]) <= 1


if __name__ == "__main__":
    test_find_talent_is_public_and_filtered()
    print("ok")
