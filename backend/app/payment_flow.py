"""Mock payment rules. No gateway, no card data, no real charge."""

import secrets
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import split_agreed_amount
from app.config import get_settings
from app.models import Contract, ContractStatus, Payment, PaymentMethod, PaymentStatus, ProjectStatus, User, utcnow

ACTIVE_PAYMENT_STATUSES = (
    PaymentStatus.pending,
    PaymentStatus.processing,
    PaymentStatus.paid,
)


def require_mock_payments_enabled() -> None:
    """Block payment mutations when PAYMENTS_MODE is not mock (pre-PSP production)."""
    mode = get_settings().payments_mode
    if mode != "mock":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mock payments are disabled. Configure a real payment provider before enabling charges.",
        )


def queue_payment_notification(db: Session, event: str, payment: Payment, actor_id: int | None = None) -> None:
    if event != "payment_successful" or payment is None:
        return
    from app.notify import notify

    label = "a milestone" if payment.milestone_id else "the contract"
    notify(
        db,
        payment.freelancer_id,
        kind="payment_successful",
        title="Payment successful",
        message=f"A demo payment for {label} was marked paid.",
        related_type="payment",
        related_id=payment.id,
        actor_id=actor_id,
    )


def user_can_access_payment(user: User, payment: Payment) -> bool:
    if user.role.value == "admin":
        return True
    return user.id in (payment.client_id, payment.freelancer_id)


def require_contract_client(user: User, contract: Contract) -> None:
    if user.id != contract.client_id or user.role.value != "client":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the contract client can do this")


def create_mock_payment(db: Session, contract: Contract, actor: User) -> Payment:
    require_mock_payments_enabled()
    require_contract_client(actor, contract)

    if contract.status == ContractStatus.funded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This contract is already funded")
    if contract.status != ContractStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A payment can only be created for a pending contract",
        )

    existing = db.scalars(
        select(Payment).where(
            Payment.contract_id == contract.id,
            Payment.milestone_id.is_(None),
            Payment.status.in_(ACTIVE_PAYMENT_STATUSES),
        )
    ).all()
    paid = next((item for item in existing if item.status == PaymentStatus.paid), None)
    if paid or contract.status == ContractStatus.funded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This contract is already funded")

    open_payment = next(
        (item for item in existing if item.status in (PaymentStatus.pending, PaymentStatus.processing)),
        None,
    )
    if open_payment:
        return open_payment

    agreed, fee, freelancer_amount = split_agreed_amount(float(contract.agreed_amount))
    payment = Payment(
        contract_id=contract.id,
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


def new_transaction_id(when: datetime) -> str:
    stamp = when.strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()
    return f"FH-MOCK-{stamp}-{suffix}"


def allocate_transaction_id(db: Session, when: datetime | None = None) -> str:
    return _unused_transaction_id(db, when or utcnow())


def _unused_transaction_id(db: Session, when: datetime) -> str:
    for _ in range(8):
        candidate = new_transaction_id(when)
        taken = db.scalar(select(Payment.id).where(Payment.transaction_id == candidate))
        if not taken:
            return candidate
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not allocate a transaction id")


def confirm_mock_payment(db: Session, payment: Payment, actor: User) -> Payment:
    require_mock_payments_enabled()
    contract = payment.contract
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    require_contract_client(actor, contract)
    if payment.milestone_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm milestone payments through the milestone payment endpoint",
        )

    if payment.status == PaymentStatus.paid:
        return payment

    if payment.status not in (PaymentStatus.pending, PaymentStatus.processing):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This payment cannot be confirmed")

    if contract.status != ContractStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract is not awaiting payment",
        )

    now = utcnow()
    payment.status = PaymentStatus.processing
    payment.updated_at = now
    db.flush()

    payment.status = PaymentStatus.paid
    payment.paid_at = now
    payment.transaction_id = _unused_transaction_id(db, now)
    payment.updated_at = now

    contract.status = ContractStatus.funded
    contract.updated_at = now
    if contract.project is not None and contract.project.status not in (
        ProjectStatus.completed,
        ProjectStatus.cancelled,
    ):
        contract.project.status = ProjectStatus.in_progress
        contract.project.updated_at = now

    queue_payment_notification(db, "payment_successful", payment, actor.id)
    db.add(payment)
    db.add(contract)
    db.flush()
    return payment


def fail_mock_payment(db: Session, payment: Payment, actor: User) -> Payment:
    require_mock_payments_enabled()
    contract = payment.contract
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    require_contract_client(actor, contract)
    if payment.milestone_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fail milestone payments through the milestone payment endpoint",
        )

    if payment.status == PaymentStatus.failed:
        return payment

    if payment.status == PaymentStatus.paid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A paid demo payment cannot be failed")

    if payment.status not in (PaymentStatus.pending, PaymentStatus.processing):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This payment cannot be failed")

    payment.status = PaymentStatus.failed
    payment.updated_at = utcnow()
    # Contract stays pending. A failed demo payment never funds a contract.
    queue_payment_notification(db, "payment_failed", payment, actor.id)
    db.add(payment)
    db.flush()
    return payment
