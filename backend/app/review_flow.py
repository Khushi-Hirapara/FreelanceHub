"""Reviews are allowed only after a contract is completed. One review per party."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Contract, ContractStatus, Review, User, utcnow


def refresh_rating(db: Session, user: User) -> None:
    average, count = db.execute(
        select(func.coalesce(func.avg(Review.rating), 0), func.count(Review.id)).where(Review.reviewee_id == user.id)
    ).one()
    user.rating_avg = round(float(average or 0), 2)
    user.rating_count = int(count or 0)
    user.updated_at = utcnow()
    db.add(user)


def other_party_id(contract: Contract, user_id: int) -> int | None:
    if user_id == contract.client_id:
        return contract.freelancer_id
    if user_id == contract.freelancer_id:
        return contract.client_id
    return None


def create_review(db: Session, contract: Contract, actor: User, rating: int, comment: str) -> Review:
    if contract.status != ContractStatus.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a completed contract can be reviewed")

    reviewee_id = other_party_id(contract, actor.id)
    if reviewee_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the client or freelancer can review this contract")
    if reviewee_id == actor.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot review yourself")

    existing = db.scalar(
        select(Review.id).where(Review.contract_id == contract.id, Review.reviewer_id == actor.id)
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already reviewed this contract")

    review = Review(
        contract_id=contract.id,
        reviewer_id=actor.id,
        reviewee_id=reviewee_id,
        rating=rating,
        comment=comment.strip(),
    )
    db.add(review)
    db.flush()
    reviewee = db.get(User, reviewee_id)
    if reviewee:
        refresh_rating(db, reviewee)
    from app.notify import notify

    title = contract.project.title if contract.project is not None else "a completed contract"
    notify(
        db,
        reviewee_id,
        kind="new_review",
        title="New review",
        message=f"{actor.name} left a {rating}-star review on “{title}”.",
        related_type="contract",
        related_id=contract.id,
        actor_id=actor.id,
    )
    return review


def update_review(db: Session, review: Review, actor: User, rating: int | None, comment: str | None) -> Review:
    if review.reviewer_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own review")
    if rating is not None:
        review.rating = rating
    if comment is not None:
        review.comment = comment.strip()
    review.updated_at = utcnow()
    db.add(review)
    db.flush()
    if review.reviewee:
        refresh_rating(db, review.reviewee)
    return review


def delete_review(db: Session, review: Review, actor: User) -> None:
    if review.reviewer_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own review")
    reviewee = review.reviewee
    db.delete(review)
    db.flush()
    if reviewee:
        refresh_rating(db, reviewee)
