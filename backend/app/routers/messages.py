from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.message_flow import mark_conversation_read, persist_message, serialize_message
from app.models import Conversation, Message, Project, User
from app.schemas import ConversationOut, MessageCreate, MessageOut, UserOut
from app.ws_hub import hub

router = APIRouter(tags=["Messages"])


def ordered_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def get_or_create_conversation(
    db: Session,
    user_a: int,
    user_b: int,
    project_id: int | None = None,
) -> Conversation:
    one, two = ordered_pair(user_a, user_b)
    stmt = select(Conversation).where(
        Conversation.participant_one_id == one,
        Conversation.participant_two_id == two,
    )
    if project_id is None:
        stmt = stmt.where(Conversation.project_id.is_(None))
    else:
        stmt = stmt.where(Conversation.project_id == project_id)

    conversation = db.scalar(stmt)
    if conversation:
        return conversation

    project_tag = None
    if project_id is not None:
        project = db.get(Project, project_id)
        if project:
            project_tag = project.title[:80]

    conversation = Conversation(
        participant_one_id=one,
        participant_two_id=two,
        project_id=project_id,
        project_tag=project_tag,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversations = db.scalars(
        select(Conversation)
        .where(
            or_(
                Conversation.participant_one_id == current_user.id,
                Conversation.participant_two_id == current_user.id,
            )
        )
        .order_by(Conversation.updated_at.desc())
    ).all()

    results: list[ConversationOut] = []
    for conv in conversations:
        other_id = (
            conv.participant_two_id
            if conv.participant_one_id == current_user.id
            else conv.participant_one_id
        )
        other = db.get(User, other_id)
        if not other:
            continue

        last = db.scalar(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        unread = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.receiver_id == current_user.id,
                Message.is_read.is_(False),
            )
        ) or 0

        results.append(
            ConversationOut(
                id=conv.id,
                other_user=UserOut.model_validate(other),
                project_id=conv.project_id,
                project_tag=conv.project_tag,
                last_message=last.message_text if last else None,
                unread_count=unread,
                updated_at=conv.updated_at,
            )
        )
    return results


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if current_user.id not in (conversation.participant_one_id, conversation.participant_two_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    mark_conversation_read(db, conversation_id, current_user.id)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    ).all()
    return messages


@router.get("/messages", response_model=list[MessageOut])
def messages_by_query(
    conversation_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_messages(conversation_id, db, current_user)


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    else:
        conversation = get_or_create_conversation(
            db,
            current_user.id,
            payload.receiver_id,
            payload.project_id,
        )

    message = persist_message(
        db,
        conversation=conversation,
        sender=current_user,
        receiver_id=payload.receiver_id,
        message_text=payload.message_text,
    )
    # Keep open WebSocket clients in sync when the REST path is used.
    await hub.broadcast(
        conversation.id,
        {"type": "message", "message": serialize_message(message)},
    )
    return message
