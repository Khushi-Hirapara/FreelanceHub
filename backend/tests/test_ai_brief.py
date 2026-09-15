"""AI project brief assistant — Gemini provider, never auto-publishes."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai_brief import sanitize_brief
from app.gemini_client import chat_json
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


def test_sanitize_brief_maps_and_clamps():
    brief = sanitize_brief(
        {
            "title": "  Restaurant website  ",
            "category": "web development",
            "description": "Build a modern restaurant site with online booking and a menu.",
            "skills": ["HTML", "HTML", "CSS", "Booking API", "x"],
            "experience_level": "senior",
            "budget_min": 1200,
            "budget_max": 800,
            "estimated_duration": "3 weeks",
        },
        "I need a website for my restaurant with online booking.",
    )
    assert brief.title == "Restaurant website"
    assert brief.category == "Web Dev"
    assert brief.experience_level == "Expert"
    assert brief.budget_max >= brief.budget_min
    assert brief.skills[0] == "HTML"
    assert brief.skills.count("HTML") == 1
    assert brief.estimated_duration == "3 weeks"


def test_project_brief_requires_client_and_does_not_create_project():
    owner = _register("client")
    freelancer = _register("freelancer")

    denied = client.post(
        "/api/ai/project-brief",
        headers=_headers(freelancer),
        json={"description": "I need a website for my restaurant with online booking."},
    )
    assert denied.status_code == 403

    guest = client.post(
        "/api/ai/project-brief",
        json={"description": "I need a website for my restaurant with online booking."},
    )
    assert guest.status_code == 401

    fake = {
        "title": "Restaurant Website with Online Booking",
        "category": "Web Dev",
        "description": (
            "Create a responsive restaurant website with menu pages, photo gallery, "
            "and an online booking flow for tables."
        ),
        "skills": ["HTML", "CSS", "JavaScript", "Booking systems"],
        "experience_level": "Intermediate",
        "budget_min": 800,
        "budget_max": 1800,
        "estimated_duration": "2-4 weeks",
    }

    with patch("app.ai_brief.chat_json", return_value=fake) as mocked:
        response = client.post(
            "/api/ai/project-brief",
            headers=_headers(owner),
            json={"description": "I need a website for my restaurant with online booking."},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["title"] == fake["title"]
        assert body["category"] == "Web Dev"
        assert isinstance(body["skills"], list)
        assert body["budget_max"] >= body["budget_min"]
        assert body["estimated_duration"] == "2-4 weeks"
        mocked.assert_called_once()
        assert "GEMINI_API_KEY" not in response.text
        assert "AIza" not in response.text

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    assert all(item.get("title") != fake["title"] for item in projects.json())


def test_gemini_missing_key_and_errors_surface_safely():
    owner = _register("client")

    with patch("app.gemini_client.get_settings") as settings_mock:
        settings = settings_mock.return_value
        settings.gemini_api_key = ""
        settings.gemini_model = "gemini-3.6-flash"
        settings.gemini_timeout_seconds = 5.0
        try:
            chat_json(user_prompt="hello")
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 503
            assert "GEMINI_API_KEY" in exc.detail
            assert "AIza" not in exc.detail

    secret = ""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError(
        f"Permission denied for key {secret}"
    )

    with patch("app.gemini_client.get_settings") as settings_mock:
        settings = settings_mock.return_value
        settings.gemini_api_key = "test-gemini-key-not-real"
        settings.gemini_model = "gemini-3.6-flash"
        settings.gemini_timeout_seconds = 5.0
        with patch("app.gemini_client.genai.Client", return_value=mock_client):
            try:
                chat_json(user_prompt="hello")
                raise AssertionError("expected HTTPException")
            except HTTPException as exc:
                assert exc.status_code in (429, 502, 504)
                assert secret not in exc.detail
                assert "test-gemini-key-not-real" not in exc.detail

    with patch(
        "app.ai_brief.chat_json",
        side_effect=HTTPException(
            status_code=504,
            detail="AI brief assistant timed out. Try again in a moment.",
        ),
    ):
        response = client.post(
            "/api/ai/project-brief",
            headers=_headers(owner),
            json={"description": "I need a website for my restaurant with online booking."},
        )
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"].lower()


def test_gemini_response_parsed_to_existing_brief_shape():
    payload = {
        "title": "Cafe Booking Site",
        "category": "Web Dev",
        "description": "Responsive restaurant website with online table booking and menu pages.",
        "skills": ["HTML", "CSS", "JavaScript"],
        "experience_level": "Intermediate",
        "budget_min": 700,
        "budget_max": 1500,
        "estimated_duration": "2-3 weeks",
    }
    mock_response = MagicMock()
    mock_response.text = __import__("json").dumps(payload)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.gemini_client.get_settings") as settings_mock:
        settings = settings_mock.return_value
        settings.gemini_api_key = "test-gemini-key-not-real"
        settings.gemini_model = "gemini-3.6-flash"
        settings.gemini_timeout_seconds = 5.0
        with patch("app.gemini_client.genai.Client", return_value=mock_client):
            data = chat_json(user_prompt="I need a website for my restaurant with online booking.")

    assert data["title"] == payload["title"]
    assert data["skills"] == payload["skills"]
    mock_client.models.generate_content.assert_called_once()
