from datetime import datetime

from pydantic import BaseModel, Field


# ---------- Auth (REST PUT) ----------
class SessionCreateRequest(BaseModel):
    """Body of PUT /auth/session — the one-off authentication request."""

    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class SessionResponse(BaseModel):
    session_id: str
    token: str
    expires_at: datetime


# ---------- Notifications (over WebSocket) ----------
class NotificationIn(BaseModel):
    """A notification the client pushes to the server through the WS channel."""

    type: str = Field(..., examples=["info", "alert", "trade_signal"])
    message: str = Field(..., max_length=1000)
    data: dict | None = None


class NotificationOut(BaseModel):
    id: str
    username: str
    type: str
    message: str
    data: dict | None = None
    received_at: datetime
