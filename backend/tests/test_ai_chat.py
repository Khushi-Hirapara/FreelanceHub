"""AI messaging assistant — Gemini chat replies for the Messages page."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai_chat import build_prompt, generate_chat_reply
from app.main import app

client = TestClient(app)
PASSWORD = "Testpass1"


def _register(role: str) -> dict:
    stamp = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "name": f"{role} {stamp}",
            "email": f"{role}-{stamp}@example.com",
            "password": PASSWORD,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"token": body["access_token"], "user": body["user"]}


def _headers(actor: dict) -> dict:
    return {"Authorization": f"Bearer {actor['token']}"}


def test_build_prompt_includes_history_and_latest_message():
    prompt = build_prompt(
        "How do milestones work?",
        [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello — how can I help?"},
        ],
    )
    assert "User: Hi" in prompt
    assert "Assistant: Hello — how can I help?" in prompt
    assert "User: How do milestones work?" in prompt
    assert prompt.strip().endswith("Assistant:")


def test_ai_chat_requires_auth_and_returns_reply():
    guest = client.post("/api/ai/chat", json={"message": "How do I post a project?"})
    assert guest.status_code == 401

    user = _register("freelancer")
    with patch("app.ai_chat.chat_text", return_value="Post a project from the client dashboard.") as mocked:
        response = client.post(
            "/api/ai/chat",
            headers=_headers(user),
            json={
                "message": "How do I post a project?",
                "history": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["reply"] == "Post a project from the client dashboard."
        mocked.assert_called_once()
        assert "GEMINI_API_KEY" not in response.text
        assert "AIza" not in response.text


def test_generate_chat_reply_sanitizes_empty():
    with patch("app.ai_chat.chat_text", return_value="   "):
        reply = generate_chat_reply("Help with proposals")
    assert "FreelanceHub" in reply
