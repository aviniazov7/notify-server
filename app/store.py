"""Storage layer.

Defines abstract stores (interfaces) and in-memory implementations.
To move to Redis/Firestore later, implement these same ABCs and swap the
instances in main.create_app() — no other code needs to change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

from .security import hash_password, generate_token


# ---------- Domain models ----------
@dataclass
class User:
    username: str
    password_hash: str


@dataclass
class Session:
    session_id: str
    username: str
    token: str
    expires_at: datetime


@dataclass
class Notification:
    id: str
    username: str
    type: str
    message: str
    data: dict | None
    received_at: datetime


# ---------- Interfaces ----------
class UserStore(ABC):
    @abstractmethod
    def get(self, username: str) -> User | None: ...


class SessionStore(ABC):
    @abstractmethod
    def create(self, username: str, ttl_seconds: int) -> Session: ...

    @abstractmethod
    def get_by_token(self, token: str) -> Session | None: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...


class NotificationStore(ABC):
    @abstractmethod
    def add(self, username: str, type: str, message: str, data: dict | None) -> Notification: ...

    @abstractmethod
    def list_for(self, username: str) -> list[Notification]: ...


# ---------- In-memory implementations ----------
class InMemoryUserStore(UserStore):
    def __init__(self) -> None:
        # Demo user for testing: avi / secret123
        self._users: dict[str, User] = {
            "avi": User("avi", hash_password("secret123")),
        }

    def get(self, username: str) -> User | None:
        return self._users.get(username)


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._by_id: dict[str, Session] = {}
        self._by_token: dict[str, Session] = {}

    def create(self, username: str, ttl_seconds: int) -> Session:
        session = Session(
            session_id=str(uuid.uuid4()),
            username=username,
            token=generate_token(),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self._by_id[session.session_id] = session
        self._by_token[session.token] = session
        return session

    def get_by_token(self, token: str) -> Session | None:
        session = self._by_token.get(token)
        if session is None:
            return None
        if session.expires_at < datetime.now(timezone.utc):
            self.delete(session.session_id)  # lazy expiry cleanup
            return None
        return session

    def delete(self, session_id: str) -> None:
        session = self._by_id.pop(session_id, None)
        if session:
            self._by_token.pop(session.token, None)


class InMemoryNotificationStore(NotificationStore):
    def __init__(self) -> None:
        self._items: list[Notification] = []

    def add(self, username: str, type: str, message: str, data: dict | None) -> Notification:
        notification = Notification(
            id=str(uuid.uuid4()),
            username=username,
            type=type,
            message=message,
            data=data,
            received_at=datetime.now(timezone.utc),
        )
        self._items.append(notification)
        return notification

    def list_for(self, username: str) -> list[Notification]:
        return [n for n in self._items if n.username == username]
