"""Admin dashboard APIs are restricted to the admin role."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import User, UserRole
from app.security import hash_password

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


def _make_admin() -> dict:
    stamp = uuid.uuid4().hex[:8]
    email = f"admin-{stamp}@example.com"
    db = SessionLocal()
    try:
        user = User(
            name=f"Admin {stamp}",
            email=email,
            hashed_password=hash_password(PASSWORD),
            role=UserRole.admin,
            skills=[],
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    body = login.json()
    return {"token": body["access_token"], "user": body["user"], "id": user_id}


def test_admin_dashboard_is_admin_only():
    admin = _make_admin()
    client_user = _register("client")
    freelancer = _register("freelancer")

    denied = client.get("/api/admin/dashboard", headers=_headers(client_user))
    assert denied.status_code == 403
    denied_f = client.get("/api/admin/users", headers=_headers(freelancer))
    assert denied_f.status_code == 403
    guest = client.get("/api/admin/projects")
    assert guest.status_code == 401

    dashboard = client.get("/api/admin/dashboard", headers=_headers(admin))
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    for key in (
        "total_users",
        "clients",
        "freelancers",
        "projects",
        "active_contracts",
        "completed_contracts",
        "total_payment_volume",
        "platform_revenue",
        "pending_disputes",
    ):
        assert key in body

    users = client.get("/api/admin/users", headers=_headers(admin), params={"q": client_user["user"]["name"], "limit": 5})
    assert users.status_code == 200
    assert users.json()["page"] == 1
    assert any(item["id"] == client_user["user"]["id"] for item in users.json()["items"])
    assert "hashed_password" not in users.text

    projects = client.get("/api/admin/projects", headers=_headers(admin))
    assert projects.status_code == 200
    contracts = client.get("/api/admin/contracts", headers=_headers(admin))
    assert contracts.status_code == 200
    payments = client.get("/api/admin/payments", headers=_headers(admin))
    assert payments.status_code == 200
    disputes = client.get("/api/admin/disputes", headers=_headers(admin))
    assert disputes.status_code == 200

    toggled = client.patch(
        f"/api/admin/users/{client_user['user']['id']}/status",
        headers=_headers(admin),
        json={"is_active": False},
    )
    assert toggled.status_code == 200
    assert toggled.json()["is_active"] is False

    self_block = client.patch(
        f"/api/admin/users/{admin['user']['id']}/status",
        headers=_headers(admin),
        json={"is_active": False},
    )
    assert self_block.status_code == 400


if __name__ == "__main__":
    test_admin_dashboard_is_admin_only()
    print("ok")
