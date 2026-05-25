"""Tracks live WebSocket connections so the server can push to a user later.

Keyed by username, with a set of sockets per user (multiple devices/tabs).
This is what makes the server "always listening" — and it's the hook for
server -> client push when you want bidirectional later.
"""

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._active: dict[str, set[WebSocket]] = {}

    async def connect(self, username: str, ws: WebSocket) -> None:
        await ws.accept()
        self._active.setdefault(username, set()).add(ws)

    def disconnect(self, username: str, ws: WebSocket) -> None:
        conns = self._active.get(username)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            self._active.pop(username, None)

    async def send_to_user(self, username: str, payload: dict) -> None:
        """Push a payload to every live socket of a user (future bidirectional use)."""
        for ws in list(self._active.get(username, [])):
            await ws.send_json(payload)

    @property
    def online_users(self) -> list[str]:
        return list(self._active.keys())
