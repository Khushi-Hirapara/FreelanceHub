from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.contract_flow import user_can_access_contract
from app.database import get_db
from app.deps import get_current_user
from app.models import Contract, Review, User
from app.review_flow import create_review, delete_review, update_review
from app.schemas import ReviewCreate, ReviewOut, ReviewUpdate, ReviewerOut

router = APIRouter(tags=["Reviews"])


def serialize_review(review: Review) -> ReviewOut:
    project_title = None
    if review.contract and review.contract.project:
        project_title = review.contract.project.title
    return ReviewOut(
        id=review.id,
        contract_id=review.contract_id,
        reviewer_id=review.reviewer_id,
        reviewee_id=review.reviewee_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        updated_at=review.updated_at,
        reviewer=ReviewerOut(id=review.reviewer.id, name=review.reviewer.name, role=review.reviewer.role)
        if review.reviewer
        else None,
        project_title=project_title,
    )


def load_review(db: Session, review_id: int) -> Review | None:
    return db.scalars(
        select(Review)
        .options(
            joinedload(Review.reviewer),
            joinedload(Review.reviewee),
            joinedload(Review.contract).joinedload(Contract.project),
        )
        .where(Review.id == review_id)
    ).unique().first()


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def post_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.scalar(select(Contract).where(Contract.id == payload.contract_id))
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    try:
        review = create_review(db, contract, current_user, payload.rating, payload.comment)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already reviewed this contract") from None
    loaded = load_review(db, review.id)
    return serialize_review(loaded)


@router.get("/users/{user_id}/reviews", response_model=list[ReviewOut])
def reviews_for_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    reviews = db.scalars(
        select(Review)
        .options(
            joinedload(Review.reviewer),
            joinedload(Review.contract).joinedload(Contract.project),
        )
        .where(Review.reviewee_id == user_id)
        .order_by(Review.created_at.desc())
    ).unique().all()
    return [serialize_review(item) for item in reviews]


@router.get("/contracts/{contract_id}/reviews", response_model=list[ReviewOut])
def reviews_for_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if not user_can_access_contract(current_user, contract):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    reviews = db.scalars(
        select(Review)
        .options(
            joinedload(Review.reviewer),
            joinedload(Review.contract).joinedload(Contract.project),
        )
        .where(Review.contract_id == contract_id)
        .order_by(Review.created_at.desc())
    ).unique().all()
    return [serialize_review(item) for item in reviews]


@router.put("/reviews/{review_id}", response_model=ReviewOut)
def put_review(
    review_id: int,
    payload: ReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = load_review(db, review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if payload.rating is None and payload.comment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")
    update_review(db, review, current_user, payload.rating, payload.comment)
    db.commit()
    loaded = load_review(db, review.id)
    return serialize_review(loaded)


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = load_review(db, review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    delete_review(db, review, current_user)
    db.commit()
