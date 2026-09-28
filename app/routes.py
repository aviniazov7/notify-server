import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError

from .config import settings
from .connection_manager import ConnectionManager
from .schemas import (
    NotificationIn,
    NotificationOut,
    SessionCreateRequest,
    SessionResponse,
)
from .security import verify_password
from .store import (
    InMemoryNotificationStore,
    InMemorySessionStore,
    InMemoryUserStore,
)

router = APIRouter(prefix=settings.api_prefix)

# Shared singletons. Swap these three lines to switch to Redis/Firestore later.
users = InMemoryUserStore()
sessions = InMemorySessionStore()
notifications = InMemoryNotificationStore()
manager = ConnectionManager()


def _to_out(saved) -> NotificationOut:
    """Map a stored Notification to its wire (NotificationOut) form."""
    return NotificationOut(
        id=saved.id,
        username=saved.username,
        type=saved.type,
        message=saved.message,
        data=saved.data,
        received_at=saved.received_at,
    )


async def _heartbeat(username: str, ws: WebSocket, interval: int) -> None:
    """Push a periodic 'still connected' notification while the socket is open.

    Not persisted — it's a live liveness signal, not a stored event, so it
    won't flood the notification history.
    """
    while True:
        await asyncio.sleep(interval)
        out = NotificationOut(
            id=str(uuid.uuid4()),
            username=username,
            type="heartbeat",
            message=f"{username} still connected",
            data=None,
            received_at=datetime.now(timezone.utc),
        )
        await ws.send_json({"type": "notification", "notification": out.model_dump(mode="json")})


# ---------- 1) Auth — the one-off PUT request ----------
@router.put("/auth/session", response_model=SessionResponse)
def create_session(body: SessionCreateRequest) -> SessionResponse:
    """Validate credentials and open a session. Returns a token for the WS handshake."""
    user = users.get(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    session = sessions.create(user.username, settings.session_ttl_seconds)
    return SessionResponse(
        session_id=session.session_id,
        token=session.token,
        expires_at=session.expires_at,
    )


# ---------- 2) Persistent channel — the server "always listens" ----------
@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = Query(...)) -> None:
    """Authenticated WebSocket. Client streams notifications; server stores + acks."""
    session = sessions.get_by_token(token)
    if session is None:
        # Reject before accepting the socket — bad/expired token.
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    username = session.username
    await manager.connect(username, ws)

    # As soon as the socket is open, push a real "connected" notification.
    # Stored like any other notification, so it shows up in the user's history too.
    welcome = notifications.add(username, "connected", f"{username} is now connected", None)
    await ws.send_json({"type": "notification", "notification": _to_out(welcome).model_dump(mode="json")})

    # Background task: push a heartbeat every settings.heartbeat_seconds while connected.
    hb_task = asyncio.create_task(_heartbeat(username, ws, settings.heartbeat_seconds))

    try:
        while True:
            raw = await ws.receive_json()

            # Validate the incoming notification against the schema.
            try:
                incoming = NotificationIn(**raw)
            except (ValidationError, TypeError):
                await ws.send_json({"type": "error", "message": "invalid notification"})
                continue

            # Session can expire mid-connection — re-check on every message.
            if sessions.get_by_token(token) is None:
                await ws.send_json({"type": "error", "message": "session expired"})
                await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                break

            saved = notifications.add(
                username, incoming.type, incoming.message, incoming.data
            )
            await ws.send_json({"type": "ack", "notification": _to_out(saved).model_dump(mode="json")})

    except WebSocketDisconnect:
        pass
    finally:
        # Always stop the heartbeat and drop the connection, however we exit.
        hb_task.cancel()
        manager.disconnect(username, ws)
