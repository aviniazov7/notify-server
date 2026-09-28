"""Tracks live WebSocket connections so the server can push to a user later.

Indexed two ways: by username (a user can have several devices/tabs open)
and by session, so logging out one session closes only the sockets it
opened. This is what makes the server "always listening" — and it's the
hook for server -> client push when you want bidirectional later.
"""

from fastapi import WebSocket, status


class ConnectionManager:
    def __init__(self) -> None:
        self._by_user: dict[str, set[WebSocket]] = {}
        self._by_session: dict[str, set[WebSocket]] = {}

    async def connect(self, username: str, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._by_user.setdefault(username, set()).add(ws)
        self._by_session.setdefault(session_id, set()).add(ws)

    def disconnect(self, username: str, session_id: str, ws: WebSocket) -> None:
        for index, key in ((self._by_user, username), (self._by_session, session_id)):
            conns = index.get(key)
            if not conns:
                continue
            conns.discard(ws)
            if not conns:
                index.pop(key, None)

    async def close_session(
        self, session_id: str, code: int = status.WS_1000_NORMAL_CLOSURE, reason: str = ""
    ) -> int:
        """Close every socket opened with this session. Returns how many were closed.

        The endpoint's receive loop then sees the disconnect and runs its own
        cleanup (which calls disconnect()).
        """
        sockets = list(self._by_session.get(session_id, ()))
        for ws in sockets:
            await ws.close(code=code, reason=reason)
        return len(sockets)

    async def send_to_user(self, username: str, payload: dict) -> None:
        """Push a payload to every live socket of a user (future bidirectional use)."""
        for ws in list(self._by_user.get(username, [])):
            await ws.send_json(payload)

    @property
    def online_users(self) -> list[str]:
        return list(self._by_user.keys())
