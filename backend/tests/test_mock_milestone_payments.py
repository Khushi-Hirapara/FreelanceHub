"""Mock milestone payments. No Stripe. Uses the existing Payment model."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import Contract, Milestone, MilestoneStatus, Payment, Project, Proposal, Review, User

PASSWORD = "Testpass1"
COVER = "I can deliver this milestone work on time and keep the client updated."


def _register(client: TestClient, role: str, stamp: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "name": f"{role} {stamp[:6]}",
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


def _project(client: TestClient, owner: dict, title: str) -> dict:
    response = client.post(
        "/api/projects",
        headers=_headers(owner),
        json={
            "title": title,
            "category": "Development",
            "description": "A short paid engagement used only by the mock payment tests.",
            "skills": ["Python"],
            "budget_min": 100,
            "budget_max": 500,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _contract(client: TestClient, owner: dict, freelancer: dict, title: str) -> dict:
    project = _project(client, owner, title)
    proposal = client.post(
        "/api/proposals",
        headers=_headers(freelancer),
        json={
            "project_id": project["id"],
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
    return {"id": accepted.json()["contract_id"], "project_id": project["id"]}


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
            db.query(Review).filter(Review.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Payment).filter(Payment.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Milestone).filter(Milestone.contract_id.in_(contract_ids)).delete(synchronize_session=False)
            db.query(Contract).filter(Contract.id.in_(contract_ids)).delete(synchronize_session=False)
        db.query(Proposal).filter(
            (Proposal.freelancer_id.in_(ids)) | (Proposal.project_id.in_(
                select(Project.id).where(Project.client_id.in_(ids))
            ))
        ).delete(synchronize_session=False)
        db.query(Project).filter(Project.client_id.in_(ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_mock_milestone_payment_flow() -> None:
    stamp = uuid.uuid4().hex[:10]
    emails = [
        f"client-{stamp}@example.com",
        f"freelancer-{stamp}@example.com",
        f"outsider-{stamp}@example.com",
    ]
    client = TestClient(app)
    try:
        owner = _register(client, "client", stamp)
        worker = _register(client, "freelancer", stamp)
        outsider = _register(client, "client", f"outsider-{stamp}")
        # outsider email used a different stamp prefix; track the actual address.
        emails.append(outsider["user"]["email"])

        contract = _contract(client, owner, worker, f"Milestone pay {stamp}")

        denied = client.post(
            f"/api/contracts/{contract['id']}/milestones",
            headers=_headers(worker),
            json={"title": "Blocked", "amount": 40},
        )
        assert denied.status_code == 403

        created = client.post(
            f"/api/contracts/{contract['id']}/milestones",
            headers=_headers(owner),
            json={"title": "Design", "description": "First slice", "amount": 80},
        )
        assert created.status_code == 201, created.text
        milestone_id = created.json()["id"]
        assert created.json()["status"] == "pending"

        edited = client.put(
            f"/api/milestones/{milestone_id}",
            headers=_headers(owner),
            json={"title": "Design v2", "amount": 90},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["title"] == "Design v2"
        assert edited.json()["amount"] == 90

        freelancer_edit = client.put(
            f"/api/milestones/{milestone_id}",
            headers=_headers(worker),
            json={"title": "Hijack"},
        )
        assert freelancer_edit.status_code == 403

        freelancer_pay = client.post(
            f"/api/milestones/{milestone_id}/payment",
            headers=_headers(worker),
        )
        assert freelancer_pay.status_code == 403

        outsider_get = client.get(f"/api/milestones/{milestone_id}", headers=_headers(outsider))
        assert outsider_get.status_code in (403, 404)

        payment = client.post(
            f"/api/milestones/{milestone_id}/payment",
            headers=_headers(owner),
            json={"amount": 1, "card_number": "4242424242424242", "cvv": "123"},
        )
        assert payment.status_code == 201, payment.text
        paid_body = payment.json()
        assert paid_body["amount"] == 90
        assert paid_body["payment_method"] == "mock_card"
        assert paid_body["status"] == "pending"
        assert paid_body["milestone_id"] == milestone_id
        assert "card" not in paid_body

        reused = client.post(f"/api/milestones/{milestone_id}/payment", headers=_headers(owner))
        assert reused.status_code == 201
        assert reused.json()["id"] == paid_body["id"]

        failed = client.post(f"/api/milestones/{milestone_id}/payment/fail", headers=_headers(owner))
        assert failed.status_code == 200, failed.text
        assert failed.json()["status"] == "failed"
        still = client.get(f"/api/milestones/{milestone_id}", headers=_headers(owner))
        assert still.json()["status"] == "pending"

        retry = client.post(f"/api/milestones/{milestone_id}/payment", headers=_headers(owner))
        assert retry.status_code == 201
        assert retry.json()["id"] != paid_body["id"]
        assert retry.json()["status"] == "pending"

        confirmed = client.post(
            f"/api/milestones/{milestone_id}/payment/confirm",
            headers=_headers(owner),
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "paid"
        assert confirmed.json()["transaction_id"].startswith("FH-MOCK-")
        again = client.post(
            f"/api/milestones/{milestone_id}/payment/confirm",
            headers=_headers(owner),
        )
        assert again.status_code == 200
        assert again.json()["transaction_id"] == confirmed.json()["transaction_id"]
        assert again.json()["id"] == confirmed.json()["id"]

        funded = client.get(f"/api/milestones/{milestone_id}", headers=_headers(owner))
        assert funded.json()["status"] == "funded"
        contract_after = client.get(f"/api/contracts/{contract['id']}", headers=_headers(owner))
        assert contract_after.json()["status"] == "pending"

        duplicate = client.post(f"/api/milestones/{milestone_id}/payment", headers=_headers(owner))
        assert duplicate.status_code == 409

        early = client.post(f"/api/milestones/{milestone_id}/release", headers=_headers(owner))
        assert early.status_code == 400

        started = client.patch(
            f"/api/milestones/{milestone_id}/status",
            headers=_headers(worker),
            json={"status": "in_progress"},
        )
        assert started.status_code == 200, started.text
        submitted = client.patch(
            f"/api/milestones/{milestone_id}/status",
            headers=_headers(worker),
            json={"status": "submitted"},
        )
        assert submitted.status_code == 200, submitted.text
        approved = client.patch(
            f"/api/milestones/{milestone_id}/status",
            headers=_headers(owner),
            json={"status": "approved"},
        )
        assert approved.status_code == 200, approved.text

        worker_release = client.post(
            f"/api/milestones/{milestone_id}/release",
            headers=_headers(worker),
        )
        assert worker_release.status_code == 403

        released = client.post(f"/api/milestones/{milestone_id}/release", headers=_headers(owner))
        assert released.status_code == 200, released.text
        assert released.json()["status"] == "released"
        assert released.json()["payment_transaction_id"] == confirmed.json()["transaction_id"]

        twice = client.post(f"/api/milestones/{milestone_id}/release", headers=_headers(owner))
        assert twice.status_code == 409

        bypass = client.patch(
            f"/api/milestones/{milestone_id}/status",
            headers=_headers(owner),
            json={"status": "funded"},
        )
        assert bypass.status_code == 400

        # Cancelled milestones cannot be approved or released.
        cancelled_ms = client.post(
            f"/api/contracts/{contract['id']}/milestones",
            headers=_headers(owner),
            json={"title": "Drop", "amount": 20},
        )
        assert cancelled_ms.status_code == 201, cancelled_ms.text
        drop_id = cancelled_ms.json()["id"]
        cancelled = client.patch(
            f"/api/milestones/{drop_id}/status",
            headers=_headers(owner),
            json={"status": "cancelled"},
        )
        assert cancelled.status_code == 200
        assert client.patch(
            f"/api/milestones/{drop_id}/status",
            headers=_headers(owner),
            json={"status": "approved"},
        ).status_code == 400
        assert client.post(f"/api/milestones/{drop_id}/release", headers=_headers(owner)).status_code == 400
        assert client.post(f"/api/milestones/{drop_id}/payment", headers=_headers(owner)).status_code == 400

        # Unpaid approved milestone cannot be released.
        unpaid = client.post(
            f"/api/contracts/{contract['id']}/milestones",
            headers=_headers(owner),
            json={"title": "Unpaid", "amount": 15},
        )
        assert unpaid.status_code == 201
        unpaid_id = unpaid.json()["id"]
        db = SessionLocal()
        try:
            row = db.get(Milestone, unpaid_id)
            row.status = MilestoneStatus.approved
            db.add(row)
            db.commit()
        finally:
            db.close()
        unpaid_release = client.post(f"/api/milestones/{unpaid_id}/release", headers=_headers(owner))
        assert unpaid_release.status_code == 400

        # Existing contract mock payment still works and does not use milestones.
        other = _contract(client, owner, worker, f"Contract pay {stamp}")
        created_pay = client.post(f"/api/payments/create/{other['id']}", headers=_headers(owner))
        assert created_pay.status_code == 201, created_pay.text
        assert created_pay.json()["milestone_id"] is None
        confirmed_contract = client.post(
            f"/api/payments/{created_pay.json()['id']}/confirm",
            headers=_headers(owner),
        )
        assert confirmed_contract.status_code == 200, confirmed_contract.text
        assert confirmed_contract.json()["status"] == "paid"
        funded_contract = client.get(f"/api/contracts/{other['id']}", headers=_headers(owner))
        assert funded_contract.json()["status"] == "funded"

        progressed = client.patch(
            f"/api/contracts/{other['id']}",
            headers=_headers(worker),
            json={"status": "in_progress"},
        )
        assert progressed.status_code == 200, progressed.text
        submitted_contract = client.patch(
            f"/api/contracts/{other['id']}",
            headers=_headers(worker),
            json={"status": "submitted"},
        )
        assert submitted_contract.status_code == 200, submitted_contract.text
        completed = client.patch(
            f"/api/contracts/{other['id']}",
            headers=_headers(owner),
            json={"status": "approved"},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"

        review = client.post(
            "/api/reviews",
            headers=_headers(owner),
            json={"contract_id": other["id"], "rating": 5, "comment": "Solid work."},
        )
        assert review.status_code == 201, review.text
        listed = client.get(f"/api/contracts/{other['id']}/reviews", headers=_headers(owner))
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    finally:
        _cleanup(emails)


if __name__ == "__main__":
    test_mock_milestone_payment_flow()
    print("ok")
