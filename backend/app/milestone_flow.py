"""Milestone rules. Funding and release follow payment records, not the client form."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing import split_agreed_amount
from app.models import (
    Contract,
    ContractStatus,
    Milestone,
    MilestoneStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Proposal,
    User,
    UserRole,
    utcnow,
)
from app.payment_flow import allocate_transaction_id, require_contract_client, require_mock_payments_enabled

ACTIVE_PAYMENT_STATUSES = (PaymentStatus.pending, PaymentStatus.processing, PaymentStatus.paid)

# Work-status changes. funded and released are not in this map.
ALLOWED_TRANSITIONS: dict[MilestoneStatus, dict[MilestoneStatus, set[UserRole]]] = {
    MilestoneStatus.pending: {
        MilestoneStatus.cancelled: {UserRole.client, UserRole.admin},
    },
    MilestoneStatus.funded: {
        MilestoneStatus.in_progress: {UserRole.freelancer, UserRole.admin},
        MilestoneStatus.cancelled: {UserRole.client, UserRole.admin},
    },
    MilestoneStatus.in_progress: {
        MilestoneStatus.submitted: {UserRole.freelancer, UserRole.admin},
        MilestoneStatus.cancelled: {UserRole.client, UserRole.admin},
    },
    MilestoneStatus.submitted: {
        MilestoneStatus.approved: {UserRole.client, UserRole.admin},
        MilestoneStatus.disputed: {UserRole.client, UserRole.freelancer, UserRole.admin},
    },
    MilestoneStatus.approved: {
        MilestoneStatus.disputed: {UserRole.client, UserRole.freelancer, UserRole.admin},
    },
    MilestoneStatus.disputed: {
        MilestoneStatus.in_progress: {UserRole.admin},
        MilestoneStatus.cancelled: {UserRole.admin},
    },
    MilestoneStatus.released: {},
    MilestoneStatus.cancelled: {},
}


def user_can_access_milestone(user: User, contract: Contract) -> bool:
    if user.role == UserRole.admin:
        return True
    return user.id in (contract.client_id, contract.freelancer_id)


def require_access(user: User, contract: Contract) -> None:
    if not user_can_access_milestone(user, contract):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def require_client(user: User, contract: Contract) -> None:
    require_contract_client(user, contract)


def _remaining_budget(db: Session, contract: Contract, exclude_id: int | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(Milestone.amount), 0)).where(
        Milestone.contract_id == contract.id,
        Milestone.status != MilestoneStatus.cancelled,
    )
    if exclude_id is not None:
        stmt = stmt.where(Milestone.id != exclude_id)
    used = Decimal(str(db.scalar(stmt) or 0))
    return Decimal(str(contract.agreed_amount)) - used


def create_milestone(
    db: Session,
    contract: Contract,
    actor: User,
    *,
    title: str,
    description: str | None,
    amount: float,
    due_date,
    order_index: int | None,
) -> Milestone:
    require_client(actor, contract)
    if contract.status != ContractStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Milestones can only be created while the contract is pending",
        )

    agreed, _, _ = split_agreed_amount(amount)
    remaining = _remaining_budget(db, contract)
    if Decimal(str(agreed)) > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Milestone amounts cannot exceed the contract amount",
        )

    if order_index is None:
        current = db.scalar(select(func.max(Milestone.order_index)).where(Milestone.contract_id == contract.id))
        order_index = 0 if current is None else int(current) + 1

    milestone = Milestone(
        contract_id=contract.id,
        title=title.strip(),
        description=(description or "").strip() or None,
        amount=agreed,
        order_index=order_index,
        status=MilestoneStatus.pending,
        due_date=due_date,
    )
    db.add(milestone)
    db.flush()
    return milestone


def update_milestone(db: Session, milestone: Milestone, actor: User, changes: dict) -> Milestone:
    contract = milestone.contract
    require_client(actor, contract)
    if contract.status != ContractStatus.pending or milestone.status != MilestoneStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Milestones can only be edited while the contract and milestone are pending",
        )
    if "amount" in changes and changes["amount"] is not None:
        agreed, _, _ = split_agreed_amount(changes["amount"])
        remaining = _remaining_budget(db, contract, exclude_id=milestone.id)
        if Decimal(str(agreed)) > remaining:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Milestone amounts cannot exceed the contract amount",
            )
        milestone.amount = agreed
    if "title" in changes and changes["title"] is not None:
        milestone.title = changes["title"].strip()
    if "description" in changes:
        milestone.description = (changes["description"] or "").strip() or None
    if "due_date" in changes:
        milestone.due_date = changes["due_date"]
    if "order_index" in changes and changes["order_index"] is not None:
        milestone.order_index = changes["order_index"]
    milestone.updated_at = utcnow()
    db.add(milestone)
    db.flush()
    return milestone


def paid_payment_for(db: Session, milestone: Milestone) -> Payment | None:
    return db.scalar(
        select(Payment)
        .where(
            Payment.milestone_id == milestone.id,
            Payment.status == PaymentStatus.paid,
        )
        .order_by(Payment.id.desc())
    )


def active_payment_for(db: Session, milestone: Milestone) -> Payment | None:
    return db.scalar(
        select(Payment)
        .where(
            Payment.milestone_id == milestone.id,
            Payment.status.in_(ACTIVE_PAYMENT_STATUSES),
        )
        .order_by(Payment.id.desc())
    )


def create_milestone_payment(db: Session, milestone: Milestone, actor: User) -> Payment:
    require_mock_payments_enabled()
    contract = milestone.contract
    require_client(actor, contract)
    if milestone.status == MilestoneStatus.cancelled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot fund a cancelled milestone")

    existing = active_payment_for(db, milestone)
    if existing and existing.status == PaymentStatus.paid:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This milestone already has a paid payment")
    if milestone.status != MilestoneStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a pending milestone can be funded")
    if existing:
        return existing

    agreed, fee, freelancer_amount = split_agreed_amount(float(milestone.amount))
    payment = Payment(
        contract_id=contract.id,
        milestone_id=milestone.id,
        client_id=contract.client_id,
        freelancer_id=contract.freelancer_id,
        amount=agreed,
        platform_fee=fee,
        freelancer_amount=freelancer_amount,
        currency=contract.currency or "USD",
        payment_method=PaymentMethod.mock_card,
        status=PaymentStatus.pending,
        transaction_id=None,
    )
    db.add(payment)
    db.flush()
    return payment


def confirm_milestone_payment(db: Session, milestone: Milestone, actor: User) -> Payment:
    require_mock_payments_enabled()
    contract = milestone.contract
    require_client(actor, contract)
    payment = active_payment_for(db, milestone) or paid_payment_for(db, milestone)
    if payment is None or payment.milestone_id != milestone.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No mock payment for this milestone")

    if payment.status == PaymentStatus.paid:
        return payment
    if payment.status not in (PaymentStatus.pending, PaymentStatus.processing):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This payment cannot be confirmed")
    if milestone.status == MilestoneStatus.cancelled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot fund a cancelled milestone")
    if milestone.status != MilestoneStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Milestone is not awaiting payment")

    now = utcnow()
    payment.status = PaymentStatus.processing
    payment.updated_at = now
    db.flush()

    payment.status = PaymentStatus.paid
    payment.paid_at = now
    payment.transaction_id = allocate_transaction_id(db, now)
    payment.updated_at = now
    milestone.status = MilestoneStatus.funded
    milestone.updated_at = now
    db.add(payment)
    db.add(milestone)
    db.flush()
    from app.payment_flow import queue_payment_notification

    queue_payment_notification(db, "payment_successful", payment, actor.id)
    return payment


def fail_milestone_payment(db: Session, milestone: Milestone, actor: User) -> Payment:
    require_mock_payments_enabled()
    contract = milestone.contract
    require_client(actor, contract)
    payment = db.scalar(
        select(Payment)
        .where(
            Payment.milestone_id == milestone.id,
            Payment.status.in_((PaymentStatus.pending, PaymentStatus.processing, PaymentStatus.failed)),
        )
        .order_by(Payment.id.desc())
    )
    if payment is None or payment.milestone_id != milestone.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No mock payment for this milestone")
    if payment.status == PaymentStatus.failed:
        return payment
    if payment.status == PaymentStatus.paid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A paid demo payment cannot be failed")

    payment.status = PaymentStatus.failed
    payment.updated_at = utcnow()
    milestone.status = MilestoneStatus.pending
    milestone.updated_at = utcnow()
    db.add(payment)
    db.add(milestone)
    db.flush()
    return payment


def release_milestone(db: Session, milestone: Milestone, actor: User) -> Milestone:
    contract = milestone.contract
    require_client(actor, contract)
    payment = paid_payment_for(db, milestone)
    if milestone.status == MilestoneStatus.released or (payment and payment.released_at):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This milestone payment is already released")
    if milestone.status == MilestoneStatus.cancelled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot release a cancelled milestone")
    if milestone.status != MilestoneStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A milestone must be approved before its payment can be released",
        )
    if payment is None or payment.status != PaymentStatus.paid or payment.milestone_id != milestone.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot release an unpaid milestone")

    now = utcnow()
    payment.released_at = now
    payment.updated_at = now
    milestone.status = MilestoneStatus.released
    milestone.updated_at = now
    db.add(payment)
    db.add(milestone)
    db.flush()
    return milestone


def apply_status(db: Session, milestone: Milestone, actor: User, new_status: MilestoneStatus) -> Milestone:
    contract = milestone.contract
    require_access(actor, contract)
    if new_status == milestone.status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Milestone is already in that status")
    if new_status in (MilestoneStatus.funded, MilestoneStatus.released):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fund and release a milestone through the mock payment endpoints",
        )
    if milestone.status == MilestoneStatus.cancelled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change a cancelled milestone")

    allowed = ALLOWED_TRANSITIONS.get(milestone.status, {}).get(new_status)
    if not allowed or actor.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change milestone from {milestone.status.value} to {new_status.value}",
        )
    if actor.role != UserRole.admin:
        if actor.role == UserRole.client and actor.id != contract.client_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your contract")
        if actor.role == UserRole.freelancer and actor.id != contract.freelancer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your contract")

    now = utcnow()
    previous = milestone.status
    milestone.status = new_status
    if new_status == MilestoneStatus.submitted:
        milestone.submitted_at = now
    if new_status == MilestoneStatus.approved:
        milestone.approved_at = now
    milestone.updated_at = now
    db.add(milestone)
    db.flush()
    _notify_milestone_status(db, milestone, actor, previous, new_status)
    return milestone


def _notify_milestone_status(
    db: Session,
    milestone: Milestone,
    actor: User,
    previous: MilestoneStatus,
    new_status: MilestoneStatus,
) -> None:
    from app.notify import notify, notify_many

    contract = milestone.contract
    label = milestone.title
    if new_status == MilestoneStatus.submitted:
        notify(
            db,
            contract.client_id,
            kind="milestone_submitted",
            title="Milestone submitted",
            message=f"“{label}” was submitted for review.",
            related_type="contract",
            related_id=contract.id,
            actor_id=actor.id,
        )
    elif new_status == MilestoneStatus.approved:
        notify(
            db,
            contract.freelancer_id,
            kind="milestone_approved",
            title="Milestone approved",
            message=f"“{label}” was approved.",
            related_type="contract",
            related_id=contract.id,
            actor_id=actor.id,
        )
    elif new_status == MilestoneStatus.disputed:
        notify_many(
            db,
            [contract.client_id, contract.freelancer_id],
            actor_id=actor.id,
            kind="dispute_opened",
            title="Dispute opened",
            message=f"A dispute was opened on “{label}”.",
            related_type="contract",
            related_id=contract.id,
        )
    elif previous == MilestoneStatus.disputed:
        notify_many(
            db,
            [contract.client_id, contract.freelancer_id],
            kind="dispute_resolved",
            title="Dispute resolved",
            message=f"The dispute on “{label}” was resolved.",
            related_type="contract",
            related_id=contract.id,
        )


def seed_from_proposal(db: Session, contract: Contract, proposal: Proposal) -> None:
    raw = proposal.milestones or []
    if not isinstance(raw, list):
        return
    remaining = Decimal(str(contract.agreed_amount))
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            agreed, _, _ = split_agreed_amount(float(item.get("amount") or 0))
        except (TypeError, ValueError):
            continue
        amount = Decimal(str(agreed))
        if amount <= 0 or amount > remaining:
            continue
        title = str(item.get("title") or item.get("description") or "Milestone").strip()[:200]
        description = str(item.get("description") or title).strip() or None
        db.add(
            Milestone(
                contract_id=contract.id,
                title=title or "Milestone",
                description=description,
                amount=agreed,
                order_index=index,
                status=MilestoneStatus.pending,
            )
        )
        remaining -= amount
    db.flush()
