"""Authenticated conversation WebSockets."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.message_flow import (
    mark_conversation_read,
    mark_message_read_for_viewer,
    other_participant_id,
    persist_message,
    serialize_message,
    user_in_conversation,
)
from app.models import Conversation, User
from app.security import decode_access_token
from app.ws_hub import hub

router = APIRouter(tags=["WebSockets"])


def _auth_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_socket(websocket: WebSocket, conversation_id: int):
    # Prefer a short-lived ticket / subprotocol in future. Query tokens can leak via logs.
    token = websocket.query_params.get("token")
    if not token:
        proto = websocket.headers.get("sec-websocket-protocol")
        if proto:
            token = proto.split(",")[0].strip()
    db = SessionLocal()
    try:
        user = _auth_user(db, token)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        conversation = db.get(Conversation, conversation_id)
        if not conversation or not user_in_conversation(conversation, user.id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await hub.connect(conversation_id, user.id, websocket)
        mark_conversation_read(db, conversation_id, user.id)
        await websocket.send_json(
            {
                "type": "connected",
                "conversation_id": conversation_id,
                "user_id": user.id,
            }
        )

        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            event = (payload.get("type") or "").strip().lower()
            if event == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if event != "send":
                await websocket.send_json({"type": "error", "detail": "Unsupported event"})
                continue

            text = payload.get("message_text") or payload.get("text") or ""
            receiver_id = other_participant_id(conversation, user.id)
            if receiver_id is None:
                await websocket.send_json({"type": "error", "detail": "Invalid conversation"})
                continue

            # Re-load conversation/user in case the session was rolled back.
            conversation = db.get(Conversation, conversation_id)
            sender = db.get(User, user.id)
            if not conversation or not sender:
                await websocket.send_json({"type": "error", "detail": "Conversation unavailable"})
                continue
            try:
                message = persist_message(
                    db,
                    conversation=conversation,
                    sender=sender,
                    receiver_id=receiver_id,
                    message_text=text,
                )
            except Exception as exc:  # noqa: BLE001
                detail = getattr(exc, "detail", None) or "Could not send message"
                await websocket.send_json({"type": "error", "detail": detail})
                db.rollback()
                continue

            # Recipients currently viewing this conversation mark the message read.
            for viewer_id in hub.connected_user_ids(conversation_id):
                if viewer_id == message.receiver_id:
                    message = mark_message_read_for_viewer(db, message, viewer_id)
                    break

            event_payload = {"type": "message", "message": serialize_message(message)}
            await hub.broadcast(conversation_id, event_payload)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — never leave sockets hanging
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:  # noqa: BLE001
            pass
    finally:
        await hub.disconnect(conversation_id, websocket)
        db.close()
