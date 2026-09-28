import pytest
from fastapi import status
from starlette.websockets import WebSocketDisconnect

from .conftest import token_for

LOGOUT = "/api/v1/auth/session"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_logout_returns_204_and_invalidates_token(client):
    token = token_for(client)

    resp = client.delete(LOGOUT, headers=auth(token))

    assert resp.status_code == 204
    assert client.get("/api/v1/notifications", headers=auth(token)).status_code == 401
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass
    assert exc.value.code == status.WS_1008_POLICY_VIOLATION


def test_logout_requires_valid_token(client):
    assert client.delete(LOGOUT).status_code == 401
    assert client.delete(LOGOUT, headers=auth("not-a-token")).status_code == 401


def test_logout_twice_fails_the_second_time(client):
    token = token_for(client)

    assert client.delete(LOGOUT, headers=auth(token)).status_code == 204
    assert client.delete(LOGOUT, headers=auth(token)).status_code == 401


def test_logout_closes_open_sockets_of_that_session(client):
    token = token_for(client)
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()  # connected

        assert client.delete(LOGOUT, headers=auth(token)).status_code == 204

        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == status.WS_1000_NORMAL_CLOSURE
        assert exc.value.reason == "logged out"

    assert client.app.state.manager.online_users == []


def test_logout_leaves_other_sessions_connected(client):
    token_a, token_b = token_for(client), token_for(client)
    with (
        client.websocket_connect(f"/api/v1/ws?token={token_a}") as ws_a,
        client.websocket_connect(f"/api/v1/ws?token={token_b}") as ws_b,
    ):
        ws_a.receive_json()
        ws_b.receive_json()

        client.delete(LOGOUT, headers=auth(token_a))

        with pytest.raises(WebSocketDisconnect):
            ws_a.receive_json()
        ws_b.send_json({"type": "info", "message": "still logged in"})
        assert ws_b.receive_json()["type"] == "ack"
