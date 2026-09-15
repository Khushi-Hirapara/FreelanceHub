from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import PortfolioItem, User, UserRole
from app.schemas import (
    PasswordChange,
    PortfolioItemCreate,
    PortfolioItemOut,
    PortfolioItemUpdate,
    PublicUserOut,
    RatingSummary,
    UserOut,
    UserPage,
    UserUpdate,
)
from app.security import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["Users"])

PUBLIC_ROLES = {UserRole.freelancer, UserRole.client}
# Existing Find Talent chips are categories, not a skills column. Match the chip
# against skills, title, and bio so those filters still return real people.
SKILL_TERMS = {
    "web-dev": (
        "web",
        "frontend",
        "front-end",
        "backend",
        "back-end",
        "fullstack",
        "full-stack",
        "full stack",
        "react",
        "javascript",
        "python",
        "developer",
        "engineer",
    ),
    "design": ("design", "figma", "ui", "ux", "brand", "illustrat"),
    "writing": ("writ", "content", "copy", "docs", "blog"),
    "mobile": ("mobile", "ios", "android", "flutter", "react native"),
}


def public_user(user: User) -> PublicUserOut:
    avg = round(float(user.rating_avg or 0), 2)
    count = int(user.rating_count or 0)
    return PublicUserOut(
        id=user.id,
        name=user.name,
        role=user.role,
        title=user.title,
        location=user.location,
        bio=user.bio,
        hourly_rate=user.hourly_rate,
        skills=list(user.skills or []),
        ratings=RatingSummary(average=avg, count=count),
        rating_avg=avg,
        rating_count=count,
        projects_done=int(user.projects_done or 0),
    )


def _skill_clause(term: str):
    needle = f"%{term.strip()}%"
    skills_text = func.coalesce(func.array_to_string(User.skills, " "), "")
    return or_(
        skills_text.ilike(needle),
        User.title.ilike(needle),
        User.bio.ilike(needle),
    )


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(current_user, key, value)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    db.add(current_user)
    db.commit()


@router.get("", response_model=UserPage)
def list_users(
    role: UserRole = Query(default=UserRole.freelancer),
    q: str | None = Query(default=None, max_length=120),
    skill: str | None = Query(default=None, max_length=80),
    location: str | None = Query(default=None, max_length=160),
    min_rate: float | None = Query(default=None, ge=0),
    max_rate: float | None = Query(default=None, ge=0),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=9, ge=1, le=50),
    db: Session = Depends(get_db),
):
    if role not in PUBLIC_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be freelancer or client")
    if min_rate is not None and max_rate is not None and min_rate > max_rate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_rate cannot exceed max_rate")

    filters = [User.role == role, User.is_active.is_(True)]
    query = (q or "").strip()
    if query:
        pattern = f"%{query}%"
        skills_text = func.coalesce(func.array_to_string(User.skills, " "), "")
        filters.append(
            or_(
                User.name.ilike(pattern),
                User.title.ilike(pattern),
                User.bio.ilike(pattern),
                User.location.ilike(pattern),
                skills_text.ilike(pattern),
            )
        )
    skill_query = (skill or "").strip()
    if skill_query and skill_query.lower() != "all":
        terms = SKILL_TERMS.get(skill_query.lower(), (skill_query,))
        filters.append(or_(*[_skill_clause(term) for term in terms]))
    place = (location or "").strip()
    if place:
        filters.append(User.location.ilike(f"%{place}%"))
    if min_rate is not None:
        filters.append(User.hourly_rate.is_not(None))
        filters.append(User.hourly_rate >= min_rate)
    if max_rate is not None:
        filters.append(User.hourly_rate.is_not(None))
        filters.append(User.hourly_rate <= max_rate)
    if min_rating is not None and min_rating > 0:
        filters.append(User.rating_avg >= min_rating)

    total = int(db.scalar(select(func.count()).select_from(User).where(*filters)) or 0)
    pages = (total + limit - 1) // limit if total else 0
    rows = db.scalars(
        select(User)
        .where(*filters)
        .order_by(User.rating_avg.desc(), User.projects_done.desc(), User.name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return UserPage(
        items=[public_user(user) for user in rows],
        page=page,
        limit=limit,
        total=total,
        pages=pages,
    )


def active_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def owned_portfolio_item(db: Session, item_id: int, owner: User) -> PortfolioItem:
    item = db.get(PortfolioItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio item not found")
    if item.user_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own portfolio")
    return item


@router.post("/me/portfolio", response_model=PortfolioItemOut, status_code=status.HTTP_201_CREATED)
def create_portfolio_item(
    payload: PortfolioItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = PortfolioItem(user_id=current_user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/me/portfolio/{item_id}", response_model=PortfolioItemOut)
def update_portfolio_item(
    item_id: int,
    payload: PortfolioItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = owned_portfolio_item(db, item_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")
    for key, value in changes.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/me/portfolio/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = owned_portfolio_item(db, item_id, current_user)
    db.delete(item)
    db.commit()


@router.get("/{user_id}/portfolio", response_model=list[PortfolioItemOut])
def list_portfolio(user_id: int, db: Session = Depends(get_db)):
    active_user_or_404(db, user_id)
    return db.scalars(
        select(PortfolioItem)
        .where(PortfolioItem.user_id == user_id)
        .order_by(PortfolioItem.created_at.desc(), PortfolioItem.id.desc())
    ).all()


@router.get("/{user_id}", response_model=PublicUserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return public_user(user)
