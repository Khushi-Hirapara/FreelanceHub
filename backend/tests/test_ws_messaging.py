"""WebSocket conversation messaging with JWT auth."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "Testpass1"
client = TestClient(app)


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


def test_websocket_message_requires_membership_and_persists():
    client_user = _register("client")
    freelancer = _register("freelancer")
    outsider = _register("client")

    started = client.post(
        "/api/messages",
        headers=_headers(client_user),
        json={
            "receiver_id": freelancer["user"]["id"],
            "message_text": "Hello from REST to open the thread.",
        },
    )
    assert started.status_code == 201, started.text
    conversation_id = started.json()["conversation_id"]

    denied = client.websocket_connect(
        f"/api/ws/conversations/{conversation_id}?token={outsider['token']}"
    )
    try:
        with denied:
            pass
        assert False, "outsider should be rejected"
    except Exception:
        pass

    with client.websocket_connect(
        f"/api/ws/conversations/{conversation_id}?token={freelancer['token']}"
    ) as freel_ws:
        connected = freel_ws.receive_json()
        assert connected["type"] == "connected"
        assert connected["conversation_id"] == conversation_id

        with client.websocket_connect(
            f"/api/ws/conversations/{conversation_id}?token={client_user['token']}"
        ) as client_ws:
            assert client_ws.receive_json()["type"] == "connected"
            client_ws.send_json({"type": "send", "message_text": "Live over WebSocket"})
            event = freel_ws.receive_json()
            assert event["type"] == "message"
            assert event["message"]["message_text"] == "Live over WebSocket"
            assert event["message"]["sender_id"] == client_user["user"]["id"]
            assert event["message"]["receiver_id"] == freelancer["user"]["id"]
            echo = client_ws.receive_json()
            assert echo["message"]["id"] == event["message"]["id"]

    history = client.get(
        f"/api/conversations/{conversation_id}/messages",
        headers=_headers(freelancer),
    )
    assert history.status_code == 200
    texts = [item["message_text"] for item in history.json()]
    assert "Live over WebSocket" in texts
    assert "Hello from REST to open the thread." in texts


if __name__ == "__main__":
    test_websocket_message_requires_membership_and_persists()
    print("ok")
