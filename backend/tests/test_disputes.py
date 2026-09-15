"""Dispute management: open, access, duplicate block, admin resolve + payments."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import (
    Contract,
    ContractStatus,
    Dispute,
    Milestone,
    Payment,
    PaymentStatus,
    Project,
    Proposal,
    Review,
    User,
    UserRole,
)
from app.security import hash_password

PASSWORD = "Testpass1"
COVER = "I can deliver this dispute test engagement with clear milestones and updates."
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
    return {"token": body["access_token"], "user": body["user"], "email": body["user"]["email"]}


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
    finally:
        db.close()
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    body = login.json()
    return {"token": body["access_token"], "user": body["user"], "email": email}


def _contract(owner: dict, freelancer: dict, title: str) -> dict:
    project = client.post(
        "/api/projects",
        headers=_headers(owner),
        json={
            "title": title,
            "category": "Development",
            "description": "Dispute management integration test project with enough description text.",
            "skills": ["Python"],
            "budget_min": 100,
            "budget_max": 500,
        },
    )
    assert project.status_code == 201, project.text
    proposal = client.post(
        "/api/proposals",
        headers=_headers(freelancer),
        json={
            "project_id": project.json()["id"],
            "bid_amount": 200,
            "cover_letter": COVER,
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

    created_pay = client.post(f"/api/payments/create/{contract_id}", headers=_headers(owner))
    assert created_pay.status_code == 201, created_pay.text
    confirmed = client.post(
        f"/api/payments/{created_pay.json()['id']}/confirm",
        headers=_headers(owner),
    )
    assert confirmed.status_code == 200, confirmed.text
    started = client.patch(
        f"/api/contracts/{contract_id}",
        headers=_headers(freelancer),
        json={"status": "in_progress"},
    )
    assert started.status_code == 200, started.text
    return {"id": contract_id, "project_id": project.json()["id"]}


def _cleanup(emails: list[str]) -> None:
    db = SessionLocal()
    try:
        users = db.scalars(select(User).where(User.email.in_(emails))).all()
        ids = [user.id for user in users]
        if not ids:
            return
        contracts = db.scalars(
            select(Contract).where(
                (Contract.client_id.in_(ids)) | (Contract.freelancer_id.in_(ids))
            )
        ).all()
        contract_ids = [item.id for item in contracts]
        if contract_ids:
            db.query(Dispute).filter(Dispute.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Review).filter(Review.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Payment).filter(Payment.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Milestone).filter(Milestone.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Contract).filter(Contract.id.in_(contract_ids)).delete(synchronize_session=False)
        db.query(Proposal).filter(
            (Proposal.freelancer_id.in_(ids))
            | (Proposal.project_id.in_(select(Project.id).where(Project.client_id.in_(ids))))
        ).delete(synchronize_session=False)
        db.query(Project).filter(Project.client_id.in_(ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_open_dispute_sets_contract_disputed_and_blocks_duplicates():
    owner = _register("client")
    freelancer = _register("freelancer")
    outsider = _register("client")
    stamp = uuid.uuid4().hex[:6]
    emails = [owner["email"], freelancer["email"], outsider["email"]]
    try:
        contract = _contract(owner, freelancer, f"Dispute open {stamp}")

        denied = client.post(
            f"/api/contracts/{contract['id']}/disputes",
            headers=_headers(outsider),
            json={"reason": "Not my contract", "description": "Outsider should not open this dispute case."},
        )
        assert denied.status_code == 403

        opened = client.post(
            f"/api/contracts/{contract['id']}/disputes",
            headers=_headers(owner),
            json={"reason": "Missed deadline", "description": "Work was not delivered by the agreed date."},
        )
        assert opened.status_code == 201, opened.text
        body = opened.json()
        assert body["status"] == "open"
        assert body["contract_id"] == contract["id"]

        detail = client.get(f"/api/contracts/{contract['id']}", headers=_headers(owner))
        assert detail.status_code == 200
        assert detail.json()["status"] == "disputed"

        duplicate = client.post(
            f"/api/contracts/{contract['id']}/disputes",
            headers=_headers(freelancer),
            json={"reason": "Same issue", "description": "Second active dispute must be blocked by the API."},
        )
        assert duplicate.status_code == 409

        mine = client.get("/api/disputes/mine", headers=_headers(owner))
        assert mine.status_code == 200
        assert any(item["id"] == body["id"] for item in mine.json())

        hidden = client.get(f"/api/disputes/{body['id']}", headers=_headers(outsider))
        assert hidden.status_code == 403
    finally:
        _cleanup(emails)


def test_completed_contract_cannot_open_dispute():
    owner = _register("client")
    freelancer = _register("freelancer")
    emails = [owner["email"], freelancer["email"]]
    try:
        contract = _contract(owner, freelancer, f"Dispute closed {uuid.uuid4().hex[:6]}")
        db = SessionLocal()
        try:
            row = db.get(Contract, contract["id"])
            row.status = ContractStatus.completed
            db.add(row)
            db.commit()
        finally:
            db.close()
        response = client.post(
            f"/api/contracts/{contract['id']}/disputes",
            headers=_headers(owner),
            json={"reason": "Too late", "description": "Completed contracts should reject new disputes."},
        )
        assert response.status_code == 400
    finally:
        _cleanup(emails)


def test_admin_resolve_refund_updates_payment():
    owner = _register("client")
    freelancer = _register("freelancer")
    admin = _make_admin()
    emails = [owner["email"], freelancer["email"], admin["email"]]
    try:
        contract = _contract(owner, freelancer, f"Dispute refund {uuid.uuid4().hex[:6]}")
        db = SessionLocal()
        try:
            payments = db.scalars(select(Payment).where(Payment.contract_id == contract["id"])).all()
            assert payments
            assert any(item.status == PaymentStatus.paid for item in payments)
            row = db.get(Contract, contract["id"])
            row.status = ContractStatus.in_progress
            db.add(row)
            db.commit()
        finally:
            db.close()

        opened = client.post(
            f"/api/contracts/{contract['id']}/disputes",
            headers=_headers(freelancer),
            json={"reason": "Scope change", "description": "Client changed requirements after funding the work."},
        )
        assert opened.status_code == 201, opened.text
        dispute_id = opened.json()["id"]

        forbidden = client.patch(
            f"/api/admin/disputes/{dispute_id}/resolve",
            headers=_headers(owner),
            json={"outcome": "resolved", "resolution": "refund_client"},
        )
        assert forbidden.status_code == 403

        resolved = client.patch(
            f"/api/admin/disputes/{dispute_id}/resolve",
            headers=_headers(admin),
            json={"outcome": "resolved", "resolution": "refund_client", "notes": "Full refund approved"},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolution"] == "refund_client"

        db = SessionLocal()
        try:
            payments = db.scalars(select(Payment).where(Payment.contract_id == contract["id"])).all()
            assert payments
            assert all(
                item.status in (PaymentStatus.refunded, PaymentStatus.cancelled) for item in payments
            )
            assert any(item.status == PaymentStatus.refunded for item in payments)
            contract_row = db.get(Contract, contract["id"])
            assert contract_row.status == ContractStatus.cancelled
        finally:
            db.close()

        admin_list = client.get("/api/admin/disputes", headers=_headers(admin))
        assert admin_list.status_code == 200
        assert all(item["id"] != dispute_id for item in admin_list.json()["items"])
    finally:
        _cleanup(emails)
