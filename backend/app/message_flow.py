"""Shared message persistence for REST and WebSocket paths."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from fastapi import HTTPException, status

from app.models import Conversation, Message, User, utcnow
from app.notify import notify
from app.schemas import MessageOut


def serialize_message(message: Message) -> dict:
    return MessageOut.model_validate(message).model_dump(mode="json")


def other_participant_id(conversation: Conversation, user_id: int) -> int | None:
    if user_id == conversation.participant_one_id:
        return conversation.participant_two_id
    if user_id == conversation.participant_two_id:
        return conversation.participant_one_id
    return None


def user_in_conversation(conversation: Conversation, user_id: int) -> bool:
    return user_id in (conversation.participant_one_id, conversation.participant_two_id)


def persist_message(
    db: Session,
    *,
    conversation: Conversation,
    sender: User,
    receiver_id: int,
    message_text: str,
) -> Message:
    text = (message_text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")
    if len(text) > 5000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is too long")
    if receiver_id == sender.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot message yourself")
    if not user_in_conversation(conversation, sender.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if receiver_id not in (conversation.participant_one_id, conversation.participant_two_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receiver not in conversation")

    receiver = db.get(User, receiver_id)
    if not receiver or not receiver.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")

    message = Message(
        conversation_id=conversation.id,
        sender_id=sender.id,
        receiver_id=receiver_id,
        message_text=text,
        is_read=False,
    )
    conversation.updated_at = utcnow()
    db.add(message)
    db.add(conversation)

    preview = text if len(text) <= 140 else f"{text[:137]}…"
    notify(
        db,
        receiver_id,
        kind="new_message",
        title="New message",
        message=f"{sender.name}: {preview}",
        related_type="conversation",
        related_id=conversation.id,
        actor_id=sender.id,
    )
    db.commit()
    db.refresh(message)
    return message


def mark_conversation_read(db: Session, conversation_id: int, user_id: int) -> int:
    messages = db.scalars(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.receiver_id == user_id,
            Message.is_read.is_(False),
        )
    ).all()
    for msg in messages:
        msg.is_read = True
        db.add(msg)
    if messages:
        db.commit()
    return len(messages)


def mark_message_read_for_viewer(db: Session, message: Message, viewer_id: int) -> Message:
    if message.receiver_id == viewer_id and not message.is_read:
        message.is_read = True
        db.add(message)
        db.commit()
        db.refresh(message)
    return message
