"""In-app notifications. Callers commit; this only stages rows."""

from sqlalchemy.orm import Session

from app.models import Notification


def notify(
    db: Session,
    user_id: int | None,
    *,
    kind: str,
    title: str,
    message: str,
    related_type: str | None = None,
    related_id: int | None = None,
    actor_id: int | None = None,
) -> Notification | None:
    if not user_id:
        return None
    if actor_id is not None and user_id == actor_id:
        return None
    item = Notification(
        user_id=user_id,
        type=kind,
        title=title[:160],
        message=message[:1000],
        related_type=related_type,
        related_id=related_id,
        is_read=False,
    )
    db.add(item)
    db.flush()
    return item


def notify_many(
    db: Session,
    user_ids: list[int | None],
    *,
    actor_id: int | None = None,
    **kwargs,
) -> None:
    seen: set[int] = set()
    for user_id in user_ids:
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        notify(db, user_id, actor_id=actor_id, **kwargs)
