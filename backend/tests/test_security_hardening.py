"""Security / production-readiness checks for authz, secrets, and payments."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from jose import jwt

from app.config import INSECURE_SECRET_KEYS, Settings, clear_settings_cache
from app.database import SessionLocal
from app.main import app
from app.models import Contract, Project, Proposal, User, UserRole
from app.security import create_access_token, decode_access_token

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


def _cleanup(emails: list[str]) -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email.in_(emails)).all()
        ids = [u.id for u in users]
        if not ids:
            return
        contracts = db.query(Contract).filter(
            (Contract.client_id.in_(ids)) | (Contract.freelancer_id.in_(ids))
        ).all()
        contract_ids = [c.id for c in contracts]
        project_ids = [c.project_id for c in contracts]
        if contract_ids:
            db.query(Contract).filter(Contract.id.in_(contract_ids)).delete(synchronize_session=False)
        db.query(Proposal).filter(Proposal.freelancer_id.in_(ids)).delete(synchronize_session=False)
        owned_projects = db.query(Project).filter(Project.client_id.in_(ids)).all()
        project_ids.extend([p.id for p in owned_projects])
        if project_ids:
            db.query(Proposal).filter(Proposal.project_id.in_(project_ids)).delete(synchronize_session=False)
            db.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_public_profile_and_project_hide_email():
    owner = _register("client")
    freelancer = _register("freelancer")
    emails = [owner["email"], freelancer["email"]]
    try:
        created = client.post(
            "/api/projects",
            headers=_headers(owner),
            json={
                "title": "Secure project listing",
                "category": "Web Dev",
                "description": "A project used to verify emails are not leaked publicly.",
                "skills": ["Python"],
                "budget_min": 100,
                "budget_max": 200,
                "experience_level": "Intermediate",
            },
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]

        public_user = client.get(f"/api/users/{owner['user']['id']}")
        assert public_user.status_code == 200
        assert "email" not in public_user.json()

        public_project = client.get(f"/api/projects/{project_id}")
        assert public_project.status_code == 200
        embedded = public_project.json().get("client") or {}
        assert "email" not in embedded
        assert embedded.get("name") == owner["user"]["name"]
    finally:
        _cleanup(emails)


def test_payment_confirm_is_owner_only_and_idempotent():
    owner = _register("client")
    freelancer = _register("freelancer")
    outsider = _register("client")
    emails = [owner["email"], freelancer["email"], outsider["email"]]
    try:
        project = client.post(
            "/api/projects",
            headers=_headers(owner),
            json={
                "title": "Payment ownership project",
                "category": "Web Dev",
                "description": "Verify only the contract client can confirm mock payments.",
                "skills": ["Python"],
                "budget_min": 200,
                "budget_max": 400,
            },
        )
        assert project.status_code == 201, project.text
        proposal = client.post(
            "/api/proposals",
            headers=_headers(freelancer),
            json={
                "project_id": project.json()["id"],
                "bid_amount": 250,
                "cover_letter": "I can deliver this payment ownership test engagement carefully.",
                "estimated_duration": "1 week",
            },
        )
        assert proposal.status_code == 201, proposal.text
        accepted = client.patch(
            f"/api/proposals/{proposal.json()['id']}",
            headers=_headers(owner),
            json={"status": "accepted"},
        )
        assert accepted.status_code == 200, accepted.text
        contract_id = accepted.json()["contract_id"]

        created = client.post(f"/api/payments/create/{contract_id}", headers=_headers(owner))
        assert created.status_code == 201, created.text
        payment_id = created.json()["id"]

        denied = client.post(f"/api/payments/{payment_id}/confirm", headers=_headers(outsider))
        assert denied.status_code == 403

        confirmed = client.post(f"/api/payments/{payment_id}/confirm", headers=_headers(owner))
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "paid"
        tx = confirmed.json()["transaction_id"]

        again = client.post(f"/api/payments/{payment_id}/confirm", headers=_headers(owner))
        assert again.status_code == 200
        assert again.json()["transaction_id"] == tx

        duplicate = client.post(f"/api/payments/create/{contract_id}", headers=_headers(owner))
        assert duplicate.status_code == 409
    finally:
        _cleanup(emails)


def test_expired_jwt_is_rejected():
    owner = _register("client")
    emails = [owner["email"]]
    try:
        expired = create_access_token(str(owner["user"]["id"]), "client", expires_minutes=-1)
        assert decode_access_token(expired) is None
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert response.status_code == 401
    finally:
        _cleanup(emails)


def test_production_rejects_insecure_secret_key():
    clear_settings_cache()
    try:
        try:
            Settings(
                secret_key="change-me-to-a-long-random-string",
                app_env="production",
                database_url="postgresql://postgres:password@localhost:5432/freelancehub",
            )
            raise AssertionError("expected validation error")
        except Exception as exc:  # pydantic ValidationError
            assert "SECRET_KEY" in str(exc) or "secret" in str(exc).lower()
        assert "change-me-to-a-long-random-string" in INSECURE_SECRET_KEYS
    finally:
        clear_settings_cache()


def test_contract_access_idor_blocked():
    owner = _register("client")
    freelancer = _register("freelancer")
    outsider = _register("client")
    emails = [owner["email"], freelancer["email"], outsider["email"]]
    try:
        project = client.post(
            "/api/projects",
            headers=_headers(owner),
            json={
                "title": "Contract IDOR project",
                "category": "Web Dev",
                "description": "Outsiders must not read contract details for other parties.",
                "skills": ["Python"],
                "budget_min": 150,
                "budget_max": 300,
            },
        )
        proposal = client.post(
            "/api/proposals",
            headers=_headers(freelancer),
            json={
                "project_id": project.json()["id"],
                "bid_amount": 200,
                "cover_letter": "Ready to deliver this contract access control test engagement.",
                "estimated_duration": "1 week",
            },
        )
        accepted = client.patch(
            f"/api/proposals/{proposal.json()['id']}",
            headers=_headers(owner),
            json={"status": "accepted"},
        )
        contract_id = accepted.json()["contract_id"]
        denied = client.get(f"/api/contracts/{contract_id}", headers=_headers(outsider))
        assert denied.status_code == 403
        allowed = client.get(f"/api/contracts/{contract_id}", headers=_headers(owner))
        assert allowed.status_code == 200
    finally:
        _cleanup(emails)
