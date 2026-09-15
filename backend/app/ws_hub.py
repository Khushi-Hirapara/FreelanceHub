"""In-memory WebSocket rooms keyed by conversation id."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ConversationHub:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._users: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, conversation_id: int, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[conversation_id].add(websocket)
            self._users[websocket] = user_id

    async def disconnect(self, conversation_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._rooms.get(conversation_id)
            if sockets and websocket in sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._rooms.pop(conversation_id, None)
            self._users.pop(websocket, None)

    def user_id_for(self, websocket: WebSocket) -> int | None:
        return self._users.get(websocket)

    def connected_user_ids(self, conversation_id: int) -> set[int]:
        return {
            self._users[socket]
            for socket in self._rooms.get(conversation_id, set())
            if socket in self._users
        }

    async def broadcast(self, conversation_id: int, payload: dict, *, exclude: WebSocket | None = None) -> None:
        sockets = list(self._rooms.get(conversation_id, set()))
        dead: list[WebSocket] = []
        for socket in sockets:
            if socket is exclude:
                continue
            try:
                await socket.send_json(payload)
            except Exception:  # noqa: BLE001 — drop broken sockets
                dead.append(socket)
        for socket in dead:
            await self.disconnect(conversation_id, socket)


hub = ConversationHub()
