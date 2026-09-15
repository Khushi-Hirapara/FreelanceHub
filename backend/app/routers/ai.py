"""AI-assisted helpers. Never publish projects automatically."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.ai_brief import generate_project_brief
from app.ai_chat import generate_chat_reply
from app.config import get_settings
from app.deps import get_current_user, require_roles
from app.models import User, UserRole
from app.rate_limit import enforce_rate_limit
from app.schemas import AiChatOut, AiChatRequest, ProjectBriefOut, ProjectBriefRequest

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/project-brief", response_model=ProjectBriefOut)
def project_brief(
    payload: ProjectBriefRequest,
    request: Request,
    _: User = Depends(require_roles(UserRole.client, UserRole.admin)),
):
    """Suggest a structured brief from a rough description. Does not create a project."""
    settings = get_settings()
    enforce_rate_limit(request, bucket="ai", limit=settings.rate_limit_ai_per_minute)
    return generate_project_brief(payload.description)


@router.post("/chat", response_model=AiChatOut)
def ai_chat(
    payload: AiChatRequest,
    request: Request,
    _: User = Depends(get_current_user),
):
    """Reply as FreelanceHub Assistant on the Messages page (Gemini). Does not send user DMs."""
    settings = get_settings()
    enforce_rate_limit(request, bucket="ai", limit=settings.rate_limit_ai_per_minute)
    history = [{"role": turn.role, "content": turn.content} for turn in payload.history]
    reply = generate_chat_reply(payload.message, history)
    return AiChatOut(reply=reply)
