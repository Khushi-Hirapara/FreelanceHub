from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.milestone_flow import (
    apply_status,
    confirm_milestone_payment,
    create_milestone,
    create_milestone_payment,
    fail_milestone_payment,
    release_milestone,
    require_access,
    update_milestone,
)
from app.models import Contract, Milestone, Payment, PaymentStatus, User
from app.routers.payments import serialize_payment
from app.schemas import MilestoneCreate, MilestoneOut, MilestoneStatusUpdate, MilestoneUpdate, PaymentOut

router = APIRouter(tags=["Milestones"])


def latest_payment(milestone: Milestone) -> Payment | None:
    payments = list(milestone.payments or [])
    if not payments:
        return None
    ranked = sorted(payments, key=lambda item: (item.status != PaymentStatus.paid, -item.id))
    return ranked[0]


def serialize_milestone(milestone: Milestone) -> MilestoneOut:
    payment = latest_payment(milestone)
    return MilestoneOut(
        id=milestone.id,
        contract_id=milestone.contract_id,
        title=milestone.title,
        description=milestone.description,
        amount=float(milestone.amount),
        order_index=milestone.order_index,
        status=milestone.status,
        due_date=milestone.due_date,
        submitted_at=milestone.submitted_at,
        approved_at=milestone.approved_at,
        created_at=milestone.created_at,
        updated_at=milestone.updated_at,
        payment_id=payment.id if payment else None,
        payment_status=payment.status if payment else None,
        payment_paid_at=payment.paid_at if payment else None,
        payment_released_at=payment.released_at if payment else None,
        payment_transaction_id=payment.transaction_id if payment else None,
    )


def load_contract(db: Session, contract_id: int) -> Contract | None:
    return db.scalar(select(Contract).where(Contract.id == contract_id))


def load_milestone(db: Session, milestone_id: int) -> Milestone | None:
    return db.scalars(
        select(Milestone)
        .options(joinedload(Milestone.contract), joinedload(Milestone.payments))
        .where(Milestone.id == milestone_id)
    ).unique().first()


@router.post("/contracts/{contract_id}/milestones", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED)
def create_contract_milestone(
    contract_id: int,
    payload: MilestoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = load_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    milestone = create_milestone(
        db,
        contract,
        current_user,
        title=payload.title,
        description=payload.description,
        amount=payload.amount,
        due_date=payload.due_date,
        order_index=payload.order_index,
    )
    db.commit()
    loaded = load_milestone(db, milestone.id)
    return serialize_milestone(loaded)


@router.get("/contracts/{contract_id}/milestones", response_model=list[MilestoneOut])
def list_contract_milestones(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = load_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    require_access(current_user, contract)
    milestones = db.scalars(
        select(Milestone)
        .options(joinedload(Milestone.payments))
        .where(Milestone.contract_id == contract_id)
        .order_by(Milestone.order_index, Milestone.id)
    ).unique().all()
    return [serialize_milestone(item) for item in milestones]


@router.get("/milestones/{milestone_id}", response_model=MilestoneOut)
def get_milestone(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    require_access(current_user, milestone.contract)
    return serialize_milestone(milestone)


@router.put("/milestones/{milestone_id}", response_model=MilestoneOut)
def put_milestone(
    milestone_id: int,
    payload: MilestoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    update_milestone(db, milestone, current_user, payload.model_dump(exclude_unset=True))
    db.commit()
    loaded = load_milestone(db, milestone.id)
    return serialize_milestone(loaded)


@router.patch("/milestones/{milestone_id}/status", response_model=MilestoneOut)
def patch_milestone_status(
    milestone_id: int,
    payload: MilestoneStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    apply_status(db, milestone, current_user, payload.status)
    db.commit()
    loaded = load_milestone(db, milestone.id)
    return serialize_milestone(loaded)


@router.post("/milestones/{milestone_id}/payment", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def start_milestone_payment(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    try:
        payment = create_milestone_payment(db, milestone, current_user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active payment already exists for this milestone",
        ) from None
    from app.models import Payment as PaymentModel

    loaded = db.scalars(
        select(PaymentModel)
        .options(
            joinedload(PaymentModel.contract).joinedload(Contract.project),
            joinedload(PaymentModel.client),
            joinedload(PaymentModel.freelancer),
        )
        .where(PaymentModel.id == payment.id)
    ).unique().one()
    return serialize_payment(loaded)


@router.post("/milestones/{milestone_id}/payment/confirm", response_model=PaymentOut)
def confirm_payment(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    payment = confirm_milestone_payment(db, milestone, current_user)
    db.commit()
    from app.models import Payment as PaymentModel

    loaded = db.scalars(
        select(PaymentModel)
        .options(
            joinedload(PaymentModel.contract).joinedload(Contract.project),
            joinedload(PaymentModel.client),
            joinedload(PaymentModel.freelancer),
        )
        .where(PaymentModel.id == payment.id)
    ).unique().one()
    return serialize_payment(loaded)


@router.post("/milestones/{milestone_id}/payment/fail", response_model=PaymentOut)
def fail_payment(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    payment = fail_milestone_payment(db, milestone, current_user)
    db.commit()
    from app.models import Payment as PaymentModel

    loaded = db.scalars(
        select(PaymentModel)
        .options(
            joinedload(PaymentModel.contract).joinedload(Contract.project),
            joinedload(PaymentModel.client),
            joinedload(PaymentModel.freelancer),
        )
        .where(PaymentModel.id == payment.id)
    ).unique().one()
    return serialize_payment(loaded)


@router.post("/milestones/{milestone_id}/release", response_model=MilestoneOut)
def release_payment(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = load_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    release_milestone(db, milestone, current_user)
    db.commit()
    loaded = load_milestone(db, milestone.id)
    return serialize_milestone(loaded)
