from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.models import Contract, Payment, User, UserRole
from app.payment_flow import (
    confirm_mock_payment,
    create_mock_payment,
    fail_mock_payment,
    user_can_access_payment,
)
from app.schemas import ContractPartyOut, ContractProjectOut, PaymentOut

router = APIRouter(prefix="/payments", tags=["Payments"])


def load_payment(db: Session, payment_id: int) -> Payment | None:
    return db.scalars(
        select(Payment)
        .options(
            joinedload(Payment.contract).joinedload(Contract.project),
            joinedload(Payment.client),
            joinedload(Payment.freelancer),
        )
        .where(Payment.id == payment_id)
    ).unique().first()


def serialize_payment(payment: Payment) -> PaymentOut:
    contract = payment.contract
    project = contract.project if contract else None
    return PaymentOut(
        id=payment.id,
        contract_id=payment.contract_id,
        milestone_id=payment.milestone_id,
        client_id=payment.client_id,
        freelancer_id=payment.freelancer_id,
        amount=float(payment.amount),
        platform_fee=float(payment.platform_fee),
        freelancer_amount=float(payment.freelancer_amount),
        currency=payment.currency,
        payment_method=payment.payment_method,
        transaction_id=payment.transaction_id,
        status=payment.status,
        paid_at=payment.paid_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        contract_status=contract.status if contract else None,
        project=ContractProjectOut.model_validate(project) if project else None,
        client=ContractPartyOut.model_validate(payment.client) if payment.client else None,
        freelancer=ContractPartyOut.model_validate(payment.freelancer) if payment.freelancer else None,
    )


def require_payment_access(payment: Payment, user: User) -> None:
    if not user_can_access_payment(user, payment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/create/{contract_id}", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.scalar(
        select(Contract).where(Contract.id == contract_id).with_for_update()
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    try:
        payment = create_mock_payment(db, contract, current_user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active payment already exists for this contract",
        ) from None

    loaded = load_payment(db, payment.id)
    return serialize_payment(loaded)


@router.post("/{payment_id}/confirm", response_model=PaymentOut)
def confirm_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    confirm_mock_payment(db, payment, current_user)
    db.commit()
    loaded = load_payment(db, payment.id)
    return serialize_payment(loaded)


@router.post("/{payment_id}/fail", response_model=PaymentOut)
def fail_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    fail_mock_payment(db, payment, current_user)
    db.commit()
    loaded = load_payment(db, payment.id)
    return serialize_payment(loaded)


@router.get("/mine", response_model=list[PaymentOut])
def my_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Payment).options(
        joinedload(Payment.contract).joinedload(Contract.project),
        joinedload(Payment.client),
        joinedload(Payment.freelancer),
    )
    if current_user.role != UserRole.admin:
        stmt = stmt.where(
            or_(Payment.client_id == current_user.id, Payment.freelancer_id == current_user.id)
        )
    stmt = stmt.order_by(Payment.created_at.desc())
    payments = db.scalars(stmt).unique().all()
    return [serialize_payment(item) for item in payments]


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = load_payment(db, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    require_payment_access(payment, current_user)
    return serialize_payment(payment)
