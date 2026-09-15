"""Contract dispute rules and payment-safe resolution."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.contract_flow import complete_contract, user_can_access_contract
from app.models import (
    Contract,
    ContractStatus,
    Dispute,
    DisputeResolution,
    DisputeStatus,
    Payment,
    PaymentStatus,
    User,
    UserRole,
    utcnow,
)
from app.notify import notify_many

ACTIVE_DISPUTE_STATUSES = (DisputeStatus.open, DisputeStatus.under_review)
DISPUTEABLE_CONTRACT_STATUSES = (
    ContractStatus.pending,
    ContractStatus.funded,
    ContractStatus.in_progress,
    ContractStatus.submitted,
    ContractStatus.approved,
)


def load_dispute(db: Session, dispute_id: int) -> Dispute | None:
    return db.scalars(
        select(Dispute)
        .options(
            joinedload(Dispute.contract).joinedload(Contract.project),
            joinedload(Dispute.opener),
            joinedload(Dispute.resolver),
        )
        .where(Dispute.id == dispute_id)
    ).unique().first()


def active_dispute_for(db: Session, contract_id: int) -> Dispute | None:
    return db.scalar(
        select(Dispute).where(
            Dispute.contract_id == contract_id,
            Dispute.status.in_(ACTIVE_DISPUTE_STATUSES),
        )
    )


def user_can_access_dispute(user: User, dispute: Dispute) -> bool:
    if user.role == UserRole.admin:
        return True
    contract = dispute.contract
    if contract is None:
        return False
    return user.id in (contract.client_id, contract.freelancer_id, dispute.opened_by)


def open_dispute(db: Session, contract: Contract, actor: User, reason: str, description: str) -> Dispute:
    if not user_can_access_contract(actor, contract):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only contract participants can open a dispute")
    if actor.role == UserRole.admin:
        # Admins resolve disputes; opening should be a party action unless they are also a party.
        if actor.id not in (contract.client_id, contract.freelancer_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only contract participants can open a dispute")

    if contract.status in (ContractStatus.completed, ContractStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completed or cancelled contracts cannot open a dispute",
        )
    if contract.status not in DISPUTEABLE_CONTRACT_STATUSES and contract.status != ContractStatus.disputed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This contract cannot be disputed")

    existing = active_dispute_for(db, contract.id)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active dispute already exists for this contract")

    reason_text = reason.strip()
    description_text = description.strip()
    if len(reason_text) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reason is required")
    if len(description_text) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Description must be at least 10 characters")

    dispute = Dispute(
        contract_id=contract.id,
        opened_by=actor.id,
        reason=reason_text[:200],
        description=description_text,
        status=DisputeStatus.open,
    )
    contract.status = ContractStatus.disputed
    contract.updated_at = utcnow()
    db.add(dispute)
    db.add(contract)
    db.flush()

    title = contract.project.title if contract.project else f"Contract #{contract.id}"
    notify_many(
        db,
        [contract.client_id, contract.freelancer_id],
        actor_id=actor.id,
        kind="dispute_opened",
        title="Dispute opened",
        message=f"A dispute was opened on “{title}”: {reason_text}",
        related_type="contract",
        related_id=contract.id,
    )
    return dispute


def update_dispute(db: Session, dispute: Dispute, actor: User, changes: dict) -> Dispute:
    if not user_can_access_dispute(actor, dispute):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if actor.role == UserRole.admin:
        new_status = changes.get("status")
        if new_status is not None:
            if new_status not in (DisputeStatus.open, DisputeStatus.under_review):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Use the resolve endpoint to resolve or reject a dispute",
                )
            if dispute.status not in ACTIVE_DISPUTE_STATUSES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dispute is already closed")
            dispute.status = new_status

    if actor.role != UserRole.admin and dispute.opened_by != actor.id and actor.id not in (
        dispute.contract.client_id if dispute.contract else None,
        dispute.contract.freelancer_id if dispute.contract else None,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if dispute.status not in ACTIVE_DISPUTE_STATUSES and actor.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Closed disputes cannot be edited")

    if "reason" in changes and changes["reason"] is not None:
        if actor.role != UserRole.admin and dispute.status != DisputeStatus.open:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open disputes can be edited")
        text = str(changes["reason"]).strip()
        if len(text) < 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reason is required")
        dispute.reason = text[:200]
    if "description" in changes and changes["description"] is not None:
        if actor.role != UserRole.admin and dispute.status != DisputeStatus.open:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open disputes can be edited")
        text = str(changes["description"]).strip()
        if len(text) < 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Description must be at least 10 characters")
        dispute.description = text

    dispute.updated_at = utcnow()
    db.add(dispute)
    db.flush()
    return dispute


def _paid_payments(db: Session, contract_id: int) -> list[Payment]:
    return list(
        db.scalars(
            select(Payment).where(Payment.contract_id == contract_id, Payment.status == PaymentStatus.paid)
        ).all()
    )


def _apply_payment_resolution(
    db: Session,
    contract: Contract,
    resolution: DisputeResolution,
    partial_amount: float | None,
) -> None:
    paid = _paid_payments(db, contract.id)
    open_payments = db.scalars(
        select(Payment).where(
            Payment.contract_id == contract.id,
            Payment.status.in_((PaymentStatus.pending, PaymentStatus.processing)),
        )
    ).all()

    if resolution == DisputeResolution.refund_client:
        for payment in paid:
            payment.status = PaymentStatus.refunded
            payment.updated_at = utcnow()
            db.add(payment)
        for payment in open_payments:
            payment.status = PaymentStatus.cancelled
            payment.updated_at = utcnow()
            db.add(payment)
        contract.status = ContractStatus.cancelled
        contract.updated_at = utcnow()
        db.add(contract)
        return

    if resolution == DisputeResolution.release_to_freelancer:
        now = utcnow()
        for payment in paid:
            if payment.milestone_id is not None and payment.released_at is None:
                payment.released_at = now
                payment.updated_at = now
                db.add(payment)
        complete_contract(contract)
        db.add(contract)
        return

    # partial_refund
    if partial_amount is None or partial_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="partial_amount is required for a partial refund")
    total_paid = sum(Decimal(str(payment.amount)) for payment in paid)
    amount = Decimal(str(partial_amount))
    if total_paid <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No paid payment is available to refund")
    if amount > total_paid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="partial_amount cannot exceed paid volume")
    for payment in paid:
        payment.status = PaymentStatus.refunded
        payment.updated_at = utcnow()
        db.add(payment)
    for payment in open_payments:
        payment.status = PaymentStatus.cancelled
        payment.updated_at = utcnow()
        db.add(payment)
    complete_contract(contract)
    db.add(contract)


def resolve_dispute(
    db: Session,
    dispute: Dispute,
    admin: User,
    *,
    outcome: DisputeStatus,
    resolution: DisputeResolution | None = None,
    partial_amount: float | None = None,
    notes: str | None = None,
) -> Dispute:
    if admin.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin can resolve disputes")
    if dispute.status not in ACTIVE_DISPUTE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dispute is already closed")
    if outcome not in (DisputeStatus.resolved, DisputeStatus.rejected):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outcome must be resolved or rejected")

    contract = dispute.contract
    if contract is None:
        contract = db.scalars(
            select(Contract)
            .options(joinedload(Contract.project), joinedload(Contract.freelancer))
            .where(Contract.id == dispute.contract_id)
        ).unique().first()
    else:
        if contract.project is None or contract.freelancer is None:
            contract = db.scalars(
                select(Contract)
                .options(joinedload(Contract.project), joinedload(Contract.freelancer))
                .where(Contract.id == dispute.contract_id)
            ).unique().first()
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    dispute.contract = contract

    now = utcnow()
    if outcome == DisputeStatus.rejected:
        dispute.status = DisputeStatus.rejected
        dispute.resolution = None
        dispute.partial_amount = None
        dispute.resolution_notes = (notes or "").strip() or "Dispute rejected"
        dispute.resolved_by = admin.id
        dispute.resolved_at = now
        dispute.updated_at = now
        if contract.status == ContractStatus.disputed:
            contract.status = ContractStatus.in_progress
            if contract.start_date is None:
                from datetime import date

                contract.start_date = date.today()
            contract.updated_at = now
            db.add(contract)
    else:
        if resolution is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="resolution is required when resolving")
        _apply_payment_resolution(db, contract, resolution, partial_amount)
        dispute.status = DisputeStatus.resolved
        dispute.resolution = resolution
        dispute.partial_amount = partial_amount if resolution == DisputeResolution.partial_refund else None
        dispute.resolution_notes = (notes or "").strip() or None
        dispute.resolved_by = admin.id
        dispute.resolved_at = now
        dispute.updated_at = now

    db.add(dispute)
    db.flush()

    title = contract.project.title if contract.project else f"Contract #{contract.id}"
    notify_many(
        db,
        [contract.client_id, contract.freelancer_id],
        kind="dispute_resolved",
        title="Dispute updated",
        message=f"The dispute on “{title}” was marked {outcome.value.replace('_', ' ')}.",
        related_type="contract",
        related_id=contract.id,
    )
    return dispute
