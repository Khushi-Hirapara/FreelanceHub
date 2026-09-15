"""Public freelancer profiles and owner-only portfolio items."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "Testpass1"
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


def test_portfolio_is_public_and_owner_managed():
    owner = _register("freelancer")
    other = _register("client")
    user_id = owner["user"]["id"]

    public = client.get(f"/api/users/{user_id}")
    assert public.status_code == 200
    assert public.json()["name"] == owner["user"]["name"]
    assert "hashed_password" not in public.text

    empty = client.get(f"/api/users/{user_id}/portfolio")
    assert empty.status_code == 200
    assert empty.json() == []

    created = client.post(
        "/api/users/me/portfolio",
        headers=_headers(owner),
        json={
            "title": "Checkout redesign",
            "description": "A calmer payment flow.",
            "project_url": "https://example.com/case",
            "image_url": "https://example.com/shot.png",
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert created.json()["user_id"] == user_id

    listed = client.get(f"/api/users/{user_id}/portfolio")
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "Checkout redesign"
    assert "hashed_password" not in listed.text

    guest = client.post("/api/users/me/portfolio", json={"title": "Nope"})
    assert guest.status_code == 401

    forbidden = client.put(
        f"/api/users/me/portfolio/{item_id}",
        headers=_headers(other),
        json={"title": "Stolen"},
    )
    assert forbidden.status_code == 403

    updated = client.put(
        f"/api/users/me/portfolio/{item_id}",
        headers=_headers(owner),
        json={"title": "Checkout redesign v2"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Checkout redesign v2"

    bad_url = client.post(
        "/api/users/me/portfolio",
        headers=_headers(owner),
        json={"title": "Bad link", "project_url": "javascript:alert(1)"},
    )
    assert bad_url.status_code == 422

    missing = client.get("/api/users/999999/portfolio")
    assert missing.status_code == 404

    deleted = client.delete(f"/api/users/me/portfolio/{item_id}", headers=_headers(owner))
    assert deleted.status_code == 204
    assert client.get(f"/api/users/{user_id}/portfolio").json() == []


if __name__ == "__main__":
    test_portfolio_is_public_and_owner_managed()
    print("ok")
