import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from .schemas import (
    NotificationIn,
    NotificationOut,
    SessionCreateRequest,
    SessionResponse,
)
from .security import verify_password
from .store import Session

log = logging.getLogger(__name__)

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def current_session(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Session:
    """Resolve 'Authorization: Bearer <token>' to a live session, or 401."""
    session = request.app.state.sessions.get_by_token(creds.credentials) if creds else None
    if session is None:
        log.warning("bearer auth failed path=%s", request.url.path)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session


CurrentSession = Annotated[Session, Depends(current_session)]


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


def _client(ws: WebSocket) -> str:
    return f"{ws.client.host}:{ws.client.port}" if ws.client else "unknown"


def _envelope(kind: str, out: NotificationOut) -> dict:
    """Wrap a notification in the {type, notification} WS message shape."""
    return {"type": kind, "notification": out.model_dump(mode="json")}


class _MalformedFrame(Exception):
    """The client sent a frame that isn't a JSON text message."""


async def _receive_json(ws: WebSocket) -> object:
    """Receive one frame and decode it as JSON.

    Raises WebSocketDisconnect when the client leaves and _MalformedFrame for
    binary frames or invalid JSON, so the caller can reply instead of crashing.
    """
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000), message.get("reason"))
    text = message.get("text")
    if text is None:
        raise _MalformedFrame
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise _MalformedFrame from exc


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
            received_at=datetime.now(UTC),
        )
        if ws.application_state is not WebSocketState.CONNECTED:
            return  # closed server-side (e.g. logout); the endpoint cleans up
        await ws.send_json(_envelope("notification", out))


# ---------- 1) Auth — the one-off PUT request ----------
@router.put("/auth/session", response_model=SessionResponse)
def create_session(body: SessionCreateRequest, request: Request) -> SessionResponse:
    """Validate credentials and open a session. Returns a token for the WS handshake."""
    state = request.app.state
    user = state.users.get(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        log.warning("login failed user=%r", body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    session = state.sessions.create(user.username, state.settings.session_ttl_seconds)
    log.info("login ok user=%r session=%s", user.username, session.session_id)
    return SessionResponse(
        session_id=session.session_id,
        token=session.token,
        expires_at=session.expires_at,
    )


@router.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(request: Request, session: CurrentSession) -> None:
    """Log out: invalidate the token and close the sockets opened with it."""
    state = request.app.state
    state.sessions.delete(session.session_id)
    closed = await state.manager.close_session(
        session.session_id, code=status.WS_1000_NORMAL_CLOSURE, reason="logged out"
    )
    log.info(
        "logout user=%r session=%s closed_sockets=%d", session.username, session.session_id, closed
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(request: Request, session: CurrentSession) -> list[NotificationOut]:
    """The caller's notification history, oldest first (heartbeats are not stored)."""
    return [_to_out(n) for n in request.app.state.notifications.list_for(session.username)]


# ---------- 2) Persistent channel — the server "always listens" ----------
@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: Annotated[str, Query()]) -> None:
    """Authenticated WebSocket. Client streams notifications; server stores + acks."""
    state = ws.app.state
    session = state.sessions.get_by_token(token)
    if session is None:
        # Reject before accepting the socket — bad/expired token.
        log.warning("ws rejected: invalid or expired token client=%s", _client(ws))
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    username = session.username
    await state.manager.connect(username, session.session_id, ws)
    log.info("ws connected user=%r session=%s client=%s", username, session.session_id, _client(ws))

    # As soon as the socket is open, push a real "connected" notification.
    # Stored like any other notification, so it shows up in the user's history too.
    welcome = state.notifications.add(username, "connected", f"{username} is now connected", None)
    await ws.send_json(_envelope("notification", _to_out(welcome)))

    # Background task: push a heartbeat every heartbeat_seconds while connected.
    hb_task = asyncio.create_task(_heartbeat(username, ws, state.settings.heartbeat_seconds))

    try:
        while True:
            try:
                raw = await _receive_json(ws)
                if ws.application_state is not WebSocketState.CONNECTED:
                    break  # closed server-side (logout) while this frame was in flight
            except _MalformedFrame:
                log.debug("ws malformed frame user=%r", username)
                await ws.send_json({"type": "error", "message": "invalid JSON"})
                continue

            # Validate the incoming notification against the schema.
            try:
                incoming = NotificationIn(**raw)
            except (ValidationError, TypeError):
                log.debug("ws invalid notification user=%r", username)
                await ws.send_json({"type": "error", "message": "invalid notification"})
                continue

            # Session can expire mid-connection — re-check on every message.
            if state.sessions.get_by_token(token) is None:
                log.info("ws session expired user=%r session=%s", username, session.session_id)
                await ws.send_json({"type": "error", "message": "session expired"})
                await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                break

            saved = state.notifications.add(
                username, incoming.type, incoming.message, incoming.data
            )
            await ws.send_json(_envelope("ack", _to_out(saved)))

    except WebSocketDisconnect as exc:
        log.info(
            "ws disconnected user=%r session=%s code=%s", username, session.session_id, exc.code
        )
    finally:
        # Always stop the heartbeat and drop the connection, however we exit.
        hb_task.cancel()
        state.manager.disconnect(username, session.session_id, ws)
