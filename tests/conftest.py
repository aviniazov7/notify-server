from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

USERNAME = "tester"
PASSWORD = "correct-horse"


def make_settings(**overrides) -> Settings:
    """Settings isolated from any local .env, with a long heartbeat so it never fires."""
    values = {
        "demo_username": USERNAME,
        "demo_password": PASSWORD,
        "heartbeat_seconds": 3600,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def make_client() -> Iterator[Callable[..., TestClient]]:
    """Factory: build a started TestClient (lifespan runs, demo user seeded)."""
    clients: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        client = TestClient(create_app(make_settings(**overrides)))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def login(client: TestClient, username: str = USERNAME, password: str = PASSWORD):
    return client.put("/api/v1/auth/session", json={"username": username, "password": password})


def token_for(client: TestClient) -> str:
    resp = login(client)
    assert resp.status_code == 200
    return resp.json()["token"]
