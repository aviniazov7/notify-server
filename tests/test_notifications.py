import pytest

from .conftest import USERNAME, login, token_for

URL = "/api/v1/notifications"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_history_requires_token(client):
    resp = client.get(URL)

    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer not-a-token", "Basic dXNlcjpwYXNz", "garbage"])
def test_history_rejects_bad_auth_header(client, header):
    assert client.get(URL, headers={"Authorization": header}).status_code == 401


def test_history_rejects_expired_token(make_client):
    client = make_client(session_ttl_seconds=0)

    assert client.get(URL, headers=auth(token_for(client))).status_code == 401


def test_history_empty_before_any_activity(client):
    assert client.get(URL, headers=auth(token_for(client))).json() == []


def test_history_returns_sent_notifications_in_order(client):
    token = token_for(client)
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()  # connected
        for i in range(3):
            ws.send_json({"type": "info", "message": f"msg {i}"})
            ws.receive_json()  # ack

    history = client.get(URL, headers=auth(token)).json()

    assert [n["type"] for n in history] == ["connected", "info", "info", "info"]
    assert [n["message"] for n in history[1:]] == ["msg 0", "msg 1", "msg 2"]
    assert all(n["username"] == USERNAME for n in history)


def test_history_is_scoped_to_the_caller(client):
    client.app.state.users.add("other", "other-password")
    with client.websocket_connect(f"/api/v1/ws?token={token_for(client)}") as ws:
        ws.receive_json()
        ws.send_json({"type": "info", "message": "private to tester"})
        ws.receive_json()

    other_token = login(client, "other", "other-password").json()["token"]

    assert client.get(URL, headers=auth(other_token)).json() == []
