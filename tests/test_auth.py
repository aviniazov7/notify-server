from datetime import datetime

from .conftest import USERNAME, login


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_success_returns_token(client):
    resp = login(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert len(body["token"]) >= 40  # 32 random bytes, base64url
    assert datetime.fromisoformat(body["expires_at"])


def test_login_wrong_password_is_401(client):
    resp = login(client, password="wrong-password")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


def test_login_unknown_user_is_401(client):
    resp = login(client, username="nobody", password="whatever")

    assert resp.status_code == 401


def test_each_login_issues_a_new_token(client):
    assert login(client).json()["token"] != login(client).json()["token"]


def test_no_demo_user_when_not_configured(make_client):
    client = make_client(demo_username=None, demo_password=None)

    assert login(client, username=USERNAME).status_code == 401
